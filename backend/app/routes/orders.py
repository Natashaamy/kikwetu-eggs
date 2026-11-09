"""Order API endpoints."""

import sqlite3

from flask import Blueprint, jsonify, request, session
from ..business_time import utc_now
from ..services.payment_records import money, outstanding, net_received, has_open_attempt, sync_order

from ..db import get_db, item_summary_expression, is_postgres
from ..auth import admin_required


orders_bp = Blueprint("orders", __name__, url_prefix="/api/orders")


@orders_bp.before_request
@admin_required
def protect_order_management():
    return None


@orders_bp.get("")
def get_orders():
    """Return all orders, with the newest orders first."""
    database = get_db()

    try:
        rows = database.execute(
            f"""
            SELECT
                orders.order_id,
                orders.customer_id,
                customers.name AS customer_name,
                orders.order_number,
                orders.order_status,
                orders.total_amount,
                orders.payment_status,
                orders.payment_method,
                orders.paid_at,
                orders.notes,
                orders.created_at,
                orders.updated_at,
                COALESCE({item_summary_expression()}, 'No items') AS item_summary,
                COALESCE(SUM(order_items.quantity), 0) AS quantity,
                (SELECT mt.status FROM mpesa_transactions AS mt
                 WHERE mt.order_id = orders.order_id
                 ORDER BY mt.transaction_id DESC LIMIT 1) AS mpesa_status
            FROM orders
            JOIN customers ON customers.customer_id = orders.customer_id
            LEFT JOIN order_items ON order_items.order_id = orders.order_id
            LEFT JOIN products ON products.product_id = order_items.product_id
            GROUP BY orders.order_id, customers.name
            ORDER BY orders.created_at DESC, orders.order_id DESC
            """
        ).fetchall()
        return jsonify({"orders": [dict(row) for row in rows]}), 200
    except sqlite3.Error:
        return jsonify({
            "error": "A database error occurred while retrieving orders"
        }), 500


@orders_bp.get("/<int:order_id>")
def get_order(order_id):
    """Return one order identified by its order ID."""
    database = get_db()

    try:
        row = database.execute(
            """
            SELECT
                orders.order_id,
                orders.customer_id,
                orders.order_number,
                orders.order_status,
                orders.total_amount,
                orders.payment_status,
                orders.payment_method,
                orders.paid_at,
                orders.notes,
                orders.created_at,
                orders.updated_at,
                customers.name AS customer_name,
                customers.phone_number AS customer_phone_number
            FROM orders
            JOIN customers ON customers.customer_id = orders.customer_id
            WHERE orders.order_id = ?
            """,
            (order_id,),
        ).fetchone()

        if row is None:
            return jsonify({"error": "Order not found"}), 404

        items = database.execute(
            """
            SELECT
                order_items.order_item_id,
                order_items.product_id,
                products.name AS product_name,
                products.unit_name,
                order_items.quantity,
                order_items.unit_price,
                order_items.line_total
            FROM order_items
            JOIN products ON products.product_id = order_items.product_id
            WHERE order_items.order_id = ?
            ORDER BY order_items.order_item_id
            """,
            (order_id,),
        ).fetchall()

        result = dict(row)
        mpesa_payment = database.execute(
            """SELECT mpesa_receipt_number, status, completed_at
               FROM mpesa_transactions
               WHERE order_id = ? AND status = 'successful'
               ORDER BY transaction_id DESC LIMIT 1""",
            (order_id,),
        ).fetchone()
        result["mpesa_payment"] = dict(mpesa_payment) if mpesa_payment else None
        latest_mpesa = database.execute(
            """SELECT status, result_description FROM mpesa_transactions
               WHERE order_id = ? ORDER BY transaction_id DESC LIMIT 1""",
            (order_id,),
        ).fetchone()
        result["latest_mpesa"] = dict(latest_mpesa) if latest_mpesa else None
        result["customer"] = {
            "name": result.pop("customer_name"),
            "phone_number": result.pop("customer_phone_number"),
        }
        result["items"] = [dict(item) for item in items]
        return jsonify(result), 200
    except sqlite3.Error:
        return jsonify({
            "error": "A database error occurred while retrieving the order"
        }), 500


@orders_bp.patch("/<int:order_id>/payment")
def record_order_payment(order_id):
    """Record only the remaining balance, or an explicit partial receipt."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('payment_status') != 'paid':
        return jsonify(error='payment_status must be paid'), 400
    method = data.get('payment_method')
    if method not in ('cash','bank_transfer'):
        return jsonify(error='Manual payments must use cash or bank transfer'), 400
    return _record_event(order_id, data, 'receipt', method)


@orders_bp.post('/<int:order_id>/refunds')
def record_refund(order_id):
    """Record an already completed refund; never initiate provider money movement."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('payment_method') not in ('cash','bank_transfer','mpesa'):
        return jsonify(error='A valid refund payment method is required'), 400
    if not data.get('reference') or not data.get('idempotency_key') or 'amount' not in data:
        return jsonify(error='Refund amount, reference and idempotency_key are required'), 400
    return _record_event(order_id, data, 'refund', data['payment_method'])


def _record_event(order_id, data, kind, method):
    db = get_db()
    try:
        db.begin()
        order = db.execute('SELECT * FROM orders WHERE order_id=?' + (' FOR UPDATE' if is_postgres() else ''), (order_id,)).fetchone()
        if not order:
            return jsonify(error='Order not found'), 404
        key = data.get('idempotency_key') or f'complete:{order_id}'
        if not isinstance(key,str) or not 1 <= len(key) <= 128:
            return jsonify(error='Invalid idempotency key'), 400
        key = kind + ':' + key
        prior = db.execute('SELECT * FROM payment_events WHERE idempotency_key=?', (key,)).fetchone()
        if prior:
            if kind == 'receipt' and not data.get('idempotency_key') and order['payment_status'] != 'paid':
                return jsonify(error='A new receipt after a refund requires a new idempotency_key'), 409
            if prior['order_id'] != order_id or prior['method'] != method or ('amount' in data and money(data['amount']) != money(prior['amount'])) or str(data.get('reference','Manual confirmation')) != prior['reference']:
                return jsonify(error='Idempotency key conflicts with an existing entry'), 409
            return jsonify(message='Payment entry already recorded',event_id=prior['event_id']), 200
        if kind == 'receipt' and (order['order_status'] == 'cancelled' or order['payment_status'] == 'paid'):
            return jsonify(error='Paid or cancelled orders cannot receive manual payments'), 400
        if has_open_attempt(db, order_id):
            return jsonify(error='An M-Pesa payment request is still pending for this order'), 409
        limit = outstanding(db, order) if kind == 'receipt' else net_received(db, order_id)
        amount = money(data.get('amount',limit))
        if amount <= 0 or amount > limit:
            return jsonify(error='Amount exceeds the available balance or is zero'), 400
        if 'amount' in data and not data.get('idempotency_key'):
            return jsonify(error='Explicit amounts require an idempotency_key'), 400
        now = utc_now().isoformat()
        reference = str(data.get('reference','Manual confirmation'))
        if len(reference) > 200:
            return jsonify(error='Reference is too long'), 400
        event = db.execute('''INSERT INTO payment_events(order_id,kind,amount,method,idempotency_key,reference,occurred_at,created_by)
                           VALUES (?,?,?,?,?,?,?,?) RETURNING event_id''',
                           (order_id,kind,str(amount),method,key,reference,now,session['user_id'])).fetchone()
        sync_order(db,order,method,now,refund=kind == 'refund')
        result = db.execute('SELECT order_id,order_status,payment_status,payment_method,paid_at FROM orders WHERE order_id=?',(order_id,)).fetchone()
        db.commit()
        return jsonify(message='Payment recorded successfully',event_id=event['event_id'],**dict(result)),200
    except ValueError as error:
        return jsonify(error=str(error)),400
    except sqlite3.IntegrityError:
        return jsonify(error='Payment entry conflicts with existing data'),409
    finally:
        db.rollback()


@orders_bp.post("/<int:order_id>/items")
def create_order_item(order_id):
    """Add a product to an order and recalculate the order total."""
    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    if "unit_price" in data or "line_total" in data:
        return jsonify({
            "error": "unit_price and line_total are calculated by the server"
        }), 400

    product_id = data.get("product_id")
    quantity = data.get("quantity")

    missing_fields = []
    if product_id is None:
        missing_fields.append("product_id")
    if quantity is None:
        missing_fields.append("quantity")

    if missing_fields:
        return jsonify({
            "error": "Missing required fields",
            "fields": missing_fields,
        }), 400

    if (
        not isinstance(product_id, int)
        or isinstance(product_id, bool)
        or product_id <= 0
    ):
        return jsonify({"error": "product_id must be a positive integer"}), 400

    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
    ):
        return jsonify({"error": "quantity must be a positive integer"}), 400

    database = get_db()

    try:
        database.begin()
        order = database.execute(
            "SELECT order_id, order_status, payment_status FROM orders WHERE order_id = ?" + (" FOR UPDATE" if is_postgres() else ""),
            (order_id,),
        ).fetchone()

        if order is None:
            database.rollback()
            return jsonify({"error": "Order not found"}), 404
        if has_open_attempt(database,order_id) or net_received(database,order_id)>0:
            database.rollback()
            return jsonify(error='Payment activity prevents item changes'),409
        if order["order_status"] != "pending":
            database.rollback()
            return jsonify({"error": "Items can only be added to pending orders"}), 400

        product = database.execute(
            """
            SELECT product_id, name, unit_name, unit_price, is_active, stock_quantity
            FROM products
            WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()

        if product is None:
            database.rollback()
            return jsonify({"error": "Product not found"}), 404

        if not product["is_active"]:
            database.rollback()
            return jsonify({"error": "Inactive products cannot be added to orders"}), 400
        if quantity > product["stock_quantity"]:
            database.rollback()
            unit = product["unit_name"] if product["stock_quantity"] == 1 else f"{product['unit_name']}s"
            return jsonify({
                "error": f"Only {product['stock_quantity']} {unit} are currently available"
            }), 400

        unit_price = product["unit_price"]
        line_total = quantity * unit_price

        created_item = database.execute(
            """
            INSERT INTO order_items(order_id, product_id, quantity, unit_price, line_total)
            VALUES (?, ?, ?, ?, ?) RETURNING order_item_id
            """,
            (order_id, product_id, quantity, unit_price, line_total),
        ).fetchone()
        stock_update = database.execute(
            """UPDATE products
               SET stock_quantity = stock_quantity - ?, updated_at = CURRENT_TIMESTAMP
               WHERE product_id = ? AND stock_quantity >= ?""",
            (quantity, product_id, quantity),
        )
        if stock_update.rowcount != 1:
            database.rollback()
            return jsonify({"error": "The requested quantity is no longer available"}), 400
        database.execute(
            """
            UPDATE orders
            SET
                total_amount = (
                    SELECT COALESCE(SUM(line_total), 0)
                    FROM order_items
                    WHERE order_id = ?
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            (order_id, order_id),
        )
        order_item = database.execute(
            """
            SELECT
                order_item_id,
                order_id,
                product_id,
                quantity,
                unit_price,
                line_total
            FROM order_items
            WHERE order_item_id = ?
            """,
            (created_item["order_item_id"],),
        ).fetchone()
        database.commit()
        return jsonify(dict(order_item)), 201
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "Order item could not be created because the supplied data is invalid"
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({
            "error": "A database error occurred while adding the order item"
        }), 500


@orders_bp.delete("/<int:order_id>")
def delete_order(order_id):
    """Retain cancelled orders and payment history for reconciliation."""
    return jsonify({"error": "Orders are retained for audit and cannot be deleted"}), 409


@orders_bp.patch("/<int:order_id>")
def update_order(order_id):
    """Partially update one order and return its current values."""
    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    if "total_amount" in data:
        return jsonify({"error": "Order totals are calculated from saved order items"}), 400

    allowed_fields = {
        "customer_id",
        "order_number",
        "order_status",
        "total_amount",
        "notes",
    }
    provided_fields = allowed_fields.intersection(data)

    if not provided_fields:
        return jsonify({"error": "No valid fields were provided for update"}), 400

    customer_id = data.get("customer_id")
    order_number = data.get("order_number")
    order_status = data.get("order_status")
    total_amount = data.get("total_amount")
    notes = data.get("notes")

    if "customer_id" in provided_fields and (
        not isinstance(customer_id, int)
        or isinstance(customer_id, bool)
        or customer_id <= 0
    ):
        return jsonify({"error": "customer_id must be a positive integer"}), 400

    if "order_number" in provided_fields and (
        not isinstance(order_number, str) or not order_number.strip()
    ):
        return jsonify({"error": "order_number cannot be empty"}), 400

    valid_statuses = {"pending", "confirmed", "processing", "completed", "cancelled"}
    if "order_status" in provided_fields and order_status not in valid_statuses:
        return jsonify({"error": "order_status is invalid"}), 400

    if "total_amount" in provided_fields and (
        total_amount is None
        or not isinstance(total_amount, int)
        or isinstance(total_amount, bool)
        or total_amount < 0
    ):
        return jsonify({"error": "total_amount must be a non-negative integer"}), 400

    if "notes" in provided_fields and notes is not None and not isinstance(notes, str):
        return jsonify({"error": "notes must be text or null"}), 400

    database = get_db()

    try:
        database.begin()
        existing_order = database.execute(
            "SELECT order_id, order_status, payment_status FROM orders WHERE order_id = ?" + (" FOR UPDATE" if is_postgres() else ""),
            (order_id,),
        ).fetchone()

        if existing_order is None:
            return jsonify({"error": "Order not found"}), 404

        if "order_status" in provided_fields:
            current_status = existing_order["order_status"]

            if order_status == "cancelled" and (existing_order["payment_status"] == "paid" or net_received(database, order_id) > 0):
                database.rollback()
                return jsonify({
                    "error": "This order has already been paid. A refund process is required before cancellation."
                }), 400
            if order_status == "cancelled" and has_open_attempt(database, order_id):
                database.rollback()
                return jsonify({
                    "error": "An M-Pesa payment request is still pending for this order"
                }), 409

            if order_status == "cancelled":
                if current_status == "completed":
                    database.rollback()
                    return jsonify({
                        "error": "Completed orders cannot be cancelled"
                    }), 400
                if current_status == "cancelled":
                    database.rollback()
                    return jsonify({
                        "error": "Order is already cancelled"
                    }), 400
                if current_status not in {"pending", "processing"}:
                    database.rollback()
                    return jsonify({
                        "error": "Only unpaid pending or processing orders can be cancelled"
                    }), 400

            if order_status == "completed" and current_status == "cancelled":
                database.rollback()
                return jsonify({
                    "error": "Cancelled orders cannot be completed"
                }), 400

        if "order_status" in provided_fields and order_status == "cancelled":
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

        database.execute(
            """
            UPDATE orders
            SET
                customer_id = CASE WHEN ? THEN ? ELSE customer_id END,
                order_number = CASE WHEN ? THEN ? ELSE order_number END,
                order_status = CASE WHEN ? THEN ? ELSE order_status END,
                total_amount = CASE WHEN ? THEN ? ELSE total_amount END,
                notes = CASE WHEN ? THEN ? ELSE notes END,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            (
                "customer_id" in provided_fields,
                customer_id,
                "order_number" in provided_fields,
                order_number,
                "order_status" in provided_fields,
                order_status,
                "total_amount" in provided_fields,
                total_amount,
                "notes" in provided_fields,
                notes,
                order_id,
            ),
        )
        updated_order = database.execute(
            """
            SELECT
                order_id,
                customer_id,
                order_number,
                order_status,
                total_amount,
                payment_status,
                payment_method,
                paid_at,
                notes,
                created_at,
                updated_at
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()
        database.commit()
        return jsonify(dict(updated_order)), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "Order could not be updated because the supplied data is invalid"
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({
            "error": "A database error occurred while updating the order"
        }), 500


@orders_bp.post("")
def create_order():
    """Validate and create an order."""
    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    customer_id = data.get("customer_id")
    order_number = data.get("order_number")
    order_status = data.get("order_status")
    total_amount = 0
    notes = data.get("notes")
    if data.get("total_amount", 0) != 0:
        return jsonify({"error": "New orders start at zero; add server-priced order items"}), 400

    missing_fields = []
    if customer_id is None:
        missing_fields.append("customer_id")
    if not order_number:
        missing_fields.append("order_number")
    if not order_status:
        missing_fields.append("order_status")
    if total_amount is None:
        missing_fields.append("total_amount")

    if missing_fields:
        return jsonify({
            "error": "Missing required fields",
            "fields": missing_fields,
        }), 400

    if notes is not None and not isinstance(notes, str):
        return jsonify({"error": "notes must be text or null"}), 400

    database = get_db()

    try:
        created_order = database.execute(
            """
            INSERT INTO orders(
                customer_id,
                order_number,
                order_status,
                total_amount,
                notes
            )
            VALUES (?, ?, ?, ?, ?) RETURNING order_id
            """,
            (customer_id, order_number, order_status, total_amount, notes),
        ).fetchone()
        database.commit()
        return jsonify({
            "message": "Order created successfully",
            "order_id": created_order["order_id"],
        }), 201
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "Order could not be created because the supplied data is invalid"
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({
            "error": "A database error occurred while creating the order"
        }), 500
