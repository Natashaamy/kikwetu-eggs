"""Authenticated customer order creation endpoint."""

import sqlite3
from uuid import uuid4

from flask import Blueprint, jsonify, request, session

from ..auth import customer_required
from ..db import get_db


customer_orders_bp = Blueprint("customer_orders", __name__, url_prefix="/api/customer-orders")


@customer_orders_bp.post("")
@customer_required
def place_customer_order():
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
        database.execute("BEGIN IMMEDIATE")
        product = database.execute(
            """SELECT product_id, name, unit_name, unit_price, is_active,
                      stock_quantity
               FROM products WHERE product_id = ?""",
            (product_id,),
        ).fetchone()
        if product is None:
            database.rollback()
            return jsonify({"error": "Product not found"}), 404
        if not product["is_active"]:
            database.rollback()
            return jsonify({"error": "This product is not currently available"}), 400
        if quantity > product["stock_quantity"]:
            database.rollback()
            unit = product["unit_name"] if product["stock_quantity"] == 1 else f"{product['unit_name']}s"
            return jsonify({
                "error": f"Only {product['stock_quantity']} {unit} are currently available"
            }), 400

        temporary_number = f"PENDING-{uuid4().hex}"
        cursor = database.execute(
            "INSERT INTO orders(customer_id, order_number, order_status, total_amount) VALUES (?, ?, 'pending', 0)",
            (session["user_id"], temporary_number),
        )
        order_id = cursor.lastrowid
        order_number = f"ORD-{order_id:06d}"
        if database.execute("SELECT 1 FROM orders WHERE order_number = ? AND order_id != ?", (order_number, order_id)).fetchone():
            order_number = f"{order_number}-{uuid4().hex[:4].upper()}"
        database.execute("UPDATE orders SET order_number = ? WHERE order_id = ?", (order_number, order_id))
        unit_price = product["unit_price"]
        line_total = quantity * unit_price
        database.execute("INSERT INTO order_items(order_id, product_id, quantity, unit_price, line_total) VALUES (?, ?, ?, ?, ?)", (order_id, product_id, quantity, unit_price, line_total))
        stock_update = database.execute(
            """UPDATE products
               SET stock_quantity = stock_quantity - ?, updated_at = CURRENT_TIMESTAMP
               WHERE product_id = ? AND stock_quantity >= ?""",
            (quantity, product_id, quantity),
        )
        if stock_update.rowcount != 1:
            database.rollback()
            return jsonify({"error": "The requested quantity is no longer available"}), 400
        database.execute("UPDATE orders SET total_amount = (SELECT COALESCE(SUM(line_total), 0) FROM order_items WHERE order_id = ?), updated_at = CURRENT_TIMESTAMP WHERE order_id = ?", (order_id, order_id))
        final_order = database.execute("SELECT order_id, order_number, order_status, total_amount FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        database.commit()
        return jsonify({
            "message": "Order placed successfully",
            "product_id": product_id,
            "quantity": quantity,
            **dict(final_order),
        }), 201
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "The order could not be placed because some information was invalid"}), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "A database error occurred while placing the order"}), 500
