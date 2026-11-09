"""Durable callback processing and authenticated STK query recovery.

Network calls never hold order locks. All state changes lock order then attempt.
Query success proves the persisted checkout amount, not receipt/date metadata.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from . import mpesa
from .payment_records import sync_order
from ..business_time import UTC, NAIROBI, utc_now, parse_timestamp


def retain_callback(db, payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    event_id = hashlib.sha256(encoded.encode()).hexdigest()
    db.execute('''INSERT INTO payment_callback_inbox(event_id,checkout_request_id,payload)
                  VALUES (?,?,?) ON CONFLICT(event_id) DO NOTHING''',
               (event_id, payload['CheckoutRequestID'], encoded))
    db.commit()
    return event_id


def _issue(db, checkout, message, event_id=None):
    from ..routes.notifications import notify
    db.rollback()
    if event_id:
        db.execute('UPDATE payment_callback_inbox SET issue=? WHERE event_id=?', (message, event_id))
    row = db.execute('SELECT transaction_id,order_id FROM mpesa_transactions WHERE checkout_request_id=?', (checkout,)).fetchone()
    if row:
        db.execute('''INSERT INTO payment_verifications(transaction_id,issue) VALUES (?,?)
                      ON CONFLICT(transaction_id) DO UPDATE SET issue=excluded.issue''', (row['transaction_id'], message))
        notify(db, f"reconcile:{row['transaction_id']}", 'Payment Requires Reconciliation', message, row['order_id'])
    db.commit()


def _provider_time(metadata, transaction, now):
    raw = str(metadata.get('TransactionDate', ''))
    try:
        if len(raw) != 14 or not raw.isdigit():
            raise ValueError()
        value = datetime.strptime(raw, '%Y%m%d%H%M%S').replace(tzinfo=NAIROBI).astimezone(UTC)
        if value < parse_timestamp(transaction['created_at']) - timedelta(minutes=5) or value > now + timedelta(minutes=5):
            raise ValueError()
        return value.isoformat(), 'provider_callback', None
    except ValueError:
        return now.isoformat(), 'verification_time', 'Provider timestamp missing or inconsistent; verification time used'


def reconcile(db, checkout, event_id=None, force=False):
    """Return (safe message, HTTP status). Unknown outcomes stay reserved/pending."""
    tx = db.execute('SELECT * FROM mpesa_transactions WHERE checkout_request_id=?', (checkout,)).fetchone()
    if tx is None:
        db.rollback()
        return 'Callback retained awaiting checkout registration', 202
    payload = None
    event = None
    if event_id:
        event = db.execute('SELECT * FROM payment_callback_inbox WHERE event_id=?', (event_id,)).fetchone()
        payload = json.loads(event['payload'])
    elif tx['status'] == 'successful':
        db.rollback()
        return 'Payment already verified', 200
    if not event_id:
        previous = db.execute('SELECT issue FROM payment_verifications WHERE transaction_id=?',(tx['transaction_id'],)).fetchone()
        if previous and previous['issue'] and 'conflict' in previous['issue'].lower():
            db.rollback()
            return 'Payment conflict requires receipt reconciliation', 202
    if event and event['processed_at']:
        db.rollback()
        return 'Callback already processed', 200
    if event:
        db.execute('UPDATE payment_callback_inbox SET last_attempt_at=CURRENT_TIMESTAMP,attempt_count=attempt_count+1 WHERE event_id=?',(event_id,))

    # Claim a recovery query with a committed timestamp before contacting Daraja.
    now = utc_now()
    if not force and not event:
        db.begin()
        db.execute('INSERT INTO payment_verifications(transaction_id) VALUES (?) ON CONFLICT(transaction_id) DO NOTHING', (tx['transaction_id'],))
        verification = db.execute('SELECT * FROM payment_verifications WHERE transaction_id=?' + (' FOR UPDATE' if db.postgres else ''), (tx['transaction_id'],)).fetchone()
        delay = min(1800, 30 * 2 ** min(verification['query_count'], 6))
        if verification['last_query_at'] and now - parse_timestamp(verification['last_query_at']) < timedelta(seconds=delay):
            db.rollback()
            return 'Payment confirmation pending', 202
        db.execute('UPDATE payment_verifications SET last_query_at=?,query_count=query_count+1 WHERE transaction_id=?', (now.isoformat(), tx['transaction_id']))
    db.commit()
    try:
        code = mpesa.query_stk_status(checkout)
    except mpesa.MpesaError:
        _issue(db, checkout, 'Provider verification unavailable; retry scheduled', event_id)
        return 'Payment verification unavailable; callback retained', 503
    if payload and str(payload.get('ResultCode')) != code:
        _issue(db, checkout, 'Callback result disagrees with provider query', event_id)
        return 'Unverified callback', 409
    if code != '0' and code not in {'1', '1032', '1037', '2001', '1025', '1019'}:
        _issue(db, checkout, 'Provider outcome unresolved; do not retry payment', event_id)
        return 'Payment confirmation pending', 202
    metadata = {}
    if payload:
        container = payload.get('CallbackMetadata', {})
        items = container.get('Item', []) if isinstance(container, dict) else []
        if isinstance(items, list):
            metadata = {v.get('Name'): v.get('Value') for v in items if isinstance(v, dict)}
    receipt = str(metadata.get('MpesaReceiptNumber', '')).strip()
    if code == '0' and payload:
        try:
            valid = (Decimal(str(metadata.get('Amount'))) == Decimal(str(tx['amount']))
                     and payload.get('MerchantRequestID') == tx['merchant_request_id']
                     and str(metadata.get('PhoneNumber')) == tx['phone_number']
                     and 1 <= len(receipt) <= 64 and receipt.isalnum())
        except InvalidOperation:
            valid = False
        if not valid:
            _issue(db, checkout, 'Payment metadata does not match persisted checkout', event_id)
            return 'Payment metadata does not match', 400
    try:
        db.begin()
        order = db.execute('SELECT * FROM orders WHERE order_id=?' + (' FOR UPDATE' if db.postgres else ''), (tx['order_id'],)).fetchone()
        tx = db.execute('SELECT * FROM mpesa_transactions WHERE transaction_id=?' + (' FOR UPDATE' if db.postgres else ''), (tx['transaction_id'],)).fetchone()
        if tx['status'] == 'successful' and (code != '0' or not payload):
            # A later failed callback cannot reverse money already received.
            if event_id:
                db.execute('UPDATE payment_callback_inbox SET processed_at=?,issue=NULL WHERE event_id=?', (now.isoformat(), event_id))
            db.commit()
            return 'Successful payment retained', 200
        if code == '0':
            if receipt:
                conflict = db.execute('SELECT transaction_id FROM mpesa_transactions WHERE mpesa_receipt_number=? AND transaction_id<>?', (receipt, tx['transaction_id'])).fetchone()
                if conflict or (tx['mpesa_receipt_number'] and tx['mpesa_receipt_number'] != receipt):
                    _issue(db, checkout, 'Receipt conflict: manual reconciliation required', event_id)
                    return 'Receipt conflict; payment not applied', 409
            if tx['status'] == 'successful' and tx['mpesa_receipt_number']:
                db.execute('UPDATE payment_callback_inbox SET processed_at=?,issue=NULL WHERE event_id=?', (now.isoformat(), event_id))
                db.commit()
                return 'Callback already processed', 200
            occurred, source, issue = _provider_time(metadata, tx, now)
            if not payload:
                issue = 'STK query confirmed payment; receipt and occurrence time await reconciliation'
            # A delayed callback can enrich a query-confirmed payment, without adding money twice.
            if tx['status'] == 'successful' and source != 'provider_callback':
                occurred = tx['completed_at']
            db.execute('''UPDATE mpesa_transactions SET status='successful',result_code='0',
                          mpesa_receipt_number=COALESCE(?,mpesa_receipt_number), completed_at=?,
                          result_description='Verified by STK query',updated_at=CURRENT_TIMESTAMP WHERE transaction_id=?''',
                       (receipt or None, occurred, tx['transaction_id']))
            db.execute('''INSERT INTO payment_verifications(transaction_id,callback_received_at,provider_paid_at,verified_at,timestamp_source,issue)
                          VALUES (?,?,?,?,?,?) ON CONFLICT(transaction_id) DO UPDATE SET
                          callback_received_at=COALESCE(payment_verifications.callback_received_at,excluded.callback_received_at),
                          provider_paid_at=COALESCE(excluded.provider_paid_at,payment_verifications.provider_paid_at),
                          verified_at=excluded.verified_at,timestamp_source=excluded.timestamp_source,issue=excluded.issue''',
                       (tx['transaction_id'], event['received_at'] if event else None,
                        occurred if source == 'provider_callback' else None, now.isoformat(), source, issue))
            sync_order(db, order, 'mpesa', occurred)
            if tx['status'] == 'successful' and source == 'provider_callback' and order['paid_at'] == tx['completed_at']:
                db.execute('UPDATE orders SET paid_at=? WHERE order_id=?',(occurred,order['order_id']))
            from ..routes.notifications import notify
            if issue or order['order_status'] == 'cancelled' or order['payment_status'] == 'paid':
                notify(db, f"reconcile:{tx['transaction_id']}", 'Payment Requires Reconciliation',
                       issue or 'Receipt received for a paid or cancelled order', tx['order_id'])
        else:
            db.execute('''UPDATE mpesa_transactions SET status=?,result_code=?,result_description=?,
                          completed_at=?,updated_at=CURRENT_TIMESTAMP WHERE transaction_id=? AND status<>'successful' ''',
                       ('cancelled' if code == '1032' else 'failed', code, 'Provider confirmed unsuccessful payment', now.isoformat(), tx['transaction_id']))
        db.execute("UPDATE payment_attempts SET state='resolved',updated_at=CURRENT_TIMESTAMP WHERE checkout_request_id=?", (checkout,))
        if event_id:
            db.execute('UPDATE payment_callback_inbox SET processed_at=?,issue=NULL WHERE event_id=?', (now.isoformat(), event_id))
        db.commit()
        return 'Callback processed' if payload else 'Payment status verified', 200
    except sqlite3.IntegrityError:
        _issue(db, checkout, 'Constraint conflict: manual reconciliation required', event_id)
        return 'Payment constraint conflict; reconciliation required', 409


def reconcile_pending(db, limit=50):
    """Bounded worker batch. No STK pushes or refunds are initiated here."""
    rows = db.execute("""SELECT mt.checkout_request_id FROM mpesa_transactions mt
                         LEFT JOIN payment_verifications pv ON pv.transaction_id=mt.transaction_id
                         WHERE mt.status='pending' ORDER BY COALESCE(pv.last_query_at,mt.created_at),mt.transaction_id LIMIT ?""", (limit,)).fetchall()
    results = [reconcile(db, row['checkout_request_id']) for row in rows]
    events = db.execute('''SELECT inbox.event_id,inbox.checkout_request_id FROM payment_callback_inbox inbox
                           JOIN mpesa_transactions mt ON mt.checkout_request_id=inbox.checkout_request_id
                           WHERE inbox.processed_at IS NULL
                           ORDER BY COALESCE(inbox.last_attempt_at,inbox.received_at),inbox.event_id LIMIT ?''', (limit,)).fetchall()
    for event in events:
        results.append(reconcile(db, event['checkout_request_id'], event['event_id']))
    return results
