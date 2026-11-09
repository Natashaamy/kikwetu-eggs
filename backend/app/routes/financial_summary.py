"""Cash overview from recorded receipts/refunds and Nairobi business dates."""
from decimal import Decimal
from flask import jsonify, request
from .reports import reports_bp
from .farm_expenses import expense_totals
from ..db import get_db
from ..business_time import business_date, period_dates
from ..services.payment_records import entries, money


@reports_bp.get('/summary')
def financial_summary():
    try:
        start,end=period_dates(request.args.get('period','month'),request.args.get('from'),request.args.get('to'))
    except ValueError as error:
        return jsonify(error=str(error)),400
    db=get_db()
    orders={r['order_id']:r for r in db.execute('SELECT * FROM orders').fetchall()}
    in_period=lambda value: bool(value) and start <= business_date(value) <= end
    received=refunded=paid=outstanding=Decimal(0)
    balances={}
    undated=0
    for entry in entries(db):
        amount=entry['amount'] if entry['kind']=='receipt' else -entry['amount']
        balances[entry['order_id']]=balances.get(entry['order_id'],Decimal(0))+amount
        if not entry['occurred_at']:
            undated+=1
        elif in_period(entry['occurred_at']):
            if entry['kind']=='receipt':
                received+=entry['amount']
            else:
                refunded+=entry['amount']
            if orders[entry['order_id']]['order_status']!='cancelled':
                paid+=amount
    for order in orders.values():
        if order['order_status']!='cancelled' and in_period(order['created_at']):
            outstanding+=max(Decimal(0),money(order['total_amount'])-balances.get(order['order_id'],Decimal(0)))
    expenses=expense_totals(db,start,end)
    return jsonify(period={'from':str(start),'to':str(end)},undated_payment_records=undated,summary={
        'paid_orders_amount':str(paid),'unpaid_orders_amount':str(outstanding),
        'confirmed_payments_received':str(received),'refunds_paid':str(refunded),
        'feed_expenses':expenses['feed'],'medicine_expenses':expenses['medicine'],
        'total_expenses':expenses['total'],
        'net_cash_balance':str(received-refunded-Decimal(expenses['total']))})
