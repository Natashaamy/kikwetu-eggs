"""Focused tests for M-Pesa phone handling and callback safety."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.services.mpesa import MpesaError, normalize_kenyan_phone


BACKEND_DIR = Path(__file__).resolve().parents[1]


class MpesaTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        with sqlite3.connect(self.database_path) as database:
            database.executescript((BACKEND_DIR / "schema.sql").read_text(encoding="utf-8"))
            customer_id = database.execute(
                "INSERT INTO customers(name, phone_number) VALUES (?, ?)",
                ("Test Customer", "0712345678"),
            ).lastrowid
            order_id = database.execute(
                """INSERT INTO orders(customer_id, order_number, order_status, total_amount)
                   VALUES (?, 'ORD-000001', 'pending', 200)""",
                (customer_id,),
            ).lastrowid
        self.app = create_app({"TESTING": True, "DATABASE": self.database_path, "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def callback_payload(self):
        return {
            "Body": {"stkCallback": {
                "MerchantRequestID": "merchant-1",
                "CheckoutRequestID": "checkout-1",
                "ResultCode": 0,
                "ResultDesc": "Processed successfully",
                "CallbackMetadata": {"Item": [
                    {"Name": "Amount", "Value": 200},
                    {"Name": "MpesaReceiptNumber", "Value": "TEST123456"},
                    {"Name": "PhoneNumber", "Value": 254712345678},
                ]},
            }},
        }

    def test_phone_normalization(self):
        for value in ("0712345678", "712345678", "+254712345678", "254712345678"):
            self.assertEqual(normalize_kenyan_phone(value), "254712345678")
        with self.assertRaises(MpesaError):
            normalize_kenyan_phone("12345")

    def test_stk_push_requires_customer_session(self):
        response = self.client.post("/api/payments/mpesa/stk-push", json={"order_id": 1})
        self.assertEqual(response.status_code, 401)

    @patch("app.routes.mpesa_payments.mpesa.initiate_stk_push")
    def test_stk_push_uses_authenticated_customers_order(self, initiate):
        initiate.return_value = {
            "merchant_request_id": "merchant-2",
            "checkout_request_id": "checkout-2",
            "phone_number": "254712345678",
        }
        with self.client.session_transaction() as customer_session:
            customer_session["user_id"] = 1
            customer_session["role"] = "customer"
        response = self.client.post("/api/payments/mpesa/stk-push", json={"order_id": 1})
        self.assertEqual(response.status_code, 202)
        initiate.assert_called_once_with(
            phone_number="0712345678", amount=200, order_number="ORD-000001"
        )
        with sqlite3.connect(self.database_path) as database:
            saved = database.execute(
                "SELECT customer_id, amount, status FROM mpesa_transactions WHERE checkout_request_id = 'checkout-2'"
            ).fetchone()
        self.assertEqual(saved, (1, 200, "pending"))

    def test_successful_callback_is_idempotent(self):
        with sqlite3.connect(self.database_path) as database:
            database.execute(
                """INSERT INTO mpesa_transactions(
                       order_id, customer_id, merchant_request_id, checkout_request_id,
                       phone_number, amount, status
                   ) VALUES (1, 1, 'merchant-1', 'checkout-1', '254712345678', 200, 'pending')"""
            )
        first = self.client.post("/api/payments/mpesa/callback", json=self.callback_payload())
        second = self.client.post("/api/payments/mpesa/callback", json=self.callback_payload())
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        with sqlite3.connect(self.database_path) as database:
            order = database.execute(
                "SELECT payment_status, payment_method FROM orders WHERE order_id = 1"
            ).fetchone()
            transaction = database.execute(
                "SELECT status, mpesa_receipt_number FROM mpesa_transactions WHERE checkout_request_id = 'checkout-1'"
            ).fetchone()
        self.assertEqual(order, ("paid", "mpesa"))
        self.assertEqual(transaction, ("successful", "TEST123456"))


if __name__ == "__main__":
    unittest.main()
