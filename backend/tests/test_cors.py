"""Cross-origin session and cookie configuration tests."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import create_app


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALLOWED_ORIGIN = "https://kikwetu-eggs.netlify.app"


class CorsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        with closing(sqlite3.connect(self.database_path)) as database:
            database.executescript((BACKEND_DIR / "schema_sqlite.sql").read_text(encoding="utf-8"))

        self.app = create_app({
            "TESTING": True,
            "DATABASE_URL": None,
            "DATABASE": self.database_path,
            "SECRET_KEY": "test-secret",
            "FRONTEND_URL": ALLOWED_ORIGIN,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_allowed_origin_receives_credentialed_cors_headers(self):
        response = self.client.get("/api/auth/me", headers={"Origin": ALLOWED_ORIGIN})

        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)
        self.assertEqual(response.headers.get("Access-Control-Allow-Credentials"), "true")

    def test_disallowed_origin_does_not_receive_cors_permission(self):
        response = self.client.get(
            "/api/auth/me", headers={"Origin": "https://untrusted.example"}
        )

        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
        self.assertIsNone(response.headers.get("Access-Control-Allow-Credentials"))

    def test_protected_route_preflight_succeeds_without_a_session(self):
        response = self.client.options(
            "/api/products",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)
        self.assertIn("POST", response.headers.get("Access-Control-Allow-Methods", ""))

    def test_production_session_cookie_is_secure_httponly_and_cross_site(self):
        environment = {
            "FLASK_HTTPS": "1",
            "FRONTEND_URL": ALLOWED_ORIGIN,
            "SECRET_KEY": "production-test-secret",
        }
        with patch.dict(os.environ, environment, clear=False):
            production_app = create_app({
                "TESTING": True,
                "DATABASE_URL": None,
                "DATABASE": self.database_path,
            })
        production_client = production_app.test_client()

        response = production_client.post(
            "/api/auth/register",
            json={
                "name": "Secure Cookie User",
                "phone_number": "0712345678",
                "password": "secure-password",
            },
            headers={"Origin": ALLOWED_ORIGIN},
        )

        self.assertEqual(response.status_code, 201)
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=None", cookie)


if __name__ == "__main__":
    unittest.main()
