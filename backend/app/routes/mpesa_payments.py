"""Customer M-Pesa STK Push initiation, status, and Daraja callback routes."""

import sqlite3

from flask import Blueprint, current_app, jsonify, request, session

from ..auth import customer_required
from ..db import get_db
from ..services import mpesa


mpesa_payments_bp = Blueprint("mpesa_payments", __name__, url_prefix="/api/payments/mpesa")


def _metadata_items(callback):
    items = callback.get("CallbackMetadata", {}).get("Item", [])
    if not isinstance(items, list):
        return {}
    return {
        item.get("Name"): item.get("Value")
        for item in items
        if isinstance(item, dict) and item.get("Name")
    }


@mpesa_payments_bp.post("/stk-push")
@customer_required
def stk_push():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400
    order_id = data.get("order_id")
    if not isinstance(order_id, int) or isinstance(order_id, bool) or order_id <= 0:
        return jsonify({"error": "A valid order is required"}), 400

    database = get_db()
    try:
        order = database.execute(
            """SELECT orders.order_id, orders.order_number, orders.order_status,
                      orders.payment_status, orders.total_amount,
                      customers.phone_number
               FROM orders
               JOIN customers ON customers.customer_id = orders.customer_id
               WHERE orders.order_id = ? AND orders.customer_id = ?""",
            (order_id, session["user_id"]),
        ).fetchone()
        if order is None:
            return jsonify({"error": "Order not found"}), 404
        if order["payment_status"] == "paid":
            return jsonify({"error": "This order has already been paid"}), 400
        if order["order_status"] == "cancelled":
            return jsonify({"error": "Cancelled orders cannot be paid"}), 400
        if order["total_amount"] <= 0:
            return jsonify({"error": "This order does not have a payable amount"}), 400

        pending = database.execute(
            """SELECT checkout_request_id FROM mpesa_transactions
               WHERE order_id = ? AND status = 'pending'
               ORDER BY transaction_id DESC LIMIT 1""",
            (order_id,),
        ).fetchone()
        if pending is not None:
            return jsonify({
                "error": "An M-Pesa payment request is already pending for this order",
                "checkout_request_id": pending["checkout_request_id"],
            }), 409

        current_app.logger.info("Starting M-Pesa STK Push for order %s", order["order_number"])
        daraja = mpesa.initiate_stk_push(
            phone_number=order["phone_number"],
            amount=order["total_amount"],
            order_number=order["order_number"],
        )

        database.execute("BEGIN IMMEDIATE")
        current_order = database.execute(
            """SELECT order_status, payment_status FROM orders
               WHERE order_id = ? AND customer_id = ?""",
            (order_id, session["user_id"]),
        ).fetchone()
        if current_order is None:
            database.rollback()
            return jsonify({"error": "Order not found"}), 404
        if current_order["payment_status"] == "paid" or current_order["order_status"] == "cancelled":
            database.rollback()
            return jsonify({"error": "This order is no longer eligible for M-Pesa payment"}), 409

        database.execute(
            """INSERT INTO mpesa_transactions(
                   order_id, customer_id, merchant_request_id,
                   checkout_request_id, phone_number, amount, status
               ) VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (
                order_id,
                session["user_id"],
                daraja["merchant_request_id"],
                daraja["checkout_request_id"],
                daraja["phone_number"],
                order["total_amount"],
            ),
        )
        database.commit()
        current_app.logger.info(
            "M-Pesa STK Push accepted for order %s; checkout %s",
            order["order_number"],
            daraja["checkout_request_id"],
        )
        return jsonify({
            "message": "M-Pesa payment request sent",
            "checkout_request_id": daraja["checkout_request_id"],
            "payment_status": "pending",
        }), 202
    except mpesa.MpesaConfigurationError as error:
        current_app.logger.error("M-Pesa sandbox configuration error: %s", error)
        return jsonify({"error": str(error)}), 503
    except mpesa.MpesaError as error:
        current_app.logger.warning("M-Pesa STK Push failed for order %s", order_id)
        return jsonify({"error": str(error)}), 502
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "The M-Pesa payment request could not be saved"}), 409
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "The payment request could not be completed"}), 500


@mpesa_payments_bp.get("/status/<checkout_request_id>")
@customer_required
def payment_status(checkout_request_id):
    try:
        transaction = get_db().execute(
            """SELECT mpesa_transactions.checkout_request_id,
                      mpesa_transactions.status,
                      mpesa_transactions.amount,
                      mpesa_transactions.mpesa_receipt_number,
                      mpesa_transactions.result_description,
                      orders.order_id, orders.order_number,
                      orders.payment_status, orders.payment_method, orders.paid_at
               FROM mpesa_transactions
               JOIN orders ON orders.order_id = mpesa_transactions.order_id
               WHERE mpesa_transactions.checkout_request_id = ?
                 AND mpesa_transactions.customer_id = ?""",
            (checkout_request_id, session["user_id"]),
        ).fetchone()
        if transaction is None:
            return jsonify({"error": "Payment request not found"}), 404
        return jsonify(dict(transaction)), 200
    except sqlite3.Error:
        return jsonify({"error": "Payment status could not be loaded"}), 500


@mpesa_payments_bp.post("/callback")
def callback():
    """Receive the public Daraja callback and apply it exactly once."""
    data = request.get_json(silent=True)
    callback_data = data.get("Body", {}).get("stkCallback") if isinstance(data, dict) else None
    if not isinstance(callback_data, dict):
        return jsonify({"ResultCode": 1, "ResultDesc": "Invalid callback"}), 400

    checkout_request_id = callback_data.get("CheckoutRequestID")
    result_code = str(callback_data.get("ResultCode", ""))
    result_description = str(callback_data.get("ResultDesc", ""))[:500]
    if not checkout_request_id:
        return jsonify({"ResultCode": 1, "ResultDesc": "CheckoutRequestID is required"}), 400

    current_app.logger.info("M-Pesa callback received for checkout %s", checkout_request_id)
    database = get_db()
    try:
        database.execute("BEGIN IMMEDIATE")
        transaction = database.execute(
            """SELECT transaction_id, order_id, amount, status
               FROM mpesa_transactions WHERE checkout_request_id = ?""",
            (checkout_request_id,),
        ).fetchone()
        if transaction is None:
            database.rollback()
            current_app.logger.warning("M-Pesa callback has no matching local transaction")
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged"}), 200
        if transaction["status"] == "successful":
            database.rollback()
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback already processed"}), 200

        metadata = _metadata_items(callback_data)
        receipt = metadata.get("MpesaReceiptNumber")
        callback_amount = metadata.get("Amount")
        is_success = result_code == "0"
        amount_matches = False
        if is_success:
            try:
                amount_matches = float(callback_amount) == float(transaction["amount"])
            except (TypeError, ValueError):
                amount_matches = False

        order = database.execute(
            "SELECT order_status, payment_status, payment_method FROM orders WHERE order_id = ?",
            (transaction["order_id"],),
        ).fetchone()
        can_apply_success = (
            is_success
            and amount_matches
            and bool(receipt)
            and order is not None
            and order["order_status"] != "cancelled"
            and (order["payment_status"] == "unpaid" or order["payment_method"] == "mpesa")
        )

        if can_apply_success:
            database.execute(
                """UPDATE mpesa_transactions
                   SET status = 'successful', result_code = ?, result_description = ?,
                       mpesa_receipt_number = ?, completed_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE transaction_id = ?""",
                (result_code, result_description, str(receipt), transaction["transaction_id"]),
            )
            database.execute(
                """UPDATE orders SET payment_status = 'paid', payment_method = 'mpesa',
                          paid_at = COALESCE(paid_at, CURRENT_TIMESTAMP),
                          updated_at = CURRENT_TIMESTAMP
                   WHERE order_id = ?""",
                (transaction["order_id"],),
            )
            current_app.logger.info("M-Pesa payment completed for checkout %s", checkout_request_id)
        else:
            status = "cancelled" if result_code == "1032" else "failed"
            safe_description = result_description
            if is_success and not amount_matches:
                safe_description = "Callback amount did not match the order total"
            elif is_success and not receipt:
                safe_description = "Successful callback did not include a receipt"
            elif is_success and order is not None and order["order_status"] == "cancelled":
                safe_description = "Order was cancelled before payment confirmation"
            elif is_success and order is not None and order["payment_status"] == "paid":
                safe_description = "Order was already paid using another method"
            database.execute(
                """UPDATE mpesa_transactions
                   SET status = ?, result_code = ?, result_description = ?,
                       completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                   WHERE transaction_id = ?""",
                (status, result_code, safe_description[:500], transaction["transaction_id"]),
            )
            current_app.logger.warning(
                "M-Pesa payment ended with status %s for checkout %s", status, checkout_request_id
            )
        database.commit()
        return jsonify({"ResultCode": 0, "ResultDesc": "Callback processed"}), 200
    except sqlite3.IntegrityError:
        database.rollback()
        current_app.logger.warning("Duplicate M-Pesa receipt or callback ignored")
        return jsonify({"ResultCode": 0, "ResultDesc": "Callback already processed"}), 200
    except sqlite3.Error:
        database.rollback()
        current_app.logger.exception("Database error while processing M-Pesa callback")
        return jsonify({"ResultCode": 1, "ResultDesc": "Callback could not be processed"}), 500
