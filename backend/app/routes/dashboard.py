"""Admin dashboard summary endpoint."""

import sqlite3

from flask import Blueprint, jsonify

from ..db import get_db
from ..auth import admin_required


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.get("")
@admin_required
def get_dashboard():
    """Return order, product, revenue, and recent-order statistics."""
    database = get_db()

    try:
        order_summary = database.execute(
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
                ), 0) AS completed_revenue,
                COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN 1 ELSE 0 END), 0)
                    AS paid_orders,
                COALESCE(SUM(CASE WHEN payment_status = 'unpaid' AND order_status != 'cancelled' THEN 1 ELSE 0 END), 0)
                    AS unpaid_orders,
                COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN total_amount ELSE 0 END), 0)
                    AS payments_received,
                COALESCE(SUM(CASE WHEN payment_status = 'unpaid' AND order_status != 'cancelled' THEN total_amount ELSE 0 END), 0)
                    AS outstanding_amount
            FROM orders
            """
        ).fetchone()

        product_summary = database.execute(
            """
            SELECT
                COUNT(*) AS total_products,
                COALESCE(SUM(CASE WHEN is_active THEN 1 ELSE 0 END), 0)
                    AS active_products,
                COALESCE(SUM(CASE WHEN stock_quantity = 0 THEN 1 ELSE 0 END), 0)
                    AS out_of_stock_products,
                COALESCE(SUM(CASE WHEN stock_quantity > 0
                    AND stock_quantity <= low_stock_threshold THEN 1 ELSE 0 END), 0)
                    AS low_stock_products
            FROM products
            """
        ).fetchone()

        recent_orders = database.execute(
            """
            SELECT
                orders.order_id,
                orders.order_number,
                customers.name AS customer_name,
                orders.order_status,
                orders.payment_status,
                orders.total_amount,
                orders.created_at
            FROM orders
            JOIN customers
                ON customers.customer_id = orders.customer_id
            ORDER BY orders.created_at DESC, orders.order_id DESC
            LIMIT ?
            """,
            (5,),
        ).fetchall()

        inventory_attention = database.execute(
            """
            SELECT product_id, name, unit_name, stock_quantity, low_stock_threshold
            FROM products
            WHERE stock_quantity <= low_stock_threshold
            ORDER BY stock_quantity ASC, name ASC
            LIMIT ?
            """,
            (5,),
        ).fetchall()

        return jsonify({
            "total_orders": order_summary["total_orders"],
            "pending_orders": order_summary["pending_orders"],
            "completed_orders": order_summary["completed_orders"],
            "cancelled_orders": order_summary["cancelled_orders"],
            "total_products": product_summary["total_products"],
            "active_products": product_summary["active_products"],
            "low_stock_products": product_summary["low_stock_products"],
            "out_of_stock_products": product_summary["out_of_stock_products"],
            "completed_revenue": order_summary["completed_revenue"],
            "paid_orders": order_summary["paid_orders"],
            "unpaid_orders": order_summary["unpaid_orders"],
            "payments_received": order_summary["payments_received"],
            "outstanding_amount": order_summary["outstanding_amount"],
            "recent_orders": [dict(order) for order in recent_orders],
            "inventory_attention": [dict(product) for product in inventory_attention],
        }), 200
    except sqlite3.Error:
        return jsonify({
            "error": "A database error occurred while loading the dashboard"
        }), 500
