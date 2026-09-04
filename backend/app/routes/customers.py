"""Customer API endpoints."""

import sqlite3

from flask import Blueprint, jsonify, request

from ..db import get_db
from ..auth import admin_required


customers_bp = Blueprint("customers", __name__, url_prefix="/api/customers")


@customers_bp.before_request
@admin_required
def protect_customer_management():
    return None


@customers_bp.get("")
def get_customers():
    """Return all customers, with the newest customers first."""
    database = get_db()

    try:
        rows = database.execute(
            """
            SELECT customer_id, name, phone_number, created_at, updated_at
            FROM customers
            ORDER BY created_at DESC, customer_id DESC
            """
        ).fetchall()
        return jsonify({"customers": [dict(row) for row in rows]}), 200
    except sqlite3.Error:
        return jsonify({
            "error": "A database error occurred while retrieving customers"
        }), 500


@customers_bp.get("/<int:customer_id>")
def get_customer(customer_id):
    """Return one customer identified by its customer ID."""
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

        return jsonify(dict(customer)), 200
    except sqlite3.Error:
        return jsonify({
            "error": "A database error occurred while retrieving the customer"
        }), 500


@customers_bp.post("")
def create_customer():
    """Validate and create a customer."""
    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    name = data.get("name")
    phone_number = data.get("phone_number")

    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "name is required and cannot be empty"}), 400

    if not isinstance(phone_number, str) or not phone_number.strip():
        return jsonify({
            "error": "phone_number is required and cannot be empty"
        }), 400

    database = get_db()

    try:
        created = database.execute(
            "INSERT INTO customers(name, phone_number) VALUES (?, ?) RETURNING customer_id",
            (name.strip(), phone_number.strip()),
        ).fetchone()
        customer = database.execute(
            """
            SELECT customer_id, name, phone_number, created_at, updated_at
            FROM customers
            WHERE customer_id = ?
            """,
            (created["customer_id"],),
        ).fetchone()
        database.commit()
        return jsonify(dict(customer)), 201
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "A customer with this phone number already exists"
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({
            "error": "A database error occurred while creating the customer"
        }), 500


@customers_bp.patch("/<int:customer_id>")
def update_customer(customer_id):
    """Partially update one customer's contact information."""
    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    allowed_fields = {"name", "phone_number"}
    provided_fields = allowed_fields.intersection(data)

    if not provided_fields:
        return jsonify({"error": "No valid fields were provided for update"}), 400

    name = data.get("name")
    phone_number = data.get("phone_number")
    database = get_db()

    try:
        existing_customer = database.execute(
            "SELECT customer_id FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()

        if existing_customer is None:
            return jsonify({"error": "Customer not found"}), 404

        if "name" in provided_fields and (
            not isinstance(name, str) or not name.strip()
        ):
            return jsonify({"error": "name cannot be empty"}), 400

        if "phone_number" in provided_fields and (
            not isinstance(phone_number, str) or not phone_number.strip()
        ):
            return jsonify({"error": "phone_number cannot be empty"}), 400

        database.execute(
            """
            UPDATE customers
            SET
                name = CASE WHEN ? THEN ? ELSE name END,
                phone_number = CASE WHEN ? THEN ? ELSE phone_number END,
                updated_at = CURRENT_TIMESTAMP
            WHERE customer_id = ?
            """,
            (
                "name" in provided_fields,
                name.strip() if isinstance(name, str) else name,
                "phone_number" in provided_fields,
                phone_number.strip() if isinstance(phone_number, str) else phone_number,
                customer_id,
            ),
        )
        customer = database.execute(
            """
            SELECT customer_id, name, phone_number, created_at, updated_at
            FROM customers
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()
        database.commit()
        return jsonify(dict(customer)), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "A customer with this phone number already exists"
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({
            "error": "A database error occurred while updating the customer"
        }), 500
