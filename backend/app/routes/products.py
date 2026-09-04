"""Product API endpoints."""

import math
import sqlite3

from flask import Blueprint, jsonify, request

from ..db import get_db
from ..auth import authorize


products_bp = Blueprint("products", __name__, url_prefix="/api/products")


@products_bp.before_request
def protect_products():
    return authorize("admin") if request.method != "GET" else authorize()


@products_bp.get("")
def get_products():
    """Return all products, with the newest products first."""
    database = get_db()

    try:
        rows = database.execute(
            """
            SELECT
                product_id,
                name,
                description,
                unit_name,
                unit_price,
                stock_quantity,
                low_stock_threshold,
                is_active,
                created_at,
                updated_at
            FROM products
            ORDER BY created_at DESC, product_id DESC
            """
        ).fetchall()
        return jsonify({"products": [dict(row) for row in rows]}), 200
    except sqlite3.Error:
        return jsonify({
            "error": "A database error occurred while retrieving products"
        }), 500


@products_bp.get("/<int:product_id>")
def get_product(product_id):
    """Return one product identified by its product ID."""
    database = get_db()

    try:
        row = database.execute(
            """
            SELECT
                product_id,
                name,
                description,
                unit_name,
                unit_price,
                stock_quantity,
                low_stock_threshold,
                is_active,
                created_at,
                updated_at
            FROM products
            WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()

        if row is None:
            return jsonify({"error": "Product not found"}), 404

        return jsonify(dict(row)), 200
    except sqlite3.Error:
        return jsonify({
            "error": "A database error occurred while retrieving the product"
        }), 500


@products_bp.patch("/<int:product_id>")
def update_product(product_id):
    """Partially update one product and return its current values."""
    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    allowed_fields = {"name", "description", "unit_name", "unit_price", "is_active"}
    provided_fields = allowed_fields.intersection(data)

    if not provided_fields:
        return jsonify({"error": "No valid fields were provided for update"}), 400

    name = data.get("name")
    description = data.get("description")
    unit_name = data.get("unit_name")
    unit_price = data.get("unit_price")
    is_active = data.get("is_active")
    database = get_db()

    try:
        existing_product = database.execute(
            "SELECT product_id FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()

        if existing_product is None:
            return jsonify({"error": "Product not found"}), 404

        if "name" in provided_fields and (
            not isinstance(name, str) or not name.strip()
        ):
            return jsonify({"error": "name cannot be empty"}), 400

        if "unit_name" in provided_fields and (
            not isinstance(unit_name, str) or not unit_name.strip()
        ):
            return jsonify({"error": "unit_name cannot be empty"}), 400

        if "unit_price" in provided_fields and (
            not isinstance(unit_price, (int, float))
            or isinstance(unit_price, bool)
            or not math.isfinite(unit_price)
        ):
            return jsonify({"error": "unit_price must be numeric"}), 400

        if "unit_price" in provided_fields and unit_price < 0:
            return jsonify({"error": "unit_price must not be negative"}), 400

        if (
            "description" in provided_fields
            and description is not None
            and not isinstance(description, str)
        ):
            return jsonify({"error": "description must be text or null"}), 400

        if "is_active" in provided_fields and not (
            isinstance(is_active, bool)
            or isinstance(is_active, int) and is_active in (0, 1)
        ):
            return jsonify({"error": "is_active must be true or false"}), 400

        database.execute(
            """
            UPDATE products
            SET
                name = CASE WHEN ? THEN ? ELSE name END,
                description = CASE WHEN ? THEN ? ELSE description END,
                unit_name = CASE WHEN ? THEN ? ELSE unit_name END,
                unit_price = CASE WHEN ? THEN ? ELSE unit_price END,
                is_active = CASE WHEN ? THEN ? ELSE is_active END,
                updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
            """,
            (
                "name" in provided_fields,
                name.strip() if isinstance(name, str) else name,
                "description" in provided_fields,
                description,
                "unit_name" in provided_fields,
                unit_name.strip() if isinstance(unit_name, str) else unit_name,
                "unit_price" in provided_fields,
                unit_price,
                "is_active" in provided_fields,
                bool(is_active) if "is_active" in provided_fields else None,
                product_id,
            ),
        )
        product = database.execute(
            """
            SELECT
                product_id,
                name,
                description,
                unit_name,
                unit_price,
                stock_quantity,
                low_stock_threshold,
                is_active,
                created_at,
                updated_at
            FROM products
            WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()
        database.commit()
        return jsonify(dict(product)), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "Product could not be updated because the supplied data is invalid"
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({
            "error": "A database error occurred while updating the product"
        }), 500


@products_bp.post("/<int:product_id>/stock")
def add_product_stock(product_id):
    """Add newly received units to a product's current stock."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    quantity = data.get("quantity")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return jsonify({"error": "quantity must be a positive whole number"}), 400

    database = get_db()
    try:
        database.begin()
        product = database.execute(
            "SELECT product_id FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if product is None:
            database.rollback()
            return jsonify({"error": "Product not found"}), 404

        database.execute(
            """
            UPDATE products
            SET stock_quantity = stock_quantity + ?, updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
            """,
            (quantity, product_id),
        )
        updated = database.execute(
            """
            SELECT product_id, name, description, unit_name, unit_price,
                   stock_quantity, low_stock_threshold, is_active,
                   created_at, updated_at
            FROM products WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()
        database.commit()
        return jsonify(dict(updated)), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "Stock could not be added"}), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "A database error occurred while adding stock"}), 500


@products_bp.patch("/<int:product_id>/stock")
def set_product_stock(product_id):
    """Replace a product's current stock with an exact non-negative value."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    stock_quantity = data.get("stock_quantity")
    if (
        not isinstance(stock_quantity, int)
        or isinstance(stock_quantity, bool)
        or stock_quantity < 0
    ):
        return jsonify({
            "error": "stock_quantity must be a whole number that is zero or greater"
        }), 400

    database = get_db()
    try:
        database.begin()
        product = database.execute(
            "SELECT product_id FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if product is None:
            database.rollback()
            return jsonify({"error": "Product not found"}), 404

        database.execute(
            """UPDATE products
               SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP
               WHERE product_id = ?""",
            (stock_quantity, product_id),
        )
        updated = database.execute(
            """SELECT product_id, name, description, unit_name, unit_price,
                      stock_quantity, low_stock_threshold, is_active,
                      created_at, updated_at
               FROM products WHERE product_id = ?""",
            (product_id,),
        ).fetchone()
        database.commit()
        return jsonify(dict(updated)), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "Stock could not be updated"}), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "A database error occurred while setting stock"}), 500


@products_bp.delete("/<int:product_id>")
def delete_product(product_id):
    """Delete one product if it is not referenced by an order."""
    database = get_db()

    try:
        existing_product = database.execute(
            "SELECT product_id FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()

        if existing_product is None:
            return jsonify({"error": "Product not found"}), 404

        database.execute(
            "DELETE FROM products WHERE product_id = ?",
            (product_id,),
        )
        database.commit()
        return jsonify({"message": "Product deleted successfully"}), 200
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "Product cannot be deleted because it is used in an order"
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({
            "error": "A database error occurred while deleting the product"
        }), 500


@products_bp.post("")
def create_product():
    """Validate and create a product."""
    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must contain valid JSON"}), 400

    name = data.get("name")
    description = data.get("description")
    unit_name = data.get("unit_name")
    unit_price = data.get("unit_price")
    is_active = data.get("is_active")

    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "name is required and cannot be empty"}), 400

    if not isinstance(unit_name, str) or not unit_name.strip():
        return jsonify({"error": "unit_name is required and cannot be empty"}), 400

    if unit_price is None:
        return jsonify({"error": "unit_price is required"}), 400

    if (
        not isinstance(unit_price, (int, float))
        or isinstance(unit_price, bool)
        or not math.isfinite(unit_price)
    ):
        return jsonify({"error": "unit_price must be numeric"}), 400

    if unit_price < 0:
        return jsonify({"error": "unit_price must not be negative"}), 400

    if description is not None and not isinstance(description, str):
        return jsonify({"error": "description must be text or null"}), 400

    if "is_active" in data and not (
        isinstance(is_active, bool)
        or isinstance(is_active, int) and is_active in (0, 1)
    ):
        return jsonify({"error": "is_active must be true or false"}), 400

    database = get_db()

    try:
        if "is_active" in data:
            created = database.execute(
                """
                INSERT INTO products(name, description, unit_name, unit_price, is_active)
                VALUES (?, ?, ?, ?, ?) RETURNING product_id
                """,
                (name.strip(), description, unit_name.strip(), unit_price, bool(is_active)),
            ).fetchone()
        else:
            created = database.execute(
                """
                INSERT INTO products(name, description, unit_name, unit_price)
                VALUES (?, ?, ?, ?) RETURNING product_id
                """,
                (name.strip(), description, unit_name.strip(), unit_price),
            ).fetchone()

        product = database.execute(
            """
            SELECT
                product_id,
                name,
                description,
                unit_name,
                unit_price,
                stock_quantity,
                low_stock_threshold,
                is_active,
                created_at,
                updated_at
            FROM products
            WHERE product_id = ?
            """,
            (created["product_id"],),
        ).fetchone()
        database.commit()
        return jsonify(dict(product)), 201
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({
            "error": "Product could not be created because the supplied data is invalid"
        }), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({
            "error": "A database error occurred while creating the product"
        }), 500
