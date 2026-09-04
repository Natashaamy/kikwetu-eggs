"""Authenticated customer dashboard, profile, history, and cancellation."""

import sqlite3

from flask import Blueprint, jsonify, request, session

from ..auth import customer_required
from ..db import get_db, is_postgres, item_summary_expression


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


def _customer_order_for_edit(database, order_id, customer_id, lock=False):
    lock_clause = " FOR UPDATE OF orders, order_items" if lock and is_postgres() else ""
    return database.execute(
        """SELECT orders.order_id, orders.order_number, orders.order_status,
                  orders.payment_status, orders.payment_method, orders.total_amount,
                  order_items.order_item_id, order_items.product_id,
                  order_items.quantity, order_items.unit_price,
                  products.name AS product_name, products.unit_name
           FROM orders
           JOIN order_items ON order_items.order_id = orders.order_id
           JOIN products ON products.product_id = order_items.product_id
           WHERE orders.order_id = ? AND orders.customer_id = ?
           ORDER BY order_items.order_item_id""" + lock_clause,
        (order_id, customer_id),
    ).fetchall()


def _edit_state_error(order):
    if order["order_status"] == "completed":
        return "Completed orders cannot be edited"
    if order["order_status"] == "cancelled":
        return "Cancelled orders cannot be edited"
    if order["payment_status"] == "paid":
        return "Paid orders cannot be edited"
    if order["order_status"] not in {"pending", "processing"}:
        return "This order cannot be edited in its current state"
    return None


@customer_portal_bp.get("/orders/<int:order_id>")
@customer_required
def customer_order_detail(order_id):
    database = get_db()
    try:
        rows = _customer_order_for_edit(database, order_id, session["user_id"])
        if not rows:
            return jsonify({"error": "Order not found"}), 404
        order = dict(rows[0])
        pending_mpesa = database.execute(
            "SELECT 1 FROM mpesa_transactions WHERE order_id = ? AND status = 'pending'",
            (order_id,),
        ).fetchone() is not None
        state_error = _edit_state_error(order)
        order["can_edit"] = state_error is None and not pending_mpesa and len(rows) == 1
        order["edit_block_reason"] = (
            "This order cannot be edited while an M-Pesa payment is pending."
            if pending_mpesa else state_error
        )
        return jsonify(order), 200
    except sqlite3.Error:
        return jsonify({"error": "Order details could not be loaded"}), 500


@customer_portal_bp.patch("/orders/<int:order_id>")
@customer_required
def edit_customer_order(order_id):
    """Replace a customer's single order line and reconcile stock atomically."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400
    product_id = data.get("product_id")
    quantity = data.get("quantity")
    if not isinstance(product_id, int) or isinstance(product_id, bool) or product_id <= 0:
        return jsonify({"error": "A valid product is required"}), 400
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return jsonify({"error": "Quantity must be a positive whole number"}), 400

    database = get_db()
    try:
        database.begin()
        rows = _customer_order_for_edit(database, order_id, session["user_id"], lock=True)
        if not rows:
            database.rollback()
            return jsonify({"error": "Order not found"}), 404
        order = rows[0]
        state_error = _edit_state_error(order)
        if state_error:
            database.rollback()
            return jsonify({"error": state_error}), 400
        if database.execute(
            "SELECT 1 FROM mpesa_transactions WHERE order_id = ? AND status = 'pending'",
            (order_id,),
        ).fetchone():
            database.rollback()
            return jsonify({
                "error": "This order cannot be edited while an M-Pesa payment is pending."
            }), 409
        if len(rows) != 1:
            database.rollback()
            return jsonify({"error": "Orders with multiple items cannot be edited here"}), 409

        current_item = rows[0]
        product = database.execute(
            """SELECT product_id, name, unit_name, unit_price, is_active
               FROM products WHERE product_id = ?""",
            (product_id,),
        ).fetchone()
        if product is None:
            database.rollback()
            return jsonify({"error": "Product not found"}), 404
        if not product["is_active"]:
            database.rollback()
            return jsonify({"error": "This product is not currently available"}), 400

        old_product_id = current_item["product_id"]
        old_quantity = current_item["quantity"]
        if product_id == old_product_id:
            stock_update = database.execute(
                """UPDATE products
                   SET stock_quantity = stock_quantity + ? - ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE product_id = ? AND stock_quantity + ? >= ?""",
                (old_quantity, quantity, product_id, old_quantity, quantity),
            )
        else:
            database.execute(
                """UPDATE products SET stock_quantity = stock_quantity + ?,
                          updated_at = CURRENT_TIMESTAMP
                   WHERE product_id = ?""",
                (old_quantity, old_product_id),
            )
            stock_update = database.execute(
                """UPDATE products SET stock_quantity = stock_quantity - ?,
                          updated_at = CURRENT_TIMESTAMP
                   WHERE product_id = ? AND stock_quantity >= ?""",
                (quantity, product_id, quantity),
            )
        if stock_update.rowcount != 1:
            database.rollback()
            return jsonify({
                "error": "Sorry, the requested quantity is currently unavailable."
            }), 400

        unit_price = product["unit_price"]
        line_total = unit_price * quantity
        database.execute(
            """UPDATE order_items SET product_id = ?, quantity = ?,
                      unit_price = ?, line_total = ?
               WHERE order_item_id = ? AND order_id = ?""",
            (product_id, quantity, unit_price, line_total,
             current_item["order_item_id"], order_id),
        )
        reset_mpesa_choice = order["payment_method"] == "mpesa"
        database.execute(
            """UPDATE orders SET total_amount = ?,
                      order_status = CASE WHEN ? THEN 'pending' ELSE order_status END,
                      payment_method = CASE WHEN ? THEN NULL ELSE payment_method END,
                      paid_at = NULL, updated_at = CURRENT_TIMESTAMP
               WHERE order_id = ? AND customer_id = ?""",
            (line_total, reset_mpesa_choice, reset_mpesa_choice,
             order_id, session["user_id"]),
        )
        updated = database.execute(
            """SELECT order_id, order_number, order_status, payment_status,
                      payment_method, total_amount
               FROM orders WHERE order_id = ?""",
            (order_id,),
        ).fetchone()
        database.commit()
        return jsonify({
            "message": "Order updated successfully",
            "product_id": product_id,
            "product_name": product["name"],
            "unit_name": product["unit_name"],
            "unit_price": unit_price,
            "quantity": quantity,
            **dict(updated),
        }), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "The order could not be updated"}), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "The order could not be updated"}), 500


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


@customer_portal_bp.patch("/profile")
@customer_required
def update_customer_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400
    name = data.get("name")
    phone_number = data.get("phone_number")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Name is required"}), 400
    if not isinstance(phone_number, str) or not phone_number.strip():
        return jsonify({"error": "Phone number is required"}), 400
    clean_name = " ".join(name.strip().split())
    clean_username = clean_name.casefold()
    clean_phone = phone_number.strip()
    database = get_db()
    try:
        database.begin()
        conflict = database.execute(
            """SELECT 1 FROM customers
               WHERE (username = ? OR phone_number = ?) AND customer_id != ?
               UNION ALL SELECT 1 FROM admins WHERE username = ? LIMIT 1""",
            (clean_username, clean_phone, session["user_id"], clean_username),
        ).fetchone()
        if conflict:
            database.rollback()
            return jsonify({"error": "That name or phone number is already in use"}), 400
        database.execute(
            """UPDATE customers SET name = ?, username = ?, phone_number = ?,
                      updated_at = CURRENT_TIMESTAMP WHERE customer_id = ?""",
            (clean_name, clean_username, clean_phone, session["user_id"]),
        )
        profile = database.execute(
            "SELECT name, phone_number FROM customers WHERE customer_id = ?",
            (session["user_id"],),
        ).fetchone()
        database.commit()
        return jsonify({"message": "Profile updated successfully.", "profile": dict(profile)}), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "That name or phone number is already in use"}), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "Profile could not be updated"}), 500
