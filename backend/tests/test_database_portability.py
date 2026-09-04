"""Smoke tests for the shared database adapter and RETURNING-based routes."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.db import DatabaseAdapter, get_db
from init_db import create_initial_admin, reset_admin_password
from werkzeug.security import check_password_hash, generate_password_hash


BACKEND_DIR = Path(__file__).resolve().parents[1]


class DatabasePortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        with closing(sqlite3.connect(self.database_path)) as database:
            database.executescript((BACKEND_DIR / "schema_sqlite.sql").read_text(encoding="utf-8"))
        self.app = create_app({
            "TESTING": True,
            "DATABASE_URL": None,
            "DATABASE": self.database_path,
            "SECRET_KEY": "test",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_postgres_placeholder_conversion(self):
        adapter = DatabaseAdapter(connection=None, postgres=True)
        self.assertEqual(
            adapter._sql("SELECT * FROM products WHERE product_id = ? AND name = ?"),
            "SELECT * FROM products WHERE product_id = %s AND name = %s",
        )

    def test_registration_uses_returning_and_preserves_session(self):
        response = self.client.post("/api/auth/register", json={
            "name": "Database Test",
            "phone_number": "0712000000",
            "password": "secure-pass",
        })
        self.assertEqual(response.status_code, 201)
        self.assertIsInstance(response.get_json()["user"]["customer_id"], int)
        me = self.client.get("/api/auth/me")
        self.assertTrue(me.get_json()["authenticated"])

    def test_product_creation_uses_returning(self):
        with self.client.session_transaction() as admin_session:
            admin_session["user_id"] = 1
            admin_session["role"] = "admin"
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """INSERT INTO admins(name, username, email, password_hash)
                   VALUES ('Admin', 'admin', 'admin@example.com', 'not-used')"""
            )
            database.commit()
        response = self.client.post("/api/products", json={
            "name": "Egg",
            "unit_name": "egg",
            "unit_price": 20,
            "is_active": True,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["product_id"], 1)

    def test_initial_admin_is_hashed_and_idempotent(self):
        variables = {
            "INITIAL_ADMIN_NAME": "Administrator",
            "INITIAL_ADMIN_USERNAME": "admin",
            "INITIAL_ADMIN_EMAIL": "admin@example.com",
            "INITIAL_ADMIN_PASSWORD": "strong-password",
        }
        with patch.dict("os.environ", variables):
            with self.app.app_context():
                database = get_db()
                create_initial_admin(database)
                database.commit()
                create_initial_admin(database)
                database.commit()
                admins = database.execute(
                    "SELECT password_hash FROM admins WHERE username = ?", ("admin",)
                ).fetchall()
        self.assertEqual(len(admins), 1)
        self.assertNotEqual(admins[0]["password_hash"], variables["INITIAL_ADMIN_PASSWORD"])
        self.assertTrue(check_password_hash(admins[0]["password_hash"], variables["INITIAL_ADMIN_PASSWORD"]))

    def add_reset_test_accounts(self):
        admin_hash = generate_password_hash("original-admin-password")
        customer_hash = generate_password_hash("original-customer-password")
        with self.app.app_context():
            database = get_db()
            database.execute(
                """INSERT INTO admins(name, username, email, password_hash)
                   VALUES (?, ?, ?, ?)""",
                ("Natasha", "natasha", "natasha@example.com", admin_hash),
            )
            database.execute(
                """INSERT INTO customers(name, username, phone_number, password_hash)
                   VALUES (?, ?, ?, ?)""",
                ("Customer", "customer", "0700000000", customer_hash),
            )
            database.commit()
        return admin_hash, customer_hash

    def test_existing_admin_password_can_be_reset(self):
        old_hash, _ = self.add_reset_test_accounts()
        variables = {
            "RESET_ADMIN_USERNAME": "  NATASHA  ",
            "RESET_ADMIN_PASSWORD": "new-secure-password",
        }
        output = StringIO()
        with patch.dict("os.environ", variables, clear=True), redirect_stdout(output):
            with self.app.app_context():
                reset_admin_password(get_db())

        with closing(sqlite3.connect(self.database_path)) as database:
            new_hash = database.execute(
                "SELECT password_hash FROM admins WHERE username = 'natasha'"
            ).fetchone()[0]
        self.assertNotEqual(new_hash, old_hash)
        self.assertTrue(check_password_hash(new_hash, variables["RESET_ADMIN_PASSWORD"]))
        self.assertEqual(output.getvalue().strip(), "Admin password reset completed.")
        self.assertNotIn(variables["RESET_ADMIN_PASSWORD"], output.getvalue())

    def test_reset_does_not_create_a_nonexistent_admin(self):
        variables = {
            "RESET_ADMIN_USERNAME": "missing-admin",
            "RESET_ADMIN_PASSWORD": "new-secure-password",
        }
        output = StringIO()
        with patch.dict("os.environ", variables, clear=True), redirect_stdout(output):
            with self.app.app_context():
                reset_admin_password(get_db())

        with closing(sqlite3.connect(self.database_path)) as database:
            admin_count = database.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
        self.assertEqual(admin_count, 0)
        self.assertIn("No matching administrator was found", output.getvalue())

    def test_missing_reset_variable_skips_password_reset(self):
        old_hash, _ = self.add_reset_test_accounts()
        with patch.dict(
            "os.environ", {"RESET_ADMIN_USERNAME": "natasha"}, clear=True
        ):
            with self.app.app_context():
                reset_admin_password(get_db())

        with closing(sqlite3.connect(self.database_path)) as database:
            unchanged_hash = database.execute(
                "SELECT password_hash FROM admins WHERE username = 'natasha'"
            ).fetchone()[0]
        self.assertEqual(unchanged_hash, old_hash)

    def test_admin_reset_does_not_change_customer_passwords(self):
        _, customer_hash = self.add_reset_test_accounts()
        variables = {
            "RESET_ADMIN_USERNAME": "natasha",
            "RESET_ADMIN_PASSWORD": "new-secure-password",
        }
        with patch.dict("os.environ", variables, clear=True):
            with self.app.app_context():
                reset_admin_password(get_db())

        with closing(sqlite3.connect(self.database_path)) as database:
            unchanged_hash = database.execute(
                "SELECT password_hash FROM customers WHERE username = 'customer'"
            ).fetchone()[0]
        self.assertEqual(unchanged_hash, customer_hash)


if __name__ == "__main__":
    unittest.main()
