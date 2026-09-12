"""Public authentication responses must not reveal account existence."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app


BACKEND_DIR = Path(__file__).resolve().parents[1]
REGISTRATION_ERROR = "Unable to create account with the provided details."
LOGIN_ERROR = "Invalid login credentials."
DEACTIVATED_ERROR = "This account has been deactivated. Please contact Kikwetu Eggs."


class AuthenticationPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        with closing(sqlite3.connect(self.database_path)) as database:
            database.executescript(
                (BACKEND_DIR / "schema_sqlite.sql").read_text(encoding="utf-8")
            )
            database.execute(
                """INSERT INTO customers(
                       name, username, phone_number, password_hash, is_active
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    "Existing Customer",
                    "existing customer",
                    "0712345678",
                    generate_password_hash("correct-password"),
                    1,
                ),
            )
            database.execute(
                """INSERT INTO customers(
                       name, username, phone_number, password_hash, is_active
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    "Inactive Customer",
                    "inactive customer",
                    "0799999999",
                    generate_password_hash("inactive-password"),
                    0,
                ),
            )
            database.commit()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": None,
                "DATABASE": self.database_path,
                "SECRET_KEY": "test",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_duplicate_phone_uses_generic_registration_error(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Different Name",
                "phone_number": "0712345678",
                "password": "new-password",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": REGISTRATION_ERROR})

    def test_duplicate_username_uses_same_generic_registration_error(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "  EXISTING   CUSTOMER ",
                "phone_number": "0700000000",
                "password": "new-password",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": REGISTRATION_ERROR})

    def test_unknown_user_and_wrong_password_are_indistinguishable(self):
        unknown = self.client.post(
            "/api/auth/login",
            json={"username": "Unknown Customer", "password": "wrong-password"},
        )
        wrong_password = self.client.post(
            "/api/auth/login",
            json={"username": "Existing Customer", "password": "wrong-password"},
        )
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong_password.status_code, unknown.status_code)
        self.assertEqual(unknown.get_json(), {"error": LOGIN_ERROR})
        self.assertEqual(wrong_password.get_json(), unknown.get_json())

    def test_successful_login_is_unchanged(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "Existing Customer", "password": "correct-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["authenticated"])
        self.assertEqual(response.get_json()["role"], "customer")

    def test_deactivated_message_requires_valid_password(self):
        wrong_password = self.client.post(
            "/api/auth/login",
            json={"username": "Inactive Customer", "password": "wrong-password"},
        )
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(wrong_password.get_json(), {"error": LOGIN_ERROR})

        valid_password = self.client.post(
            "/api/auth/login",
            json={"username": "Inactive Customer", "password": "inactive-password"},
        )
        self.assertEqual(valid_password.status_code, 403)
        self.assertEqual(valid_password.get_json(), {"error": DEACTIVATED_ERROR})


if __name__ == "__main__":
    unittest.main()
