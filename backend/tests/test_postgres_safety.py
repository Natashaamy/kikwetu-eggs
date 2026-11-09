"""Opt-in integration tests. Requires an explicitly isolated PostgreSQL database.

Set PGTEST_DATABASE_URL securely and PGTEST_CONFIRM_ISOLATED=1. Never use production.
Each test creates/drops only its own random kikwetu_test_* schema.
"""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app import create_app
from app.db import get_db, DatabaseAdapter
from app.schema_validation import scripts, SchemaMismatch
from migrate_financial_admin import migrate
import test_payment_safety as regression


@unittest.skipUnless(os.environ.get('PGTEST_DATABASE_URL') and os.environ.get('PGTEST_CONFIRM_ISOLATED')=='1',
                     'Isolated PostgreSQL staging not configured (PGTEST_DATABASE_URL / PGTEST_CONFIRM_ISOLATED)')
class PostgresSafetyTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        self.schema='kikwetu_test_'+uuid.uuid4().hex
        self.url=os.environ['PGTEST_DATABASE_URL']
        original_connect=psycopg.connect
        with original_connect(self.url,autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        def cleanup_schema():
            # Name is generated here, never obtained from an external configuration.
            assert self.schema.startswith('kikwetu_test_') and len(self.schema)==45
            with original_connect(self.url,autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.addCleanup(cleanup_schema)
        def isolated_connect(*args,**kwargs):
            connection=original_connect(*args,**kwargs)
            connection.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(self.schema)))
            connection.commit()
            return connection
        patcher=patch('psycopg.connect',side_effect=isolated_connect)
        patcher.start();self.addCleanup(patcher.stop)
        self.app=create_app({'TESTING':True,'DATABASE_URL':self.url,'SECRET_KEY':'test'})
        self.client=self.app.test_client()
        with self.app.app_context():
            db=get_db()
            for _,script in scripts(True):
                db.executescript(script)
            db.execute("INSERT INTO admins(name,username,email,password_hash) VALUES ('Admin','admin','a@example.test','unused')")
            db.execute("INSERT INTO customers(name,phone_number) VALUES ('Customer','0712345678')")
            db.execute("INSERT INTO products(name,unit_name,unit_price,stock_quantity) VALUES ('Eggs','tray',200,20)")
            db.execute("INSERT INTO orders(customer_id,order_number,order_status,total_amount) VALUES (1,'ORD-1','pending',200)")
            db.execute('INSERT INTO order_items(order_id,product_id,quantity,unit_price,line_total) VALUES (1,1,1,200,200)')
            db.commit()
        self.login('customer')
        verifier=patch('app.services.mpesa.query_stk_status',return_value='0')
        self.query=verifier.start();self.addCleanup(verifier.stop)

    login=regression.PaymentSafetyTests.login
    seed=regression.PaymentSafetyTests.seed
    payload=regression.PaymentSafetyTests.payload
    callback=regression.PaymentSafetyTests.callback
    cash=regression.PaymentSafetyTests.cash
    summary=regression.PaymentSafetyTests.summary

    def sql(self,statement,args=()):
        with self.app.app_context():
            db=get_db()
            cursor=db.execute(statement,args)
            result=cursor.fetchall() if cursor._cursor.description else []
            db.commit()
            return result

    test_migration_preserves_rows_and_repeats=regression.PaymentSafetyTests.test_migration_preserves_rows_and_repeats
    test_cash_vs_callback_concurrency_preserves_success=regression.PaymentSafetyTests.test_cash_vs_callback_concurrency_preserves_success
    test_duplicate_callbacks_count_once_even_concurrently=regression.PaymentSafetyTests.test_duplicate_callbacks_count_once_even_concurrently

    def test_migration_rejects_column_drift(self):
        self.sql('ALTER TABLE farm_expenses DROP COLUMN quantity')
        with self.assertRaisesRegex(SchemaMismatch,'quantity'):
            migrate(self.app)

    def test_failed_migration_rolls_back_all_new_tables(self):
        # Build a legacy-only isolated fixture, then inject a mid-DDL failure.
        names=['payment_events','payment_verifications','payment_callback_inbox','payment_attempts',
               'notification_reads','admin_notifications','expense_audit','farm_expenses']
        for name in names:
            self.sql('DROP TABLE '+name)
        original=DatabaseAdapter.execute
        def fail_after_first_table(db,statement,parameters=()):
            if statement.strip().startswith('CREATE TABLE IF NOT EXISTS expense_audit'):
                raise RuntimeError('Injected staging DDL failure')
            return original(db,statement,parameters)
        with patch.object(DatabaseAdapter,'execute',fail_after_first_table):
            with self.assertRaisesRegex(RuntimeError,'Injected'):
                migrate(self.app)
        tables=self.sql('SELECT table_name FROM information_schema.tables WHERE table_schema=?',(self.schema,))
        self.assertNotIn('farm_expenses',{r['table_name'] for r in tables})
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM orders')[0]['n'],1)
