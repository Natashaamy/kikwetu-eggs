"""Regression coverage for financial administration without live business data."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import date
from decimal import Decimal
from app import create_app
from app.business_time import business_date, period_dates, utc_bounds


class FinancialAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.db'
        self.schema = (Path(__file__).resolve().parents[1] / 'schema_sqlite.sql').read_text()
        with self.db() as db:
            db.executescript(self.schema)
            db.execute("INSERT INTO admins(name,username,email,password_hash) VALUES ('Admin','admin','admin@example.test','unused')")
            db.execute("INSERT INTO admins(name,username,email,password_hash) VALUES ('Admin2','admin2','admin2@example.test','unused')")
            db.execute("INSERT INTO customers(name,phone_number) VALUES ('Customer','0712345678')")
            db.execute("INSERT INTO products(name,unit_name,unit_price,stock_quantity) VALUES ('Eggs','tray',500,100)")
        self.app = create_app({'TESTING': True, 'DATABASE_URL': None, 'DATABASE': self.path, 'SECRET_KEY': 'test'})
        self.client = self.app.test_client()
        self.login('admin')

    def db(self):
        return sqlite3.connect(self.path)

    def login(self, role, user_id=1):
        with self.client.session_transaction() as s:
            s['role'], s['user_id'] = role, user_id

    def expense(self, **changes):
        return dict(category='feed', item_name='Layers Mash', quantity='50', unit='kg', unit_price='65', purchase_date='2026-01-01', notes='', submission_key='unique-submission-0001', **changes)

    def summary(self, start='2026-01-01', end='2026-01-31'):
        response = self.client.get(f'/api/admin/reports/summary?period=custom&from={start}&to={end}')
        self.assertEqual(response.status_code, 200)
        return {k: Decimal(v) for k,v in response.json['summary'].items()}

    def test_expense_lifecycle_idempotency_and_audit(self):
        payload = self.expense()
        response = self.client.post('/api/admin/expenses', json={**payload, 'total_amount': 1})
        self.assertEqual(response.status_code, 201, response.json)
        expense_id = response.json['id']
        self.assertEqual(self.summary()['feed_expenses'], 3250)
        self.assertEqual(self.client.post('/api/admin/expenses', json=payload).status_code, 200)
        self.assertEqual(self.client.post('/api/admin/expenses', json={**payload, 'quantity':'51'}).status_code, 409)
        self.assertEqual(self.client.put(f'/api/admin/expenses/{expense_id}', json={**payload, 'quantity':'0.125', 'unit_price':'65.25'}).status_code, 200)
        self.assertEqual(self.summary()['feed_expenses'], Decimal('8.16'))
        self.assertEqual(self.client.delete(f'/api/admin/expenses/{expense_id}').status_code, 200)
        self.assertEqual(self.summary()['total_expenses'], 0)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM farm_expenses').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM expense_audit').fetchone()[0], 3)

    def test_medicine_and_invalid_expenses(self):
        payload = {**self.expense(), 'category':'medicine', 'item_name':'Vitamins', 'unit':'bottles','quantity':'3','unit_price':'850'}
        self.assertEqual(self.client.post('/api/admin/expenses', json=payload).status_code, 201)
        self.assertEqual(self.summary()['medicine_expenses'], 2550)
        for changes in ({'quantity':'-1'}, {'quantity':'NaN'}, {'unit_price':'Infinity'}, {'unit_price':'-1'}, {'purchase_date':'2026-02-30'}, {'purchase_date':'9999-01-01'}, {'category':'other'}, {'quantity':'0'}, {'unit_price':'0.001'}, {'notes':[]}, {'item_name':''}):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post('/api/admin/expenses', json={**payload, **changes}).status_code, 400)

    def test_permissions_and_invalid_filters(self):
        for endpoint in ('expenses', 'notifications', 'reports/summary'):
            self.login('customer')
            self.assertEqual(self.client.get('/api/admin/'+endpoint).status_code, 403)
        self.assertEqual(self.client.post('/api/admin/expenses', json=self.expense()).status_code,403)
        self.assertEqual(self.client.patch('/api/admin/notifications/read-all').status_code,403)
        self.login('admin')
        self.assertEqual(self.client.get('/api/admin/reports/summary?period=custom&from=2026-02-02&to=2026-01-01').status_code,400)
        self.assertEqual(self.client.get('/api/admin/expenses?from=bad').status_code,400)

    def test_nairobi_year_month_and_week_boundaries(self):
        self.assertEqual(business_date('2025-12-31 21:00:00'), date(2026,1,1))
        self.assertEqual(business_date('2025-12-31T23:59:00+03:00'), date(2025,12,31))
        self.assertEqual(period_dates('week', today=date(2026,1,1)), (date(2025,12,29),date(2026,1,4)))
        self.assertEqual(period_dates('month', today=date(2024,2,20)), (date(2024,2,1),date(2024,2,29)))
        self.assertEqual(utc_bounds(date(2026,1,1),date(2026,1,1))[0].isoformat(), '2025-12-31T21:00:00+00:00')

    def test_reports_payment_dates_partial_cancelled_and_no_double_count(self):
        with self.db() as db:
            for number,status,payment,total,created,paid in [
                ('paid','completed','paid',500,'2025-12-01','2025-12-31 21:00:00'),
                ('partial','pending','unpaid',500,'2026-01-02',None),
                ('cancel','cancelled','unpaid',900,'2026-01-03',None),
                ('cancel-paid','cancelled','paid',100,'2026-01-03','2026-01-03')]:
                db.execute('INSERT INTO orders(customer_id,order_number,order_status,payment_status,total_amount,created_at,paid_at) VALUES (1,?,?,?,?,?,?)',(number,status,payment,total,created,paid))
            db.execute("INSERT INTO payments(order_id,payment_method,payment_status,amount_due,amount_paid,paid_at) VALUES (2,'cash','processing',500,125,'2026-01-02')")
            db.execute("INSERT INTO mpesa_transactions(order_id,customer_id,checkout_request_id,phone_number,amount,status,completed_at) VALUES (1,1,'c','254712345678',500,'successful','2025-12-31 21:00:00')")
            db.execute("INSERT INTO payments(order_id,payment_method,payment_status,amount_due,amount_paid,paid_at) VALUES (4,'cash','paid',100,100,'2026-01-03')")
        result = self.summary()
        self.assertEqual(result['paid_orders_amount'],625)
        self.assertEqual(result['unpaid_orders_amount'],375)
        self.assertEqual(result['confirmed_payments_received'],725)
        self.assertEqual(result['net_cash_balance'],725)
        self.assertEqual(self.summary('2025-11-01','2025-11-30')['net_cash_balance'],0)

    def test_cancelled_order_hidden_history_retained_and_notifications_persist(self):
        self.login('customer')
        created = self.client.post('/api/customer-orders',json={'product_id':1,'quantity':2})
        self.assertEqual(created.status_code,201)
        order_id=created.json['order_id']
        self.assertEqual(self.client.patch(f'/api/customer/orders/{order_id}/cancel').status_code,200)
        for _ in range(2):
            self.assertEqual(self.client.get('/api/customer/orders').json['orders'],[])
            self.assertEqual(self.client.get('/api/customer/dashboard').json['amount_outstanding'],0)
        self.login('admin')
        self.assertEqual(self.client.get('/api/orders').json['orders'][0]['order_status'],'cancelled')
        self.assertEqual(self.client.delete(f'/api/orders/{order_id}').status_code,409)
        notifications=self.client.get('/api/admin/notifications').json
        self.assertEqual(notifications['unread_count'],2)
        self.client.patch(f"/api/admin/notifications/{notifications['notifications'][0]['id']}/read")
        self.assertEqual(self.client.get('/api/admin/notifications').json['unread_count'],1)
        self.client.patch('/api/admin/notifications/read-all')
        self.assertEqual(self.client.get('/api/admin/notifications').json['unread_count'],0)
        self.login('admin',2)
        self.assertEqual(self.client.get('/api/admin/notifications').json['unread_count'],2)

    def test_schema_reapplication_preserves_data(self):
        self.client.post('/api/admin/expenses',json=self.expense())
        with self.db() as db:
            db.executescript(self.schema)
            db.executescript(self.schema)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM farm_expenses').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM customers').fetchone()[0],1)
        from migrate_financial_admin import migrate
        migrate(self.app)
        migrate(self.app)
        self.assertEqual(self.summary()['feed_expenses'],3250)

    def test_partial_payment_blocks_cancellation_and_client_total_override(self):
        with self.db() as db:
            db.execute("INSERT INTO orders(customer_id,order_number,order_status,total_amount) VALUES (1,'partial','pending',500)")
            db.execute("INSERT INTO payments(order_id,payment_method,payment_status,amount_due,amount_paid) VALUES (1,'cash','processing',500,100)")
        self.assertEqual(self.client.patch('/api/orders/1',json={'total_amount':1}).status_code,400)
        self.assertEqual(self.client.patch('/api/orders/1',json={'order_status':'cancelled'}).status_code,400)
        self.login('customer')
        self.assertEqual(self.client.patch('/api/customer/orders/1/cancel').status_code,400)

    def test_active_product_count_changes(self):
        self.assertEqual(self.client.get('/api/dashboard').json['active_products'],1)
        with self.db() as db:
            db.execute("INSERT INTO products(name,unit_name,unit_price) VALUES ('New','tray',500)")
        self.assertEqual(self.client.get('/api/dashboard').json['active_products'],2)
        with self.db() as db:
            db.execute('UPDATE products SET is_active=0 WHERE product_id=2')
        self.assertEqual(self.client.get('/api/dashboard').json['active_products'],1)
