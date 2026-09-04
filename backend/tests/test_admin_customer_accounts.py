"""Customer deactivation and history-safe permanent deletion tests."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db
from init_db import migrate_customer_account_status


BACKEND_DIR = Path(__file__).resolve().parents[1]


class AdminCustomerAccountTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        with closing(sqlite3.connect(self.database_path)) as database:
            database.executescript((BACKEND_DIR / "schema_sqlite.sql").read_text(encoding="utf-8"))
            database.execute("INSERT INTO admins(name, username, email, password_hash) VALUES (?, ?, ?, ?)", ("Admin", "admin", "admin@example.com", generate_password_hash("admin-password")))
            database.execute("INSERT INTO customers(name, username, phone_number, password_hash) VALUES (?, ?, ?, ?)", ("History Customer", "history customer", "0711111111", generate_password_hash("customer-password")))
            database.execute("INSERT INTO customers(name, username, phone_number, password_hash) VALUES (?, ?, ?, ?)", ("Empty Customer", "empty customer", "0722222222", generate_password_hash("customer-password")))
            database.execute("INSERT INTO products(name, unit_name, unit_price, stock_quantity) VALUES ('Egg', 'egg', 20, 8)")
            database.execute("INSERT INTO orders(customer_id, order_number, order_status, total_amount, payment_status, payment_method, paid_at) VALUES (1, 'ORD-HISTORY', 'completed', 40, 'paid', 'mpesa', CURRENT_TIMESTAMP)")
            database.execute("INSERT INTO order_items(order_id, product_id, quantity, unit_price, line_total) VALUES (1, 1, 2, 20, 40)")
            database.execute("INSERT INTO payments(order_id, payment_method, payment_status, amount_due, amount_paid, paid_at) VALUES (1, 'mpesa', 'paid', 40, 40, CURRENT_TIMESTAMP)")
            database.execute("INSERT INTO mpesa_transactions(order_id, customer_id, checkout_request_id, phone_number, amount, status, mpesa_receipt_number) VALUES (1, 1, 'checkout-history', '254711111111', 40, 'successful', 'RECEIPT1')")
            database.commit()
        self.app = create_app({"TESTING": True, "DATABASE_URL": None, "DATABASE": self.database_path, "SECRET_KEY": "test"})
        self.client = self.app.test_client()
        self.login_admin_session()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def login_admin_session(self):
        with self.client.session_transaction() as auth_session:
            auth_session["user_id"] = 1
            auth_session["role"] = "admin"

    def database_snapshot(self):
        with closing(sqlite3.connect(self.database_path)) as database:
            return {
                "customers": database.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
                "orders": database.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                "items": database.execute("SELECT COUNT(*) FROM order_items").fetchone()[0],
                "payments": database.execute("SELECT COUNT(*) FROM payments").fetchone()[0],
                "mpesa": database.execute("SELECT COUNT(*) FROM mpesa_transactions").fetchone()[0],
                "stock": database.execute("SELECT stock_quantity FROM products WHERE product_id = 1").fetchone()[0],
            }

    def test_deactivation_preserves_all_business_data_and_inventory(self):
        before = self.database_snapshot()
        response = self.client.patch("/api/admin/customers/1/status", json={"is_active": False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["customer"]["is_active"])
        self.assertEqual(self.database_snapshot(), before)
        with closing(sqlite3.connect(self.database_path)) as database:
            self.assertEqual(database.execute("SELECT is_active FROM customers WHERE customer_id = 1").fetchone()[0], 0)

    def test_deactivated_customer_cannot_login_or_reuse_existing_session(self):
        self.client.patch("/api/admin/customers/1/status", json={"is_active": False})
        login = self.client.post("/api/auth/login", json={"username": "History Customer", "password": "customer-password"})
        self.assertEqual(login.status_code, 403)
        self.assertIn("deactivated", login.get_json()["error"])
        with self.client.session_transaction() as auth_session:
            auth_session["user_id"] = 1
            auth_session["role"] = "customer"
        protected = self.client.get("/api/customer/profile")
        self.assertEqual(protected.status_code, 403)
        with self.client.session_transaction() as auth_session:
            self.assertNotIn("user_id", auth_session)

    def test_admin_is_unaffected_and_can_reactivate_customer(self):
        self.client.patch("/api/admin/customers/1/status", json={"is_active": False})
        admin_login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
        self.assertEqual(admin_login.status_code, 200)
        reactivated = self.client.patch("/api/admin/customers/1/status", json={"is_active": True})
        self.assertEqual(reactivated.status_code, 200)
        self.assertTrue(reactivated.get_json()["customer"]["is_active"])
        customer_login = self.client.post("/api/auth/login", json={"username": "History Customer", "password": "customer-password"})
        self.assertEqual(customer_login.status_code, 200)

    def test_customer_cannot_use_admin_status_or_delete_endpoints(self):
        with self.client.session_transaction() as auth_session:
            auth_session["user_id"] = 2
            auth_session["role"] = "customer"
        self.assertEqual(self.client.patch("/api/admin/customers/1/status", json={"is_active": False}).status_code, 403)
        self.assertEqual(self.client.delete("/api/admin/customers/1").status_code, 403)

    def test_missing_customer_status_returns_404(self):
        self.assertEqual(self.client.patch("/api/admin/customers/9999/status", json={"is_active": False}).status_code, 404)

    def test_customer_with_history_cannot_be_deleted_and_nothing_changes(self):
        before = self.database_snapshot()
        response = self.client.delete("/api/admin/customers/1")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.database_snapshot(), before)

    def test_deactivated_customer_with_history_still_cannot_be_deleted(self):
        self.client.patch("/api/admin/customers/1/status", json={"is_active": False})
        self.assertEqual(self.client.delete("/api/admin/customers/1").status_code, 409)

    def test_active_or_deactivated_customer_without_history_can_be_deleted(self):
        response = self.client.delete("/api/admin/customers/2")
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("INSERT INTO customers(name, username, phone_number, is_active) VALUES ('Inactive Empty', 'inactive empty', '0733333333', 0)")
            customer_id = database.execute("SELECT customer_id FROM customers WHERE username = 'inactive empty'").fetchone()[0]
            database.commit()
        self.assertEqual(self.client.delete(f"/api/admin/customers/{customer_id}").status_code, 200)

    def test_existing_customer_migration_defaults_to_active(self):
        legacy_path = Path(self.temporary_directory.name) / "legacy.db"
        with closing(sqlite3.connect(legacy_path)) as database:
            database.execute("CREATE TABLE customers(customer_id INTEGER PRIMARY KEY, name TEXT)")
            database.execute("INSERT INTO customers(customer_id, name) VALUES (1, 'Legacy')")
            database.commit()
        legacy_app = create_app({"TESTING": True, "DATABASE_URL": None, "DATABASE": legacy_path, "SECRET_KEY": "test"})
        with legacy_app.app_context():
            database = get_db()
            migrate_customer_account_status(database)
            database.commit()
        with closing(sqlite3.connect(legacy_path)) as database:
            self.assertEqual(database.execute("SELECT is_active FROM customers WHERE customer_id = 1").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
