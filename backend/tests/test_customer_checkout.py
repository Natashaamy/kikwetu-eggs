"""Customer catalogue, inventory, and cash-payment flow tests."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


BACKEND_DIR = Path(__file__).resolve().parents[1]


class CustomerCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        with closing(sqlite3.connect(self.database_path)) as database:
            database.executescript((BACKEND_DIR / "schema_sqlite.sql").read_text(encoding="utf-8"))
            database.execute(
                "INSERT INTO customers(name, username, phone_number) VALUES ('Customer', 'customer', '0712345678')"
            )
            database.execute(
                "INSERT INTO admins(name, username, email, password_hash) VALUES ('Admin', 'admin', 'admin@example.com', 'unused')"
            )
            database.execute(
                "INSERT INTO products(name, unit_name, unit_price, stock_quantity, is_active) VALUES ('Egg', 'egg', 20, 5, 1)"
            )
            database.execute(
                "INSERT INTO products(name, unit_name, unit_price, stock_quantity, is_active) VALUES ('Hidden', 'tray', 400, 5, 0)"
            )
            database.execute(
                "INSERT INTO products(name, unit_name, unit_price, stock_quantity, is_active) VALUES ('Empty', 'chicken', 700, 0, 1)"
            )
            database.commit()
        self.app = create_app({"TESTING": True, "DATABASE_URL": None, "DATABASE": self.database_path, "SECRET_KEY": "test"})
        self.client = self.app.test_client()
        self.login_customer()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def login_customer(self):
        with self.client.session_transaction() as customer_session:
            customer_session["user_id"] = 1
            customer_session["role"] = "customer"

    def test_customer_catalogue_hides_inventory_and_unavailable_products(self):
        response = self.client.get("/api/products")
        self.assertEqual(response.status_code, 200)
        products = response.get_json()["products"]
        self.assertEqual([product["name"] for product in products], ["Egg"])
        self.assertNotIn("stock_quantity", products[0])
        self.assertNotIn("low_stock_threshold", products[0])
        self.assertNotIn("is_active", products[0])
        detail = self.client.get("/api/products/1").get_json()
        self.assertNotIn("stock_quantity", detail)
        self.assertEqual(self.client.get("/api/products/2").status_code, 404)

    def test_only_active_available_products_are_orderable(self):
        inactive = self.client.post("/api/customer-orders", json={"product_id": 2, "quantity": 1})
        out_of_stock = self.client.post("/api/customer-orders", json={"product_id": 3, "quantity": 1})
        available = self.client.post("/api/customer-orders", json={"product_id": 1, "quantity": 1})
        self.assertEqual(inactive.status_code, 400)
        self.assertEqual(out_of_stock.status_code, 400)
        self.assertEqual(available.status_code, 201)

    def test_excess_quantity_is_rejected_without_revealing_stock(self):
        response = self.client.post("/api/customer-orders", json={"product_id": 1, "quantity": 6})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Sorry, the requested quantity is currently unavailable.")
        self.assertNotIn("5", response.get_json()["error"])

    def test_cash_selection_changes_payment_state_without_changing_inventory(self):
        order = self.client.post("/api/customer-orders", json={"product_id": 1, "quantity": 2}).get_json()
        with closing(sqlite3.connect(self.database_path)) as database:
            stock_before = database.execute("SELECT stock_quantity FROM products WHERE product_id = 1").fetchone()[0]

        response = self.client.patch(
            f"/api/customer/orders/{order['order_id']}/payment-method",
            json={"payment_method": "cash"},
        )
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(self.database_path)) as database:
            saved = database.execute(
                "SELECT order_status, payment_status, payment_method, paid_at FROM orders WHERE order_id = ?",
                (order["order_id"],),
            ).fetchone()
            stock_after = database.execute("SELECT stock_quantity FROM products WHERE product_id = 1").fetchone()[0]
        self.assertEqual(saved, ("processing", "unpaid", "cash", None))
        self.assertEqual(stock_after, stock_before)

    def test_existing_admin_cash_confirmation_still_works(self):
        order = self.client.post("/api/customer-orders", json={"product_id": 1, "quantity": 1}).get_json()
        self.client.patch(f"/api/customer/orders/{order['order_id']}/payment-method", json={"payment_method": "cash"})
        with closing(sqlite3.connect(self.database_path)) as database:
            stock_before_confirmation = database.execute(
                "SELECT stock_quantity FROM products WHERE product_id = 1"
            ).fetchone()[0]
        with self.client.session_transaction() as admin_session:
            admin_session["user_id"] = 1
            admin_session["role"] = "admin"
        response = self.client.patch(
            f"/api/orders/{order['order_id']}/payment",
            json={"payment_status": "paid", "payment_method": "cash"},
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["order_status"], "completed")
        self.assertEqual(result["payment_status"], "paid")
        self.assertEqual(result["payment_method"], "cash")
        self.assertIsNotNone(result["paid_at"])
        with closing(sqlite3.connect(self.database_path)) as database:
            stock_after_confirmation = database.execute(
                "SELECT stock_quantity FROM products WHERE product_id = 1"
            ).fetchone()[0]
        self.assertEqual(stock_after_confirmation, stock_before_confirmation)

        self.login_customer()
        cancellation = self.client.patch(f"/api/customer/orders/{order['order_id']}/cancel")
        self.assertEqual(cancellation.status_code, 400)
        self.assertEqual(cancellation.get_json()["error"], "Completed orders cannot be cancelled")

    def test_bank_transfer_confirmation_does_not_complete_order(self):
        order = self.client.post("/api/customer-orders", json={"product_id": 1, "quantity": 1}).get_json()
        with self.client.session_transaction() as admin_session:
            admin_session["user_id"] = 1
            admin_session["role"] = "admin"
        response = self.client.patch(
            f"/api/orders/{order['order_id']}/payment",
            json={"payment_status": "paid", "payment_method": "bank_transfer"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["order_status"], "pending")


if __name__ == "__main__":
    unittest.main()
