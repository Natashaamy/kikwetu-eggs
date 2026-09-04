"""Authenticated customer dashboard, profile, history, and cancellation."""

import sqlite3

from flask import Blueprint, jsonify, request, session

from ..auth import customer_required
from ..db import get_db, item_summary_expression


customer_portal_bp = Blueprint("customer_portal", __name__, url_prefix="/api/customer")


def order_rows(database, customer_id):
    return database.execute(
        f"""
        SELECT orders.order_id, orders.order_number, orders.order_status,
               orders.payment_status, orders.payment_method, orders.paid_at,
               orders.total_amount, orders.created_at,
               (SELECT mt.status FROM mpesa_transactions AS mt
                WHERE mt.order_id = orders.order_id
                ORDER BY mt.transaction_id DESC LIMIT 1) AS mpesa_status,
               (SELECT mt.checkout_request_id FROM mpesa_transactions AS mt
                WHERE mt.order_id = orders.order_id
                ORDER BY mt.transaction_id DESC LIMIT 1) AS checkout_request_id,
               (SELECT mt.mpesa_receipt_number FROM mpesa_transactions AS mt
                WHERE mt.order_id = orders.order_id AND mt.status = 'successful'
                ORDER BY mt.transaction_id DESC LIMIT 1) AS mpesa_receipt_number,
               COALESCE({item_summary_expression()}, 'No items') AS products,
               COALESCE(SUM(order_items.quantity), 0) AS quantity
        FROM orders
        LEFT JOIN order_items ON order_items.order_id = orders.order_id
        LEFT JOIN products ON products.product_id = order_items.product_id
        WHERE orders.customer_id = ?
        GROUP BY orders.order_id
        ORDER BY orders.created_at DESC, orders.order_id DESC
        """,
        (customer_id,),
    ).fetchall()


@customer_portal_bp.get("/dashboard")
@customer_required
def customer_dashboard():
    database = get_db()
    customer_id = session["user_id"]
    try:
        summary = database.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN order_status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_orders,
                COALESCE(SUM(CASE WHEN order_status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_orders,
                COALESCE(SUM(CASE WHEN order_status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_orders,
                COALESCE(SUM(CASE WHEN payment_status = 'unpaid' AND order_status != 'cancelled' THEN 1 ELSE 0 END), 0) AS unpaid_orders,
                COALESCE(SUM(CASE WHEN payment_status = 'unpaid' AND order_status != 'cancelled' THEN total_amount ELSE 0 END), 0) AS amount_outstanding,
                COALESCE(SUM(CASE WHEN order_status = 'completed' THEN total_amount ELSE 0 END), 0) AS total_amount_spent
               FROM orders WHERE customer_id = ?""",
            (customer_id,),
        ).fetchone()
        orders = [dict(row) for row in order_rows(database, customer_id)]
        return jsonify({**dict(summary), "recent_orders": orders[:5]}), 200
    except sqlite3.Error:
        return jsonify({"error": "Customer dashboard could not be loaded"}), 500


@customer_portal_bp.get("/orders")
@customer_required
def customer_orders():
    try:
        return jsonify({"orders": [dict(row) for row in order_rows(get_db(), session["user_id"])]}), 200
    except sqlite3.Error:
        return jsonify({"error": "Customer orders could not be loaded"}), 500


@customer_portal_bp.patch("/orders/<int:order_id>/payment-method")
@customer_required
def select_customer_payment_method(order_id):
    """Record a customer's cash choice without recording a payment."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("payment_method") != "cash":
        return jsonify({"error": "payment_method must be cash"}), 400

    database = get_db()
    try:
        database.begin()
        order = database.execute(
            """SELECT order_status, payment_status, payment_method
               FROM orders WHERE order_id = ? AND customer_id = ?""",
            (order_id, session["user_id"]),
        ).fetchone()
        if order is None:
            database.rollback()
            return jsonify({"error": "Order not found"}), 404
        if order["order_status"] == "cancelled":
            database.rollback()
            return jsonify({"error": "Cancelled orders cannot select a payment method"}), 400
        if order["payment_status"] == "paid":
            database.rollback()
            return jsonify({"error": "This order has already been paid"}), 400
        if order["payment_method"] == "cash":
            database.rollback()
            return jsonify({"error": "Cash payment has already been selected"}), 400
        if database.execute(
            "SELECT 1 FROM mpesa_transactions WHERE order_id = ? AND status = 'pending'",
            (order_id,),
        ).fetchone():
            database.rollback()
            return jsonify({"error": "An M-Pesa payment request is still pending"}), 409

        database.execute(
            """UPDATE orders
               SET order_status = 'processing', payment_status = 'unpaid',
                   payment_method = 'cash', paid_at = NULL,
                   updated_at = CURRENT_TIMESTAMP
               WHERE order_id = ? AND customer_id = ?""",
            (order_id, session["user_id"]),
        )
        updated = database.execute(
            """SELECT order_id, order_number, order_status, payment_status,
                      payment_method, paid_at
               FROM orders WHERE order_id = ?""",
            (order_id,),
        ).fetchone()
        database.commit()
        return jsonify({
            "message": "Cash payment selected. Please pay when your order is fulfilled.",
            **dict(updated),
        }), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "The payment method could not be selected"}), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "The payment method could not be selected"}), 500


@customer_portal_bp.patch("/orders/<int:order_id>/cancel")
@customer_required
def cancel_customer_order(order_id):
    database = get_db()
    try:
        database.begin()
        order = database.execute("SELECT order_status, payment_status FROM orders WHERE order_id = ? AND customer_id = ?", (order_id, session["user_id"])).fetchone()
        if order is None:
            database.rollback()
            return jsonify({"error": "Order not found"}), 404
        if order["order_status"] == "completed":
            database.rollback()
            return jsonify({"error": "Completed orders cannot be cancelled"}), 400
        if order["payment_status"] == "paid":
            database.rollback()
            return jsonify({"error": "This order has already been paid. Please contact the administrator for cancellation."}), 400
        if order["order_status"] == "cancelled":
            database.rollback()
            return jsonify({"error": "Order is already cancelled"}), 400
        if order["order_status"] not in {"pending", "processing"}:
            database.rollback()
            return jsonify({"error": "Only unpaid orders can be cancelled"}), 400
        if database.execute(
            "SELECT 1 FROM mpesa_transactions WHERE order_id = ? AND status = 'pending'",
            (order_id,),
        ).fetchone():
            database.rollback()
            return jsonify({"error": "Please wait for the pending M-Pesa request to finish before cancelling this order"}), 409
        database.execute(
            """UPDATE products
               SET stock_quantity = stock_quantity + COALESCE((
                   SELECT SUM(order_items.quantity) FROM order_items
                   WHERE order_items.order_id = ?
                     AND order_items.product_id = products.product_id
               ), 0), updated_at = CURRENT_TIMESTAMP
               WHERE product_id IN (
                   SELECT product_id FROM order_items WHERE order_id = ?
               )""",
            (order_id, order_id),
        )
        database.execute("UPDATE orders SET order_status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE order_id = ? AND customer_id = ?", (order_id, session["user_id"]))
        database.commit()
        return jsonify({"message": "Order cancelled successfully", "order_id": order_id, "order_status": "cancelled"}), 200
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "Order cancellation could not be completed"}), 500


@customer_portal_bp.get("/profile")
@customer_required
def customer_profile():
    try:
        row = get_db().execute("SELECT customer_id, name, username, phone_number FROM customers WHERE customer_id = ?", (session["user_id"],)).fetchone()
        if row is None:
            return jsonify({"error": "Customer not found"}), 404
        return jsonify({"profile": dict(row)}), 200
    except sqlite3.Error:
        return jsonify({"error": "Customer profile could not be loaded"}), 500
