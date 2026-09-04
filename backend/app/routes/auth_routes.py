"""Customer and administrator authentication endpoints."""

import sqlite3

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
MINIMUM_PASSWORD_LENGTH = 8


def valid_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def normalize_login_name(name):
    """Normalize a displayed account name for case-insensitive login."""
    return " ".join(name.strip().split()).casefold()


@auth_bp.post("/register")
def register_customer():
    data = valid_json()
    if data is None:
        return jsonify({"error": "Request body must contain valid JSON"}), 400
    name = data.get("name")
    phone_number = data.get("phone_number")
    password = data.get("password")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Full name is required"}), 400
    if not isinstance(phone_number, str) or not phone_number.strip():
        return jsonify({"error": "Phone number is required"}), 400
    if not isinstance(password, str) or len(password) < MINIMUM_PASSWORD_LENGTH:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    database = get_db()
    try:
        clean_name = " ".join(name.strip().split())
        clean_username = normalize_login_name(clean_name)
        database.begin()
        username_exists = database.execute(
            "SELECT 1 FROM customers WHERE username = ? UNION ALL SELECT 1 FROM admins WHERE username = ? LIMIT 1",
            (clean_username, clean_username),
        ).fetchone()
        if username_exists:
            database.rollback()
            return jsonify({"error": "An account with this name already exists. Please use a different name."}), 400
        if database.execute("SELECT 1 FROM customers WHERE phone_number = ?", (phone_number.strip(),)).fetchone():
            database.rollback()
            return jsonify({"error": "An account with this phone number already exists"}), 400
        customer = database.execute(
            """INSERT INTO customers(name, username, phone_number, password_hash)
               VALUES (?, ?, ?, ?) RETURNING customer_id""",
            (clean_name, clean_username, phone_number.strip(), generate_password_hash(password)),
        ).fetchone()
        customer_id = customer["customer_id"]
        database.commit()
        session.clear()
        session["user_id"] = customer_id
        session["role"] = "customer"
        return jsonify({"authenticated": True, "message": "Registration successful", "role": "customer", "user": {"customer_id": customer_id, "name": clean_name, "username": clean_username, "phone_number": phone_number.strip()}}), 201
    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify({"error": "An account with this name or phone number already exists"}), 400
    except sqlite3.Error:
        database.rollback()
        return jsonify({"error": "Registration could not be completed"}), 500


@auth_bp.post("/login")
def login():
    data = valid_json()
    if data is None:
        return jsonify({"error": "Request body must contain valid JSON"}), 400
    login_name = data.get("username")
    password = data.get("password")
    if not isinstance(login_name, str) or not login_name.strip() or not isinstance(password, str):
        return jsonify({"error": "Invalid name or password"}), 401
    database = get_db()
    try:
        clean_username = normalize_login_name(login_name)
        admin = database.execute("SELECT admin_id, name, username, password_hash, is_active FROM admins WHERE username = ?", (clean_username,)).fetchone()
        customer = database.execute("SELECT customer_id, name, username, phone_number, password_hash, is_active FROM customers WHERE username = ?", (clean_username,)).fetchone()
        if admin is not None and customer is not None:
            return jsonify({"error": "Invalid name or password"}), 401
        if admin is not None:
            if not admin["is_active"] or not check_password_hash(admin["password_hash"], password):
                return jsonify({"error": "Invalid name or password"}), 401
            session.clear()
            session["user_id"] = admin["admin_id"]
            session["role"] = "admin"
            return jsonify({"authenticated": True, "message": "Login successful", "role": "admin", "user": {"admin_id": admin["admin_id"], "name": admin["name"], "username": admin["username"]}}), 200
        if customer is not None and not customer["is_active"]:
            return jsonify({"error": "This account has been deactivated. Please contact Kikwetu Eggs."}), 403
        if customer is None or customer["password_hash"] is None or not check_password_hash(customer["password_hash"], password):
            return jsonify({"error": "Invalid name or password"}), 401
        session.clear()
        session["user_id"] = customer["customer_id"]
        session["role"] = "customer"
        return jsonify({"authenticated": True, "message": "Login successful", "role": "customer", "user": {"customer_id": customer["customer_id"], "name": customer["name"], "username": customer["username"], "phone_number": customer["phone_number"]}}), 200
    except sqlite3.Error:
        return jsonify({"error": "Login could not be completed"}), 500


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.get("/me")
def get_current_user():
    user_id = session.get("user_id")
    role = session.get("role")
    if user_id is None or role not in {"admin", "customer"}:
        return jsonify({"authenticated": False}), 200
    database = get_db()
    try:
        if role == "customer":
            user = database.execute("SELECT customer_id, name, username, phone_number FROM customers WHERE customer_id = ? AND is_active", (user_id,)).fetchone()
        else:
            user = database.execute("SELECT admin_id, name, username FROM admins WHERE admin_id = ? AND is_active", (user_id,)).fetchone()
        if user is None:
            session.clear()
            return jsonify({"authenticated": False}), 200
        return jsonify({"authenticated": True, "role": role, "user": dict(user)}), 200
    except sqlite3.Error:
        return jsonify({"error": "Authentication status could not be checked"}), 500
