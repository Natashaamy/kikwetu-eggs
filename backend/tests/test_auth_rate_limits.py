"""Authentication endpoint rate-limit behavior."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import get_client_ip


BACKEND_DIR = Path(__file__).resolve().parents[1]
RATE_LIMIT_ERROR = "Too many attempts. Please try again later."


class AuthenticationRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        with closing(sqlite3.connect(self.database_path)) as database:
            database.executescript(
                (BACKEND_DIR / "schema_sqlite.sql").read_text(encoding="utf-8")
            )
            database.execute(
                """INSERT INTO customers(name, username, phone_number, password_hash)
                   VALUES (?, ?, ?, ?)""",
                (
                    "Rate Test",
                    "rate test",
                    "0711111111",
                    generate_password_hash("correct-password"),
                ),
            )
            database.commit()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": None,
                "DATABASE": self.database_path,
                "SECRET_KEY": "test",
                "TRUST_PROXY_HEADERS": False,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_successful_login_response_is_unchanged_before_limit(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "Rate Test", "password": "correct-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["authenticated"])
        self.assertEqual(response.get_json()["role"], "customer")

    def test_successful_registration_response_is_unchanged_before_limit(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "New Rate User",
                "phone_number": "0722222222",
                "password": "secure-password",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["authenticated"])
        self.assertEqual(response.get_json()["role"], "customer")

    def test_repeated_failed_logins_return_json_429_and_retry_after(self):
        responses = [
            self.client.post(
                "/api/auth/login",
                json={"username": "Unknown", "password": "wrong-password"},
            )
            for _ in range(6)
        ]
        self.assertTrue(all(response.status_code == 401 for response in responses[:5]))
        limited = responses[5]
        self.assertEqual(limited.status_code, 429)
        self.assertTrue(limited.is_json)
        self.assertEqual(limited.get_json(), {"error": RATE_LIMIT_ERROR})
        self.assertIsNotNone(limited.headers.get("Retry-After"))

    def test_repeated_registration_attempts_return_json_429(self):
        responses = [
            self.client.post(
                "/api/auth/register",
                json={
                    "name": "Rate Test",
                    "phone_number": "0711111111",
                    "password": "secure-password",
                },
            )
            for _ in range(4)
        ]
        self.assertTrue(all(response.status_code == 400 for response in responses[:3]))
        self.assertEqual(responses[3].status_code, 429)
        self.assertEqual(responses[3].get_json(), {"error": RATE_LIMIT_ERROR})

    def test_options_requests_do_not_consume_login_limit(self):
        for _ in range(12):
            response = self.client.options("/api/auth/login")
            self.assertEqual(response.status_code, 204)

        for _ in range(5):
            response = self.client.post(
                "/api/auth/login",
                json={"username": "Unknown", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"username": "Unknown", "password": "wrong-password"},
            ).status_code,
            429,
        )

    def test_authenticated_endpoints_are_not_globally_limited(self):
        with self.client.session_transaction() as auth_session:
            auth_session["user_id"] = 1
            auth_session["role"] = "customer"

        responses = [self.client.get("/api/auth/me") for _ in range(30)]
        self.assertTrue(all(response.status_code == 200 for response in responses))

    def test_production_uses_valid_first_forwarded_ip(self):
        self.app.config["TRUST_PROXY_HEADERS"] = True
        with self.app.test_request_context(
            "/", headers={"X-Forwarded-For": "203.0.113.8"},
            environ_base={"REMOTE_ADDR": "10.0.0.5"},
        ):
            self.assertEqual(get_client_ip(), "203.0.113.8")

    def test_production_uses_first_ip_from_multiple_forwarded_values(self):
        self.app.config["TRUST_PROXY_HEADERS"] = True
        with self.app.test_request_context(
            "/", headers={"X-Forwarded-For": "2001:db8::7, 198.51.100.9, 10.0.0.5"},
            environ_base={"REMOTE_ADDR": "10.0.0.6"},
        ):
            self.assertEqual(get_client_ip(), "2001:db8::7")

    def test_malformed_forwarded_header_falls_back_to_remote_address(self):
        self.app.config["TRUST_PROXY_HEADERS"] = True
        with self.app.test_request_context(
            "/", headers={"X-Forwarded-For": "not-an-ip, 198.51.100.9"},
            environ_base={"REMOTE_ADDR": "10.0.0.7"},
        ):
            self.assertEqual(get_client_ip(), "10.0.0.7")

    def test_missing_forwarded_header_falls_back_to_remote_address(self):
        self.app.config["TRUST_PROXY_HEADERS"] = True
        with self.app.test_request_context(
            "/", environ_base={"REMOTE_ADDR": "10.0.0.8"}
        ):
            self.assertEqual(get_client_ip(), "10.0.0.8")

    def test_local_development_ignores_forwarded_spoofing(self):
        self.app.config["TRUST_PROXY_HEADERS"] = False
        with self.app.test_request_context(
            "/", headers={"X-Forwarded-For": "203.0.113.99"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
            self.assertEqual(get_client_ip(), "127.0.0.1")

    def test_limiter_groups_by_first_forwarded_client_ip(self):
        self.app.config["TRUST_PROXY_HEADERS"] = True
        payload = {"username": "Unknown", "password": "wrong-password"}
        for proxy_ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"):
            response = self.client.post(
                "/api/auth/login",
                json=payload,
                headers={"X-Forwarded-For": f"203.0.113.40, {proxy_ip}"},
            )
            self.assertEqual(response.status_code, 401)

        limited = self.client.post(
            "/api/auth/login",
            json=payload,
            headers={"X-Forwarded-For": "203.0.113.40, 10.0.0.99"},
        )
        other_client = self.client.post(
            "/api/auth/login",
            json=payload,
            headers={"X-Forwarded-For": "203.0.113.41, 10.0.0.99"},
        )
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(other_client.status_code, 401)


if __name__ == "__main__":
    unittest.main()
