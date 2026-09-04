"""Session authentication and role authorization helpers."""

from functools import wraps

from flask import jsonify, session


def authorize(role=None):
    """Return an auth error response, or None when access is allowed."""
    if session.get("user_id") is None or session.get("role") is None:
        return jsonify({"error": "Authentication required"}), 401
    if role is not None and session.get("role") != role:
        return jsonify({"error": "Forbidden"}), 403
    if session.get("role") == "customer":
        from .db import get_db
        customer = get_db().execute(
            "SELECT is_active FROM customers WHERE customer_id = ?",
            (session["user_id"],),
        ).fetchone()
        if customer is None or not customer["is_active"]:
            session.clear()
            return jsonify({
                "error": "This account has been deactivated. Please contact Kikwetu Eggs."
            }), 403
    return None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        error = authorize()
        if error:
            return error
        return view(*args, **kwargs)
    return wrapped_view


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            error = authorize(role)
            if error:
                return error
            return view(*args, **kwargs)
        return wrapped_view
    return decorator


admin_required = role_required("admin")
customer_required = role_required("customer")
