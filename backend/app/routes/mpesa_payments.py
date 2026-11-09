"""Customer payment intents, status recovery and durable Daraja callbacks."""
import sqlite3
import uuid
from flask import Blueprint, jsonify, request, session
from ..auth import customer_required
from ..db import get_db
from ..services import mpesa
from ..services.payment_records import outstanding, has_open_attempt
from ..services.payment_reconciliation import retain_callback, reconcile

mpesa_payments_bp = Blueprint('mpesa_payments', __name__, url_prefix='/api/payments/mpesa')


@mpesa_payments_bp.post('/stk-push')
@customer_required
def stk_push():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Request body must contain valid JSON'), 400
    order_id = data.get('order_id')
    if not isinstance(order_id, int) or isinstance(order_id, bool) or order_id <= 0:
        return jsonify(error='A valid order is required'), 400
    key = request.headers.get('Idempotency-Key') or data.get('request_key') or str(uuid.uuid4())
    if not isinstance(key, str) or not 8 <= len(key) <= 128:
        return jsonify(error='Invalid payment request key'), 400
    key = f"{session['user_id']}:{key}"
    db = get_db()
    attempt_id = str(uuid.uuid4())
    try:
        db.begin()
        order = db.execute('''SELECT orders.*,customers.phone_number FROM orders
            JOIN customers ON customers.customer_id=orders.customer_id
            WHERE orders.order_id=? AND orders.customer_id=?''' + (' FOR UPDATE OF orders' if db.postgres else ''),
            (order_id, session['user_id'])).fetchone()
        if not order:
            return jsonify(error='Order not found'), 404
        prior = db.execute('SELECT * FROM payment_attempts WHERE request_key=?', (key,)).fetchone()
        if prior:
            if prior['order_id'] != order_id:
                return jsonify(error='Payment key already used for a different order'), 409
            return jsonify(attempt_id=prior['attempt_id'],checkout_request_id=prior['checkout_request_id'],
                           payment_status=prior['state'],message='Existing payment attempt; no new prompt sent'), 200
        if order['order_status'] == 'cancelled' or order['payment_status'] == 'paid':
            return jsonify(error='Paid or cancelled orders cannot be paid again'), 400
        amount = outstanding(db, order)
        if amount <= 0 or amount != amount.to_integral_value():
            return jsonify(error='M-Pesa requires a positive whole-shilling outstanding balance'), 400
        if has_open_attempt(db, order_id):
            row = db.execute("SELECT checkout_request_id FROM mpesa_transactions WHERE order_id=? AND status='pending' ORDER BY transaction_id DESC LIMIT 1", (order_id,)).fetchone()
            return jsonify(error='An M-Pesa request is unresolved; do not retry payment',checkout_request_id=row['checkout_request_id'] if row else None), 409
        phone = mpesa.normalize_kenyan_phone(order['phone_number'])
        db.execute('''INSERT INTO payment_attempts(attempt_id,request_key,order_id,customer_id,amount,phone_number,state)
                      VALUES (?,?,?,?,?,?,'reserved')''', (attempt_id,key,order_id,session['user_id'],str(amount),phone))
        db.commit()
        try:
            response = mpesa.initiate_stk_push(phone_number=order['phone_number'],amount=int(amount),order_number=order['order_number'])
        except (mpesa.MpesaConfigurationError, mpesa.MpesaRejectedError) as error:
            db.execute("UPDATE payment_attempts SET state='rejected',issue=?,updated_at=CURRENT_TIMESTAMP WHERE attempt_id=?", (str(error),attempt_id))
            db.commit()
            return jsonify(error=str(error),attempt_id=attempt_id), 503
        except mpesa.MpesaError:
            db.execute("UPDATE payment_attempts SET state='unknown',issue='Initiation outcome unknown; reconcile before retry',updated_at=CURRENT_TIMESTAMP WHERE attempt_id=?", (attempt_id,))
            db.commit()
            return jsonify(error='Payment outcome is unknown. Do not send another payment; contact support.',attempt_id=attempt_id), 502
        db.begin()
        db.execute('SELECT order_id FROM orders WHERE order_id=?' + (' FOR UPDATE' if db.postgres else ''), (order_id,)).fetchone()
        db.execute('''INSERT INTO mpesa_transactions(order_id,customer_id,merchant_request_id,checkout_request_id,phone_number,amount)
                      VALUES (?,?,?,?,?,?)''', (order_id,session['user_id'],response['merchant_request_id'],response['checkout_request_id'],phone,int(amount)))
        db.execute("UPDATE payment_attempts SET state='pending',checkout_request_id=?,updated_at=CURRENT_TIMESTAMP WHERE attempt_id=?", (response['checkout_request_id'],attempt_id))
        db.execute("""UPDATE orders SET order_status='processing',payment_method='mpesa',updated_at=CURRENT_TIMESTAMP
                      WHERE order_id=? AND payment_status='unpaid' AND order_status<>'cancelled' """, (order_id,))
        db.commit()
        events = db.execute('SELECT event_id FROM payment_callback_inbox WHERE checkout_request_id=? AND processed_at IS NULL', (response['checkout_request_id'],)).fetchall()
        db.commit()
        for event in events:
            reconcile(db,response['checkout_request_id'],event['event_id'])
        return jsonify(message='M-Pesa payment request sent',attempt_id=attempt_id,
                       checkout_request_id=response['checkout_request_id'],payment_status='pending'), 202
    except mpesa.MpesaError as error:
        db.rollback()
        return jsonify(error=str(error)), 400
    except sqlite3.Error:
        db.rollback()
        return jsonify(error='Payment could not be saved; reconcile before retry',attempt_id=attempt_id), 503
    finally:
        db.rollback()


@mpesa_payments_bp.get('/status/<checkout_request_id>')
@customer_required
def payment_status(checkout_request_id):
    db = get_db()
    tx = db.execute('SELECT * FROM mpesa_transactions WHERE checkout_request_id=? AND customer_id=?', (checkout_request_id,session['user_id'])).fetchone()
    if not tx:
        return jsonify(error='Payment request not found'), 404
    db.commit()
    if tx['status'] == 'pending':
        reconcile(db,checkout_request_id)
    row = db.execute('''SELECT mt.checkout_request_id,mt.status,mt.amount,mt.mpesa_receipt_number,
                       mt.result_description,o.order_id,o.order_number,o.payment_status,o.payment_method,o.paid_at,
                       pv.issue AS reconciliation_issue,pv.timestamp_source
                       FROM mpesa_transactions mt JOIN orders o ON o.order_id=mt.order_id
                       LEFT JOIN payment_verifications pv ON pv.transaction_id=mt.transaction_id
                       WHERE mt.checkout_request_id=?''', (checkout_request_id,)).fetchone()
    return jsonify(dict(row)), 200


@mpesa_payments_bp.post('/callback')
def callback():
    if request.content_length and request.content_length > 32768:
        return jsonify(ResultCode=1,ResultDesc='Callback too large'), 413
    data = request.get_json(silent=True)
    body = data.get('Body') if isinstance(data, dict) else None
    payload = body.get('stkCallback') if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        return jsonify(ResultCode=1,ResultDesc='Invalid callback'), 400
    checkout = payload.get('CheckoutRequestID')
    if not isinstance(checkout,str) or not 1 <= len(checkout) <= 200 or not str(payload.get('ResultCode','')).isdigit():
        return jsonify(ResultCode=1,ResultDesc='Invalid checkout or result'), 400
    db = get_db()
    event_id = retain_callback(db,payload)
    message,status = reconcile(db,checkout,event_id)
    return jsonify(ResultCode=0 if status in (200,202) else 1,ResultDesc=message), status
