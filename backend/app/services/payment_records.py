"""Receipt accounting shared by payment transitions and reports.

Legacy M-Pesa payment summaries overlap STK rows; cash/bank receipts do not.
Order flags are never evidence of money. New manual receipts/refunds are immutable.
"""
from decimal import Decimal, InvalidOperation


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('999999999999'):
            raise ValueError('Invalid payment amount')
        if amount != amount.quantize(Decimal('0.01')):
            raise ValueError('Use at most two decimal places')
        return amount
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid payment amount') from None


def entries(db, order_id=None):
    where = ' WHERE order_id = ?' if order_id is not None else ''
    args = (order_id,) if order_id is not None else ()
    result, mpesa_orders = [], set()
    for row in db.execute('SELECT * FROM mpesa_transactions' + where, args).fetchall():
        if row['status'] == 'successful':
            mpesa_orders.add(row['order_id'])
            result.append(dict(order_id=row['order_id'], amount=money(row['amount']),
                               kind='receipt', occurred_at=row['completed_at'], method='mpesa'))
    for row in db.execute('SELECT * FROM payments' + where, args).fetchall():
        amount = money(row['amount_paid'])
        if not amount or row['payment_status'] not in ('paid', 'processing', 'refunded'):
            continue
        overlap = row['payment_method'] == 'mpesa' and row['order_id'] in mpesa_orders
        if not overlap:
            result.append(dict(order_id=row['order_id'], amount=amount, kind='receipt',
                               occurred_at=row['paid_at'], method=row['payment_method']))
        if row['payment_status'] == 'refunded':
            result.append(dict(order_id=row['order_id'], amount=amount, kind='refund',
                               occurred_at=row['updated_at'], method=row['payment_method']))
    for row in db.execute('SELECT * FROM payment_events' + where, args).fetchall():
        result.append(dict(order_id=row['order_id'], amount=money(row['amount']),
                           kind=row['kind'], occurred_at=row['occurred_at'], method=row['method']))
    return result


def net_received(db, order_id):
    return sum((e['amount'] if e['kind'] == 'receipt' else -e['amount']
                for e in entries(db, order_id)), Decimal(0))


def outstanding(db, order):
    if order['order_status'] == 'cancelled':
        return Decimal(0)
    return max(Decimal(0), money(order['total_amount']) - net_received(db, order['order_id']))


def has_open_attempt(db, order_id):
    return bool(db.execute("SELECT 1 FROM mpesa_transactions WHERE order_id=? AND status='pending'", (order_id,)).fetchone()
                or db.execute("SELECT 1 FROM payment_attempts WHERE order_id=? AND state IN ('reserved','unknown','pending')", (order_id,)).fetchone())


def totals(db, orders, start=None, end=None):
    """Receipt-date cash totals; order-creation-date receivable cohort."""
    from ..business_time import business_date
    from datetime import date
    start = date.fromisoformat(start) if start else date.min
    end = date.fromisoformat(end) if end else date.max
    selected = {o['order_id']:o for o in orders}
    balances, methods = {}, {}
    received = refunded = due = Decimal(0)
    for entry in entries(db):
        if entry['order_id'] not in selected:
            continue
        signed = entry['amount'] if entry['kind']=='receipt' else -entry['amount']
        balances[entry['order_id']] = balances.get(entry['order_id'],Decimal(0))+signed
        if entry['occurred_at'] and start <= business_date(entry['occurred_at']) <= end:
            if entry['kind']=='receipt':
                received += entry['amount']
            else:
                refunded += entry['amount']
            methods[entry['method']] = methods.get(entry['method'],Decimal(0))+signed
    unpaid = paid = 0
    for order in selected.values():
        if order['order_status']=='cancelled' or not start <= business_date(order['created_at']) <= end:
            continue
        balance = max(Decimal(0),money(order['total_amount'])-balances.get(order['order_id'],Decimal(0)))
        due += balance
        unpaid += balance > 0
        paid += balance == 0 and money(order['total_amount']) > 0
    def wire(value):
        return int(value) if value == value.to_integral_value() else str(value)
    return dict(payments_received=wire(received),refunds_paid=wire(refunded),net_payments=wire(received-refunded),
                outstanding_amount=wire(due),paid_orders=paid,unpaid_orders=unpaid), [
                    dict(payment_method=method,amount=wire(amount)) for method,amount in methods.items()]


def sync_order(db, order, method, occurred_at, refund=False):
    """Caller must hold the order lock. Failed callbacks never call this."""
    paid = net_received(db, order['order_id']) >= money(order['total_amount'])
    if not refund and order['payment_status'] == 'paid':
        paid = True
    db.execute("""UPDATE orders SET payment_status=?, payment_method=?,
        paid_at=CASE WHEN ? THEN COALESCE(paid_at, ?) ELSE NULL END,
        order_status=CASE WHEN order_status='cancelled' THEN 'cancelled'
                          WHEN ? AND ? <> 'bank_transfer' THEN 'completed' ELSE order_status END,
        updated_at=CURRENT_TIMESTAMP WHERE order_id=?""",
        ('paid' if paid else 'unpaid', method, paid, occurred_at, paid, method, order['order_id']))
