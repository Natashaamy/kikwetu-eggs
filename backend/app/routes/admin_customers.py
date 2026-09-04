"""Admin-only customer account reporting and safe deletion endpoints."""

import sqlite3

from flask import Blueprint, jsonify

from ..auth import admin_required
from ..db import get_db


admin_customers_bp = Blueprint(
    "admin_customers", __name__, url_prefix="/api/admin/customers"
)


@admin_customers_bp.before_request
@admin_required
def protect_admin_customer_management():
    return None


@admin_customers_bp.get("")
def list_customers():
    """Return registered customers with useful order summaries."""
    database = get_db()

    try:
        customers = database.execute(
            """
            SELECT
                customers.customer_id,
                customers.name,
                customers.phone_number,
                customers.created_at,
                COUNT(orders.order_id) AS total_orders,
                COALESCE(SUM(
                    CASE WHEN orders.order_status = 'completed' THEN 1 ELSE 0 END
                ), 0) AS completed_orders,
                COALESCE(SUM(
                    CASE WHEN orders.order_status = 'completed'
                         THEN orders.total_amount ELSE 0 END
                ), 0) AS total_spent,
                (
                    SELECT COUNT(*)
                    FROM order_items
                    JOIN orders AS customer_orders
                        ON customer_orders.order_id = order_items.order_id
                    WHERE customer_orders.customer_id = customers.customer_id
                ) AS order_items_count,
                MAX(orders.created_at) AS last_order_date
            FROM customers
            LEFT JOIN orders ON orders.customer_id = customers.customer_id
            GROUP BY customers.customer_id
            ORDER BY customers.created_at DESC, customers.customer_id DESC
            """
        ).fetchall()
        return jsonify({"customers": [dict(customer) for customer in customers]}), 200
    except sqlite3.Error:
        return jsonify({"error": "Customer accounts could not be loaded"}), 500


@admin_customers_bp.get("/<int:customer_id>")
def customer_details(customer_id):
    """Return one customer profile, statistics, and order history."""
    database = get_db()

    try:
        customer = database.execute(
            """
            SELECT customer_id, name, phone_number, created_at, updated_at
            FROM customers
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

        if customer is None:
            return jsonify({"error": "Customer not found"}), 404

        statistics = database.execute(
            """
            SELECT
                COUNT(*) AS total_orders,
                COALESCE(SUM(CASE WHEN order_status = 'pending' THEN 1 ELSE 0 END), 0)
                    AS pending_orders,
                COALESCE(SUM(CASE WHEN order_status = 'completed' THEN 1 ELSE 0 END), 0)
                    AS completed_orders,
                COALESCE(SUM(CASE WHEN order_status = 'cancelled' THEN 1 ELSE 0 END), 0)
                    AS cancelled_orders,
                COALESCE(SUM(
                    CASE WHEN order_status = 'completed' THEN total_amount ELSE 0 END
                ), 0) AS total_spent,
                MAX(created_at) AS most_recent_order
            FROM orders
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

        orders = database.execute(
            """
            SELECT order_number, order_status, total_amount, created_at
            FROM orders
            WHERE customer_id = ?
            ORDER BY created_at DESC, order_id DESC
            """,
            (customer_id,),
        ).fetchall()

        return jsonify({
            "customer": dict(customer),
            "statistics": dict(statistics),
            "orders": [dict(order) for order in orders],
        }), 200
    except sqlite3.Error:
        return jsonify({"error": "Customer details could not be loaded"}), 500


@admin_customers_bp.delete("/<int:customer_id>")
def delete_customer(customer_id):
    """Permanently delete a customer and all of their order history."""
    database = get_db()

    try:
        database.execute("BEGIN IMMEDIATE")
        customer = database.execute(
            "SELECT customer_id FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        if customer is None:
            database.rollback()
            return jsonify({"error": "Customer not found"}), 404

        deletion_counts = database.execute(
            """
            SELECT
                COUNT(DISTINCT orders.order_id) AS orders,
                COUNT(order_items.order_item_id) AS order_items
            FROM orders
            LEFT JOIN order_items ON order_items.order_id = orders.order_id
            WHERE orders.customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

        # Pending orders still hold reserved stock, so restore it before deletion.
        database.execute(
            """UPDATE products
               SET stock_quantity = stock_quantity + COALESCE((
                   SELECT SUM(order_items.quantity)
                   FROM order_items
                   JOIN orders ON orders.order_id = order_items.order_id
                   WHERE orders.customer_id = ?
                     AND orders.order_status = 'pending'
                     AND order_items.product_id = products.product_id
               ), 0), updated_at = CURRENT_TIMESTAMP
               WHERE product_id IN (
                   SELECT order_items.product_id
                   FROM order_items
                   JOIN orders ON orders.order_id = order_items.order_id
                   WHERE orders.customer_id = ?
                     AND orders.order_status = 'pending'
               )""",
            (customer_id, customer_id),
        )

        # Deleting orders cascades to their order_items and payments.
        database.execute(
            "DELETE FROM orders WHERE customer_id = ?",
            (customer_id,),
        )
        database.execute(
            "DELETE FROM customers WHERE customer_id = ?",
            (customer_id,),
        )
        database.commit()
        return jsonify({
            "message": "Customer and order history deleted successfully.",
            "deleted_orders": deletion_counts["orders"],
            "deleted_order_items": deletion_counts["order_items"],
        }), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "Customer and order history could not be deleted."
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "Customer deletion could not be completed"}), 500
