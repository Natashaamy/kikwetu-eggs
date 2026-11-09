"""Regression tests for the production audit, using disposable data and no network."""
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.business_time import utc_now, NAIROBI, parse_timestamp
from app.db import get_db
from app.services import mpesa
from app.services.payment_reconciliation import reconcile_pending
from app.schema_validation import SchemaMismatch
from migrate_financial_admin import migrate

ROOT=Path(__file__).resolve().parents[1]


class PaymentSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.db'
        self.app=create_app({'TESTING':True,'DATABASE_URL':None,'DATABASE':self.path,'SECRET_KEY':'test'})
        self.client=self.app.test_client()
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript((ROOT/'schema_sqlite.sql').read_text())
            db.execute("INSERT INTO admins(name,username,email,password_hash) VALUES ('Admin','admin','a@example.test','unused')")
            db.execute("INSERT INTO customers(name,phone_number) VALUES ('Customer','0712345678')")
            db.execute("INSERT INTO products(name,unit_name,unit_price,stock_quantity) VALUES ('Eggs','tray',200,20)")
            db.execute("INSERT INTO orders(customer_id,order_number,order_status,total_amount) VALUES (1,'ORD-1','pending',200)")
            db.execute('INSERT INTO order_items(order_id,product_id,quantity,unit_price,line_total) VALUES (1,1,1,200,200)')
            db.commit()
        self.login('customer')
        self.query=patch('app.services.mpesa.query_stk_status',return_value='0').start()
        self.addCleanup(patch.stopall)

    def sql(self,sql,args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory=sqlite3.Row
            result=db.execute(sql,args).fetchall()
            db.commit()
            return [dict(r) for r in result]

    def login(self,role):
        with self.client.session_transaction() as session:
            session['role'],session['user_id']=role,1

    def seed(self,checkout='checkout-1',amount=200,order=1):
        self.sql("INSERT INTO mpesa_transactions(order_id,customer_id,merchant_request_id,checkout_request_id,phone_number,amount) VALUES (?,1,'merchant-1',?,'254712345678',?)",(order,checkout,amount))

    def payload(self,checkout='checkout-1',amount=200,receipt='RECEIPT1',timestamp=None):
        return {'Body':{'stkCallback':{'CheckoutRequestID':checkout,'MerchantRequestID':'merchant-1','ResultCode':0,
            'CallbackMetadata':{'Item':[{'Name':'Amount','Value':amount},{'Name':'PhoneNumber','Value':254712345678},
                {'Name':'MpesaReceiptNumber','Value':receipt},
                {'Name':'TransactionDate','Value':timestamp or utc_now().astimezone(NAIROBI).strftime('%Y%m%d%H%M%S')}]}}}}

    def callback(self,**kwargs):
        return self.client.post('/api/payments/mpesa/callback',json=self.payload(**kwargs))

    def cash(self,amount=100,status='processing',method='cash'):
        self.sql("INSERT INTO payments(order_id,payment_method,payment_status,amount_due,amount_paid,paid_at) VALUES (1,?,?,200,?,CURRENT_TIMESTAMP)",(method,status,amount))

    def summary(self):
        self.login('admin')
        result=self.client.get('/api/admin/reports/summary?period=custom&from=2000-01-01&to=2100-01-01')
        self.assertEqual(result.status_code,200,result.json)
        return {k:Decimal(v) for k,v in result.json['summary'].items()}

    def initiation(self):
        return patch('app.services.mpesa.initiate_stk_push',return_value={'merchant_request_id':'merchant-1','checkout_request_id':'checkout-1','phone_number':'254712345678'})

    def test_partial_payment_only_charges_remaining_balance(self):
        self.cash()
        with self.initiation() as provider:
            response=self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1})
        self.assertEqual(response.status_code,202)
        self.assertEqual(provider.call_args.kwargs['amount'],100)
        self.assertEqual(self.sql('SELECT amount FROM mpesa_transactions')[0]['amount'],100)

    def test_idempotency_retry_does_not_initiate_twice(self):
        with self.initiation() as provider:
            first=self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1,'request_key':'stable-key-123'})
            second=self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1,'request_key':'stable-key-123'})
        self.assertEqual(first.status_code,202)
        self.assertEqual(second.status_code,200)
        self.assertEqual(first.json['attempt_id'],second.json['attempt_id'])
        self.assertEqual(provider.call_count,1)

    def test_intent_commits_before_network_and_timeout_blocks_retry(self):
        def timeout(**kwargs):
            self.assertEqual(self.sql('SELECT state FROM payment_attempts')[0]['state'],'reserved')
            raise mpesa.MpesaError('Timeout')
        with patch('app.services.mpesa.initiate_stk_push',side_effect=timeout):
            self.assertEqual(self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1}).status_code,502)
        self.assertEqual(self.sql('SELECT state FROM payment_attempts')[0]['state'],'unknown')
        self.assertEqual(self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1}).status_code,409)
        self.assertEqual(self.client.patch('/api/customer/orders/1/payment-method',json={'payment_method':'cash'}).status_code,409)

    def test_explicit_rejection_allows_new_attempt(self):
        with patch('app.services.mpesa.initiate_stk_push',side_effect=mpesa.MpesaRejectedError('Rejected')):
            self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1})
        with self.initiation():
            self.assertEqual(self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1}).status_code,202)

    def test_acceptance_never_marks_paid(self):
        with self.initiation():
            self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1})
        self.assertEqual(self.sql('SELECT payment_status FROM orders')[0]['payment_status'],'unpaid')

    def test_missed_callback_recovers_via_provider_query_without_invented_receipt(self):
        self.seed()
        response=self.client.get('/api/payments/mpesa/status/checkout-1')
        self.assertEqual(response.json['payment_status'],'paid')
        self.assertIsNone(response.json['mpesa_receipt_number'])
        self.assertEqual(response.json['timestamp_source'],'verification_time')
        self.query.assert_called_once_with('checkout-1')

    def test_status_outage_stays_pending_and_queries_are_throttled(self):
        self.seed()
        self.query.side_effect=mpesa.MpesaError('Outage')
        for _ in range(2):
            self.assertEqual(self.client.get('/api/payments/mpesa/status/checkout-1').json['status'],'pending')
        self.assertEqual(self.query.call_count,1)

    def test_callback_outage_is_durable_and_worker_retries(self):
        self.seed()
        self.query.side_effect=mpesa.MpesaError('Outage')
        self.assertEqual(self.callback().status_code,503)
        self.assertIsNone(self.sql('SELECT processed_at FROM payment_callback_inbox')[0]['processed_at'])
        self.query.side_effect=None
        with self.app.app_context():
            reconcile_pending(get_db())
        self.assertEqual(self.sql('SELECT status FROM mpesa_transactions')[0]['status'],'successful')
        self.assertIsNotNone(self.sql('SELECT processed_at FROM payment_callback_inbox')[0]['processed_at'])

    def test_early_callback_replayed_after_initiation_registered(self):
        self.assertEqual(self.callback().status_code,202)
        with self.initiation():
            self.assertEqual(self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1}).status_code,202)
        self.assertEqual(self.sql('SELECT payment_status FROM orders')[0]['payment_status'],'paid')

    def test_duplicate_callbacks_count_once_even_concurrently(self):
        self.seed()
        payload=self.payload()
        def call(_):
            return self.app.test_client().post('/api/payments/mpesa/callback',json=payload).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(call,range(2))),[200,200])
        self.assertEqual(len(self.sql('SELECT * FROM payment_callback_inbox')),1)
        self.assertEqual(self.summary()['confirmed_payments_received'],200)

    def test_receipt_conflict_is_not_silently_acknowledged(self):
        self.seed()
        self.assertEqual(self.callback().status_code,200)
        self.sql("INSERT INTO orders(customer_id,order_number,order_status,total_amount) VALUES (1,'ORD-2','pending',200)")
        self.seed('checkout-2',order=2)
        self.assertEqual(self.callback(checkout='checkout-2').status_code,409)
        self.assertEqual(self.sql("SELECT status FROM mpesa_transactions WHERE checkout_request_id='checkout-2'")[0]['status'],'pending')
        self.assertIn('conflict',self.sql("SELECT issue FROM payment_verifications WHERE transaction_id=2")[0]['issue'])

    def test_later_failure_and_cash_cannot_overwrite_success(self):
        self.seed()
        self.callback()
        self.query.return_value='1032'
        payload=self.payload();payload['Body']['stkCallback']['ResultCode']=1032
        self.client.post('/api/payments/mpesa/callback',json=payload)
        self.assertEqual(self.client.patch('/api/customer/orders/1/payment-method',json={'payment_method':'cash'}).status_code,400)
        self.assertEqual(self.sql('SELECT payment_status FROM orders')[0]['payment_status'],'paid')

    def test_cash_vs_callback_concurrency_preserves_success(self):
        self.seed()
        def cash():
            return self.client.patch('/api/customer/orders/1/payment-method',json={'payment_method':'cash'}).status_code
        def callback():
            return self.app.test_client().post('/api/payments/mpesa/callback',json=self.payload()).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            a,b=pool.submit(cash),pool.submit(callback)
            self.assertIn(a.result(),(400,409));self.assertEqual(b.result(),200)
        self.assertEqual(self.sql('SELECT payment_status FROM orders')[0]['payment_status'],'paid')

    def test_failed_attempt_can_retry_and_success_can_arrive_late(self):
        self.seed();self.query.return_value='1032'
        payload=self.payload();payload['Body']['stkCallback']['ResultCode']=1032
        self.assertEqual(self.client.post('/api/payments/mpesa/callback',json=payload).status_code,200)
        self.query.return_value='0'
        self.assertEqual(self.callback().status_code,200)
        self.assertEqual(self.sql('SELECT payment_status FROM orders')[0]['payment_status'],'paid')

    def test_mixed_receipts_are_added_and_partial_completion_is_correct(self):
        self.cash();self.seed(amount=100)
        self.assertEqual(self.callback(amount=100).status_code,200)
        result=self.summary()
        self.assertEqual(result['confirmed_payments_received'],200)
        self.assertEqual(result['unpaid_orders_amount'],0)

    def test_manual_completion_adds_balance_and_retry_is_idempotent(self):
        self.cash();self.login('admin')
        for _ in range(2):
            self.assertEqual(self.client.patch('/api/orders/1/payment',json={'payment_status':'paid','payment_method':'cash'}).status_code,200)
        self.assertEqual(self.sql('SELECT amount FROM payment_events')[0]['amount'],100)
        self.assertEqual(self.summary()['confirmed_payments_received'],200)
        self.assertEqual(self.summary()['unpaid_orders_amount'],0)

    def test_explicit_decimal_partial_receipt_and_refund(self):
        self.login('admin')
        response=self.client.patch('/api/orders/1/payment',json={'payment_status':'paid','payment_method':'cash','amount':'50.25','idempotency_key':'partial-1'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['payment_status'],'unpaid')
        refund={'payment_method':'cash','amount':'10.10','reference':'cash-return-1','idempotency_key':'refund-1'}
        for _ in range(2):
            self.assertEqual(self.client.post('/api/orders/1/refunds',json=refund).status_code,200)
        result=self.summary()
        self.assertEqual(result['net_cash_balance'],Decimal('40.15'))
        self.assertEqual(result['unpaid_orders_amount'],Decimal('159.85'))
        self.assertEqual(result['refunds_paid'],Decimal('10.10'))

    def test_legacy_refunded_mpesa_is_not_net_income(self):
        self.seed();self.callback();self.cash(200,'refunded','mpesa')
        result=self.summary()
        self.assertEqual(result['confirmed_payments_received'],200)
        self.assertEqual(result['refunds_paid'],200)
        self.assertEqual(result['net_cash_balance'],0)

    def test_overlapping_mpesa_summary_does_not_double_count(self):
        self.seed();self.callback();self.cash(200,'paid','mpesa')
        self.assertEqual(self.summary()['confirmed_payments_received'],200)

    def test_cancelled_order_receipt_retained_without_receivable(self):
        self.seed();self.sql("UPDATE orders SET order_status='cancelled'")
        self.callback()
        result=self.summary()
        self.assertEqual(result['confirmed_payments_received'],200)
        self.assertEqual(result['paid_orders_amount'],0)
        self.assertEqual(result['unpaid_orders_amount'],0)
        self.assertEqual(self.sql('SELECT order_status FROM orders')[0]['order_status'],'cancelled')

    def test_flags_alone_are_not_receipts(self):
        self.sql("UPDATE orders SET payment_status='paid',paid_at=CURRENT_TIMESTAMP")
        self.assertEqual(self.summary()['confirmed_payments_received'],0)

    def test_admin_revocation_clears_existing_cookie_on_all_route_families(self):
        self.sql('UPDATE admins SET is_active=0')
        for route in ('/api/orders','/api/products','/api/customers','/api/dashboard','/api/admin/expenses','/api/admin/notifications','/api/admin/reports/summary'):
            self.login('admin')
            self.assertEqual(self.client.get(route).status_code,403,route)
            with self.client.session_transaction() as session:
                self.assertNotIn('user_id',session)

    def test_deleted_admin_session_rejected(self):
        self.login('admin');self.sql('DELETE FROM admins')
        self.assertEqual(self.client.get('/api/orders').status_code,403)

    def test_provider_nairobi_time_separate_from_callback_receipt(self):
        self.seed()
        self.sql("UPDATE mpesa_transactions SET created_at='2025-12-31 20:55:00'")
        self.assertEqual(self.callback(timestamp='20260101000100').status_code,200)
        row=self.sql('SELECT * FROM payment_verifications')[0]
        self.assertEqual(parse_timestamp(row['provider_paid_at']).isoformat(),'2025-12-31T21:01:00+00:00')
        self.assertNotEqual(row['provider_paid_at'],row['callback_received_at'])
        self.login('admin')
        jan=self.client.get('/api/admin/reports/summary?period=custom&from=2026-01-01&to=2026-01-01').json
        dec=self.client.get('/api/admin/reports/summary?period=custom&from=2025-12-31&to=2025-12-31').json
        self.assertEqual(Decimal(jan['summary']['confirmed_payments_received']),200)
        self.assertEqual(Decimal(dec['summary']['confirmed_payments_received']),0)

    def test_malformed_and_inconsistent_timestamps_use_flagged_fallback(self):
        for value in ('invalid','20200101150000','20990101000000'):
            with self.subTest(value=value):
                self.sql('DELETE FROM payment_callback_inbox');self.sql('DELETE FROM payment_verifications');self.sql('DELETE FROM mpesa_transactions')
                self.seed();self.callback(timestamp=value)
                row=self.sql('SELECT * FROM payment_verifications')[0]
                self.assertEqual(row['timestamp_source'],'verification_time')
                self.assertIsNone(row['provider_paid_at']);self.assertIsNotNone(row['issue'])

    def test_query_success_later_callback_enriches_without_double_count(self):
        self.seed();self.client.get('/api/payments/mpesa/status/checkout-1')
        self.callback()
        self.assertEqual(self.sql('SELECT mpesa_receipt_number FROM mpesa_transactions')[0]['mpesa_receipt_number'],'RECEIPT1')
        self.assertEqual(self.summary()['confirmed_payments_received'],200)

    def test_migration_preserves_rows_and_repeats(self):
        self.cash();self.seed()
        tables=('customers','admins','products','orders','order_items','payments','mpesa_transactions')
        before={t:self.sql('SELECT * FROM '+t) for t in tables}
        migrate(self.app);migrate(self.app)
        self.assertEqual(before,{t:self.sql('SELECT * FROM '+t) for t in tables})

    def test_migration_rejects_missing_column_and_rolls_back(self):
        self.sql('DROP TABLE farm_expenses')
        self.sql('CREATE TABLE farm_expenses(id INTEGER PRIMARY KEY,category TEXT,purchase_date TEXT)')
        with self.assertRaisesRegex(SchemaMismatch,'farm_expenses'):
            migrate(self.app)
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM orders')[0]['n'],1)

    def test_migration_rejects_removed_unique_constraint(self):
        self.sql('DROP TABLE payment_attempts')
        self.sql('''CREATE TABLE payment_attempts(attempt_id TEXT PRIMARY KEY,request_key TEXT NOT NULL,
                    order_id BIGINT NOT NULL REFERENCES orders(order_id),customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
                    amount NUMERIC(16,2) NOT NULL CHECK(amount>0),phone_number TEXT NOT NULL,state TEXT NOT NULL,
                    checkout_request_id TEXT UNIQUE,issue TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        with self.assertRaises(SchemaMismatch):
            migrate(self.app)

    def test_migration_checksum_change_is_rejected(self):
        migrate(self.app)
        self.sql("UPDATE schema_migrations SET checksum='tampered'")
        with self.assertRaisesRegex(SchemaMismatch,'checksum'):
            migrate(self.app)

    def test_receipt_conflict_cannot_be_bypassed_by_status_query(self):
        self.seed();self.callback()
        self.sql("INSERT INTO orders(customer_id,order_number,order_status,total_amount) VALUES (1,'ORD-2','pending',200)")
        self.seed('checkout-2',order=2)
        self.callback(checkout='checkout-2')
        self.assertEqual(self.client.get('/api/payments/mpesa/status/checkout-2').json['status'],'pending')

    def test_manual_overpayment_and_excess_refund_rejected(self):
        self.cash();self.login('admin')
        self.assertEqual(self.client.patch('/api/orders/1/payment',json={'payment_status':'paid','payment_method':'cash','amount':'101','idempotency_key':'overpay'}).status_code,400)
        self.assertEqual(self.client.post('/api/orders/1/refunds',json={'payment_method':'cash','amount':'101','idempotency_key':'refund','reference':'ref'}).status_code,400)

    def test_fractional_outstanding_is_not_rounded_up_for_mpesa(self):
        self.sql("INSERT INTO payment_events(order_id,kind,amount,method,idempotency_key,reference,occurred_at) VALUES (1,'receipt',10.25,'cash','fraction','cash',CURRENT_TIMESTAMP)")
        with self.initiation() as provider:
            self.assertEqual(self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1}).status_code,400)
            provider.assert_not_called()

    def test_confirmed_failed_attempt_allows_retry(self):
        self.seed();self.query.return_value='1032'
        payload=self.payload();payload['Body']['stkCallback']['ResultCode']=1032
        self.client.post('/api/payments/mpesa/callback',json=payload)
        with patch('app.services.mpesa.initiate_stk_push',return_value={'checkout_request_id':'checkout-2','merchant_request_id':'m2','phone_number':'254712345678'}):
            self.assertEqual(self.client.post('/api/payments/mpesa/stk-push',json={'order_id':1}).status_code,202)

    def test_stale_reservation_blocks_admin_cancel_and_item_changes(self):
        self.sql("INSERT INTO payment_attempts(attempt_id,request_key,order_id,customer_id,amount,phone_number,state) VALUES ('a','key',1,1,200,'254712345678','reserved')")
        self.login('admin')
        self.assertEqual(self.client.patch('/api/orders/1',json={'order_status':'cancelled'}).status_code,409)
        self.assertEqual(self.client.post('/api/orders/1/items',json={'product_id':1,'quantity':1}).status_code,409)

    def test_dashboards_and_legacy_report_use_partial_receipts(self):
        self.cash()
        self.assertEqual(self.client.get('/api/customer/dashboard').json['amount_outstanding'],100)
        self.login('admin')
        for route in ('/api/dashboard','/api/admin/reports'):
            response=self.client.get(route).json
            summary=response.get('summary',response)
            self.assertEqual(summary['payments_received'],100)
            self.assertEqual(summary['outstanding_amount'],100)

    def test_migration_adds_known_missing_indexes(self):
        self.sql('DROP INDEX idx_expense_audit_expense')
        migrate(self.app)
        self.assertTrue(self.sql("SELECT name FROM sqlite_master WHERE name='idx_expense_audit_expense'"))

    def test_migration_rejects_missing_legacy_table(self):
        self.sql('DROP TABLE products')
        with self.assertRaisesRegex(SchemaMismatch,'products'):
            migrate(self.app)

    def test_environment_selection_and_invalid_environment_fail_closed(self):
        env={name:'test' for name in ('MPESA_CONSUMER_KEY','MPESA_CONSUMER_SECRET','MPESA_SHORTCODE','MPESA_PASSKEY')}
        env['MPESA_CALLBACK_URL']='https://example.test/callback'
        with patch.dict('os.environ',{**env,'MPESA_ENV':'production'},clear=True):
            self.assertEqual(mpesa._settings()['BASE_URL'],'https://api.safaricom.co.ke')
        with patch.dict('os.environ',{**env,'MPESA_ENV':'sandbox'},clear=True):
            self.assertEqual(mpesa._settings()['BASE_URL'],'https://sandbox.safaricom.co.ke')
        with patch.dict('os.environ',{**env,'MPESA_ENV':'invalid'},clear=True):
            with self.assertRaises(mpesa.MpesaConfigurationError):
                mpesa._settings()

    def test_production_missing_config_refuses_to_start(self):
        with patch.dict('os.environ',{'APP_ENV':'production'},clear=True):
            with self.assertRaisesRegex(RuntimeError,'DATABASE_URL'):
                create_app()

    def test_receipt_after_refund_needs_new_key_not_stale_success(self):
        self.login('admin')
        complete={'payment_status':'paid','payment_method':'cash'}
        self.assertEqual(self.client.patch('/api/orders/1/payment',json=complete).status_code,200)
        self.assertEqual(self.client.post('/api/orders/1/refunds',json={'payment_method':'cash','amount':100,'idempotency_key':'refund','reference':'returned-cash'}).status_code,200)
        self.assertEqual(self.client.patch('/api/orders/1/payment',json=complete).status_code,409)
        self.assertEqual(self.client.patch('/api/orders/1/payment',json={**complete,'idempotency_key':'new-receipt'}).status_code,200)
        self.assertEqual(self.summary()['net_cash_balance'],200)
