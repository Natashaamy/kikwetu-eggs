"""Readiness probes using ONLY disposable SQLite and mocked Daraja responses.

Run: python audit_readiness.py
No environment database URL is used, no credentials are read, and no network
requests are made. These probes document observed behavior, not release approval.
"""
import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.db import get_db
from migrate_financial_admin import migrate

SCHEMA = Path(__file__).with_name('schema_sqlite.sql').read_text(encoding='utf-8')
LEGACY = SCHEMA.split('CREATE TABLE IF NOT EXISTS farm_expenses', 1)[0]
BUSINESS_TABLES = ('customers', 'admins', 'products', 'orders', 'order_items', 'payments', 'mpesa_transactions')


def connect(path):
    return closing(sqlite3.connect(path))


def fixture(directory, name, schema=SCHEMA):
    path = Path(directory) / f'{name}.db'
    with connect(path) as db:
        db.executescript(schema)
        db.execute("INSERT INTO admins(name,username,email,password_hash) VALUES ('Audit','audit','audit@example.invalid','unused')")
        db.execute("INSERT INTO customers(name,username,phone_number) VALUES ('Audit Customer','audit-customer','0712345678')")
        db.execute("INSERT INTO products(name,unit_name,unit_price,stock_quantity) VALUES ('Eggs','tray',200,100)")
        db.execute("INSERT INTO orders(customer_id,order_number,order_status,total_amount,created_at) VALUES (1,'AUDIT-1','pending',200,'2020-01-01 10:00:00')")
        db.execute("INSERT INTO order_items(order_id,product_id,quantity,unit_price,line_total) VALUES (1,1,1,200,200)")
        db.commit()
    app = create_app({'TESTING': True, 'DATABASE_URL': None, 'DATABASE': path,
                      'SECRET_KEY': 'disposable-audit-secret', 'FRONTEND_URL': 'https://audit.invalid'})
    return path, app, app.test_client()


def login(client, role='admin'):
    with client.session_transaction() as session:
        session['user_id'], session['role'] = 1, role


def snapshot(path):
    with connect(path) as db:
        rows = {t: db.execute(f'SELECT * FROM {t} ORDER BY 1').fetchall() for t in BUSINESS_TABLES}
    return hashlib.sha256(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()


def add_payment(path, amount=100, status='processing', method='cash'):
    with connect(path) as db:
        db.execute("INSERT INTO payments(order_id,payment_method,payment_status,amount_due,amount_paid,paid_at) VALUES (1,?,?,200,?,'2020-01-01 12:00:00')", (method, status, amount))
        db.commit()


def add_attempt(path, checkout='checkout-1', status='pending', receipt=None):
    with connect(path) as db:
        db.execute("""INSERT INTO mpesa_transactions(order_id,customer_id,merchant_request_id,checkout_request_id,
            phone_number,amount,status,mpesa_receipt_number,completed_at)
            VALUES (1,1,'merchant-1',?,'254712345678',200,?,?,?)""",
            (checkout,status,receipt,'2020-01-01 12:00:00' if status=='successful' else None))
        db.commit()


def callback_payload(checkout='checkout-1', receipt='AUDITRECEIPT'):
    return {'Body': {'stkCallback': {'MerchantRequestID':'merchant-1','CheckoutRequestID':checkout,
        'ResultCode':0,'ResultDesc':'Audit only','CallbackMetadata':{'Item':[
            {'Name':'Amount','Value':200}, {'Name':'PhoneNumber','Value':254712345678},
            {'Name':'MpesaReceiptNumber','Value':receipt}, {'Name':'TransactionDate','Value':20200101150000}]}}}}


def report(client):
    login(client)
    return client.get('/api/admin/reports/summary?period=custom&from=2020-01-01&to=2030-01-01').json['summary']


def main():
    findings = {}
    with tempfile.TemporaryDirectory(prefix='kikwetu-readiness-') as directory:
        path, app, client = fixture(directory,'migration',LEGACY)
        add_payment(path)
        add_attempt(path)
        before = snapshot(path)
        migrate(app)
        migrate(app)
        after = snapshot(path)
        assert before == after
        with connect(path) as db:
            tables = ('farm_expenses','expense_audit','admin_notifications','notification_reads','payment_attempts','payment_callback_inbox','payment_verifications','payment_events','schema_migrations')
            findings['schema'] = {t: {'columns':[dict(zip(('cid','name','type','notnull','default','pk'), r)) for r in db.execute(f'PRAGMA table_info({t})')],
                'foreign_keys':db.execute(f'PRAGMA foreign_key_list({t})').fetchall(),
                'indexes':db.execute(f'PRAGMA index_list({t})').fetchall()} for t in tables}
        findings['migration_preserves_all_seven_business_tables_on_two_runs'] = before == after

        path, app, client = fixture(directory,'drift',LEGACY)
        with connect(path) as db:
            db.execute('CREATE TABLE farm_expenses(id INTEGER PRIMARY KEY,purchase_date TEXT,category TEXT)')
            db.commit()
        from app.schema_validation import SchemaMismatch
        try:
            migrate(app)
            drift_rejected = False
        except SchemaMismatch:
            drift_rejected = True
        with connect(path) as db:
            columns = [r[1] for r in db.execute('PRAGMA table_info(farm_expenses)')]
        findings['schema_drift'] = {'migration_returned_success':not drift_rejected,'incompatible_schema_rejected':drift_rejected,'required_quantity_column_present':'quantity' in columns}

        path, app, client = fixture(directory,'auth')
        endpoints = [('GET','/api/admin/expenses'),('POST','/api/admin/expenses'),
            ('PUT','/api/admin/expenses/1'),('PATCH','/api/admin/expenses/1'),('DELETE','/api/admin/expenses/1'),
            ('GET','/api/admin/notifications'),('PATCH','/api/admin/notifications/1/read'),
            ('PATCH','/api/admin/notifications/read-all'),('GET','/api/admin/reports/summary')]
        anonymous = [client.open(url,method=method,json={}).status_code for method,url in endpoints]
        login(client,'customer')
        customer = [client.open(url,method=method,json={}).status_code for method,url in endpoints]
        assert anonymous == [401]*9 and customer == [403]*9
        findings['new_endpoint_auth'] = {'endpoints':endpoints,'anonymous':anonymous,'customer':customer}
        login(client)
        with connect(path) as db:
            db.execute('UPDATE admins SET is_active=0 WHERE admin_id=1')
            db.commit()
        findings['deactivated_admin_existing_session'] = {'expense_read_status':client.get('/api/admin/expenses').status_code,
            'mark_all_read_status':client.patch('/api/admin/notifications/read-all').status_code}

        path, app, client = fixture(directory,'partial_stk')
        add_payment(path)
        login(client,'customer')
        with patch('app.routes.mpesa_payments.mpesa.initiate_stk_push',return_value={
            'merchant_request_id':'merchant-1','checkout_request_id':'checkout-1','phone_number':'254712345678'}) as initiate:
            response=client.post('/api/payments/mpesa/stk-push',json={'order_id':1})
            findings['partial_payment_stk']={'status':response.status_code,'order_total':200,'already_received':100,
                'requested_from_provider':initiate.call_args.kwargs['amount']}

        path, app, client = fixture(directory,'partial_cash')
        add_payment(path)
        login(client)
        response=client.patch('/api/orders/1/payment',json={'payment_status':'paid','payment_method':'cash'})
        findings['partial_payment_cash_confirmation']={'status':response.status_code,'reported':report(client)}

        path, app, client = fixture(directory,'mixed')
        add_payment(path)
        add_attempt(path,status='successful',receipt='AUDIT-1')
        findings['mixed_receipts']={'cash_receipt':100,'mpesa_receipt':200,'reported':report(client)}

        path, app, client = fixture(directory,'refund')
        add_payment(path,amount=200,status='refunded',method='mpesa')
        add_attempt(path,status='successful',receipt='AUDIT-1')
        findings['refunded_mpesa']={'reported':report(client)}

        path, app, client = fixture(directory,'delayed_callback')
        add_attempt(path)
        with connect(path) as db:
            db.execute("UPDATE mpesa_transactions SET created_at='2020-01-01 11:55:00'")
            db.commit()
        with patch('app.routes.mpesa_payments.mpesa.query_stk_status',return_value='0'):
            response=client.post('/api/payments/mpesa/callback',json=callback_payload())
        with connect(path) as db:
            completed=db.execute('SELECT completed_at FROM mpesa_transactions').fetchone()[0]
        findings['receipt_time']={'status':response.status_code,'provider_TransactionDate':'2020-01-01 15:00:00 EAT',
            'stored_completed_at_UTC':completed}

        path, app, client = fixture(directory,'receipt_conflict')
        add_attempt(path,checkout='other-checkout',status='successful',receipt='AUDITRECEIPT')
        add_attempt(path)
        with patch('app.routes.mpesa_payments.mpesa.query_stk_status',return_value='0'):
            response=client.post('/api/payments/mpesa/callback',json=callback_payload())
        with connect(path) as db:
            status=db.execute("SELECT status FROM mpesa_transactions WHERE checkout_request_id='checkout-1'").fetchone()[0]
        findings['receipt_conflict_acknowledged_but_not_applied']={'http_status':response.status_code,'response':response.json,'stored_status':status}

        path, app, client = fixture(directory,'missed_callback')
        add_attempt(path)
        login(client,'customer')
        with patch('app.routes.mpesa_payments.mpesa.query_stk_status',return_value='0') as query:
            response=client.get('/api/payments/mpesa/status/checkout-1')
            findings['missed_callback']={'stored_status':response.json['status'],'provider_query_called':query.called}

    print(json.dumps(findings,indent=2,default=str))


if __name__ == '__main__':
    main()
