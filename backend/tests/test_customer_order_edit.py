"""Customer order editing, inventory reconciliation, and payment-lock tests."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import create_app


BACKEND_DIR = Path(__file__).resolve().parents[1]


class CustomerOrderEditTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        with closing(sqlite3.connect(self.database_path)) as database:
            database.executescript((BACKEND_DIR / "schema_sqlite.sql").read_text(encoding="utf-8"))
            database.execute("INSERT INTO customers(name, username, phone_number) VALUES ('One', 'one', '0711111111')")
            database.execute("INSERT INTO customers(name, username, phone_number) VALUES ('Two', 'two', '0722222222')")
            database.execute("INSERT INTO products(name, unit_name, unit_price, stock_quantity) VALUES ('Egg', 'egg', 20, 20)")
            database.execute("INSERT INTO products(name, unit_name, unit_price, stock_quantity) VALUES ('Tray', 'tray', 400, 10)")
            database.commit()
        self.app = create_app({"TESTING": True, "DATABASE_URL": None, "DATABASE": self.database_path, "SECRET_KEY": "test"})
        self.client = self.app.test_client()
        self.login(1)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def login(self, customer_id):
        with self.client.session_transaction() as customer_session:
            customer_session["user_id"] = customer_id
            customer_session["role"] = "customer"

    def place(self, product_id=1, quantity=2):
        response = self.client.post("/api/customer-orders", json={"product_id": product_id, "quantity": quantity})
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def saved_state(self, order_id):
        with closing(sqlite3.connect(self.database_path)) as database:
            order = database.execute("SELECT order_id, order_number, order_status, payment_status, payment_method, total_amount FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            item = database.execute("SELECT product_id, quantity, unit_price, line_total FROM order_items WHERE order_id = ?", (order_id,)).fetchone()
            stocks = tuple(row[0] for row in database.execute("SELECT stock_quantity FROM products ORDER BY product_id"))
        return order, item, stocks

    def test_eligible_edit_preserves_identity_and_uses_database_price(self):
        original = self.place(quantity=2)
        response = self.client.patch(f"/api/customer/orders/{original['order_id']}", json={"product_id": 2, "quantity": 3, "unit_price": 1, "total_amount": 3})
        self.assertEqual(response.status_code, 200)
        updated = response.get_json()
        self.assertEqual(updated["order_id"], original["order_id"])
        self.assertEqual(updated["order_number"], original["order_number"])
        self.assertEqual(updated["unit_price"], 400)
        self.assertEqual(updated["total_amount"], 1200)
        _, item, stocks = self.saved_state(original["order_id"])
        self.assertEqual(item, (2, 3, 400, 1200))
        self.assertEqual(stocks, (20, 7))

    def test_increasing_and_decreasing_quantity_adjust_only_the_difference(self):
        order = self.place(quantity=2)
        increased = self.client.patch(f"/api/customer/orders/{order['order_id']}", json={"product_id": 1, "quantity": 5})
        self.assertEqual(increased.status_code, 200)
        self.assertEqual(self.saved_state(order["order_id"])[2][0], 15)
        decreased = self.client.patch(f"/api/customer/orders/{order['order_id']}", json={"product_id": 1, "quantity": 1})
        self.assertEqual(decreased.status_code, 200)
        self.assertEqual(self.saved_state(order["order_id"])[2][0], 19)

    def test_insufficient_inventory_rolls_back_order_item_total_and_stock(self):
        order = self.place(quantity=2)
        before = self.saved_state(order["order_id"])
        response = self.client.patch(f"/api/customer/orders/{order['order_id']}", json={"product_id": 2, "quantity": 11})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Sorry, the requested quantity is currently unavailable.")
        self.assertEqual(self.saved_state(order["order_id"]), before)

    def test_customer_cannot_edit_another_customers_order(self):
        order = self.place()
        self.login(2)
        response = self.client.patch(f"/api/customer/orders/{order['order_id']}", json={"product_id": 1, "quantity": 1})
        self.assertEqual(response.status_code, 404)

    def test_completed_paid_and_cancelled_orders_are_not_editable(self):
        for status, payment, expected in (
            ("completed", "unpaid", "Completed orders cannot be edited"),
            ("processing", "paid", "Paid orders cannot be edited"),
            ("cancelled", "unpaid", "Cancelled orders cannot be edited"),
        ):
            with self.subTest(status=status, payment=payment):
                order = self.place()
                with closing(sqlite3.connect(self.database_path)) as database:
                    database.execute("UPDATE orders SET order_status = ?, payment_status = ? WHERE order_id = ?", (status, payment, order["order_id"]))
                    database.commit()
                response = self.client.patch(f"/api/customer/orders/{order['order_id']}", json={"product_id": 1, "quantity": 1})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"], expected)

    def test_pending_mpesa_locks_edit_and_preserves_everything(self):
        order = self.place(quantity=2)
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("INSERT INTO mpesa_transactions(order_id, customer_id, checkout_request_id, phone_number, amount, status) VALUES (?, 1, 'pending-edit', '254711111111', 40, 'pending')", (order["order_id"],))
            database.commit()
        before = self.saved_state(order["order_id"])
        response = self.client.patch(f"/api/customer/orders/{order['order_id']}", json={"product_id": 2, "quantity": 2})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "This order cannot be edited while an M-Pesa payment is pending.")
        self.assertEqual(self.saved_state(order["order_id"]), before)
        cash = self.client.patch(f"/api/customer/orders/{order['order_id']}/payment-method", json={"payment_method": "cash"})
        self.assertEqual(cash.status_code, 409)

    def test_failed_mpesa_allows_edit_and_clears_payment_choice(self):
        order = self.place(quantity=2)
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("UPDATE orders SET order_status = 'processing', payment_method = 'mpesa' WHERE order_id = ?", (order["order_id"],))
            database.execute("INSERT INTO mpesa_transactions(order_id, customer_id, checkout_request_id, phone_number, amount, status) VALUES (?, 1, 'failed-edit', '254711111111', 40, 'failed')", (order["order_id"],))
            database.commit()
        response = self.client.patch(f"/api/customer/orders/{order['order_id']}", json={"product_id": 1, "quantity": 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["order_status"], "pending")
        self.assertIsNone(response.get_json()["payment_method"])

    @patch("app.routes.mpesa_payments.mpesa.initiate_stk_push")
    def test_stk_push_after_edit_uses_updated_server_total(self, initiate):
        initiate.return_value = {"merchant_request_id": "merchant-new", "checkout_request_id": "checkout-new", "phone_number": "254711111111"}
        order = self.place(product_id=2, quantity=2)
        self.client.patch(f"/api/customer/orders/{order['order_id']}", json={"product_id": 2, "quantity": 3})
        response = self.client.post("/api/payments/mpesa/stk-push", json={"order_id": order["order_id"], "amount": 1})
        self.assertEqual(response.status_code, 202)
        initiate.assert_called_once_with(phone_number="0711111111", amount=1200, order_number=order["order_number"])


if __name__ == "__main__":
    unittest.main()
