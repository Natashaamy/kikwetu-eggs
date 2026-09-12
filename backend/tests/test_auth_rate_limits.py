"""Authentication endpoint rate-limit behavior."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import get_client_ip, get_login_identifier_key


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

    def test_one_ip_attacking_many_identifiers_reaches_ip_limit(self):
        responses = [
            self.client.post(
                "/api/auth/login",
                json={"username": f"Unknown {attempt}", "password": "wrong-password"},
            )
            for attempt in range(11)
        ]
        self.assertTrue(all(response.status_code == 401 for response in responses[:10]))
        self.assertEqual(responses[10].status_code, 429)
        self.assertEqual(responses[10].get_json(), {"error": RATE_LIMIT_ERROR})

    def test_identifier_limit_applies_across_different_client_ips(self):
        self.app.config["TRUST_PROXY_HEADERS"] = True
        responses = [
            self.client.post(
                "/api/auth/login",
                json={"username": "Shared Target", "password": "wrong-password"},
                headers={"X-Forwarded-For": f"203.0.113.{attempt}"},
            )
            for attempt in range(1, 7)
        ]
        self.assertTrue(all(response.status_code == 401 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, 429)
        self.assertEqual(responses[5].get_json(), {"error": RATE_LIMIT_ERROR})

        unaffected = self.client.post(
            "/api/auth/login",
            json={"username": "Different Target", "password": "wrong-password"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        self.assertEqual(unaffected.status_code, 401)

    def test_existing_and_nonexistent_identifiers_have_same_limit_behavior(self):
        self.app.config["TRUST_PROXY_HEADERS"] = True
        for identifier, address in (
            ("Rate Test", "203.0.113.20"),
            ("Does Not Exist", "203.0.113.21"),
        ):
            responses = [
                self.client.post(
                    "/api/auth/login",
                    json={"username": identifier, "password": "wrong-password"},
                    headers={"X-Forwarded-For": address},
                )
                for _ in range(6)
            ]
            self.assertTrue(all(response.status_code == 401 for response in responses[:5]))
            self.assertEqual(responses[5].status_code, 429)
            self.assertEqual(responses[5].get_json(), {"error": RATE_LIMIT_ERROR})

    def test_identifier_normalization_shares_one_bucket(self):
        variants = [
            " Natasha ",
            "natasha",
            "NATASHA",
            "  Natasha",
            "Natasha  ",
            "NaTaShA",
        ]
        responses = [
            self.client.post(
                "/api/auth/login",
                json={"username": identifier, "password": "wrong-password"},
            )
            for identifier in variants
        ]
        self.assertTrue(all(response.status_code == 401 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, 429)

    def test_missing_identifier_uses_safe_constant_bucket(self):
        responses = [
            self.client.post(
                "/api/auth/login", json={"password": f"password-{attempt}"}
            )
            for attempt in range(6)
        ]
        self.assertTrue(all(response.status_code == 401 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, 429)

    def test_password_does_not_affect_identifier_bucket(self):
        responses = [
            self.client.post(
                "/api/auth/login",
                json={"username": "Password Independent", "password": f"value-{attempt}"},
            )
            for attempt in range(6)
        ]
        self.assertTrue(all(response.status_code == 401 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, 429)

    def test_identifier_key_is_normalized_hashed_and_fixed_length(self):
        keys = []
        for identifier in (" Natasha ", "NATASHA", "natasha"):
            with self.app.test_request_context(
                "/api/auth/login", method="POST", json={"username": identifier}
            ):
                keys.append(get_login_identifier_key())
        self.assertEqual(len(set(keys)), 1)
        self.assertEqual(len(keys[0]), len("login-id:") + 64)
        self.assertNotIn("natasha", keys[0])

    def test_admin_login_still_succeeds_before_limits(self):
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """INSERT INTO admins(name, username, email, password_hash)
                   VALUES (?, ?, ?, ?)""",
                (
                    "Administrator",
                    "administrator",
                    "admin@example.com",
                    generate_password_hash("admin-password"),
                ),
            )
            database.commit()
        response = self.client.post(
            "/api/auth/login",
            json={"username": "Administrator", "password": "admin-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["role"], "admin")

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
        for attempt in range(10):
            response = self.client.post(
                "/api/auth/login",
                json={"username": f"IP Target {attempt}", "password": "wrong-password"},
                headers={"X-Forwarded-For": f"203.0.113.40, 10.0.0.{attempt + 1}"},
            )
            self.assertEqual(response.status_code, 401)

        limited = self.client.post(
            "/api/auth/login",
            json={"username": "IP Target Limited", "password": "wrong-password"},
            headers={"X-Forwarded-For": "203.0.113.40, 10.0.0.99"},
        )
        other_client = self.client.post(
            "/api/auth/login",
            json={"username": "Other Client Target", "password": "wrong-password"},
            headers={"X-Forwarded-For": "203.0.113.41, 10.0.0.99"},
        )
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(other_client.status_code, 401)


if __name__ == "__main__":
    unittest.main()
