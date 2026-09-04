"""Admin-only customer account reporting and safe deletion endpoints."""

import sqlite3

from flask import Blueprint, jsonify, request

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
                customers.is_active,
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
            SELECT customer_id, name, phone_number, is_active, created_at, updated_at
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
                COALESCE(SUM(CASE WHEN order_status = 'processing' THEN 1 ELSE 0 END), 0)
                    AS processing_orders,
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
            SELECT order_number, order_status, payment_status, payment_method,
                   total_amount, created_at
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


@admin_customers_bp.patch("/<int:customer_id>/status")
def update_customer_status(customer_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("is_active"), bool):
        return jsonify({"error": "is_active must be true or false"}), 400
    database = get_db()
    try:
        database.begin()
        customer = database.execute(
            "SELECT customer_id FROM customers WHERE customer_id = ?", (customer_id,)
        ).fetchone()
        if customer is None:
            database.rollback()
            return jsonify({"error": "Customer not found"}), 404
        database.execute(
            """UPDATE customers SET is_active = ?, updated_at = CURRENT_TIMESTAMP
               WHERE customer_id = ?""",
            (data["is_active"], customer_id),
        )
        updated = database.execute(
            """SELECT customer_id, name, phone_number, is_active, created_at
               FROM customers WHERE customer_id = ?""",
            (customer_id,),
        ).fetchone()
        database.commit()
        return jsonify({
            "message": "Customer account reactivated successfully." if data["is_active"]
                       else "Customer account deactivated successfully.",
            "customer": dict(updated),
        }), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "Customer status could not be updated"}), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "Customer status could not be updated"}), 500


@admin_customers_bp.delete("/<int:customer_id>")
def delete_customer(customer_id):
    """Delete only a customer account that has no business history."""
    database = get_db()

    try:
        database.begin()
        customer = database.execute(
            "SELECT customer_id FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        if customer is None:
            database.rollback()
            return jsonify({"error": "Customer not found"}), 404

        has_orders = database.execute(
            "SELECT 1 FROM orders WHERE customer_id = ? LIMIT 1", (customer_id,)
        ).fetchone()
        has_mpesa_history = database.execute(
            "SELECT 1 FROM mpesa_transactions WHERE customer_id = ? LIMIT 1", (customer_id,)
        ).fetchone()
        if has_orders or has_mpesa_history:
            database.rollback()
            return jsonify({
                "error": "This customer has order or payment history and cannot be permanently deleted. Deactivate the account instead."
            }), 409

        database.execute(
            "DELETE FROM customers WHERE customer_id = ?",
            (customer_id,),
        )
        database.commit()
        return jsonify({
            "message": "Customer account permanently deleted successfully.",
        }), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "Customer and order history could not be deleted."
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "Customer deletion could not be completed"}), 500
