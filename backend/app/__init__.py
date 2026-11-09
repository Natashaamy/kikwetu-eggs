"""Flask application package."""

from pathlib import Path
import os
import secrets
import sqlite3

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter.errors import RateLimitExceeded

from .db import close_db
from .extensions import limiter
from .routes.auth_routes import auth_bp
from .routes.admin_customers import admin_customers_bp
from .routes.customer_orders import customer_orders_bp
from .routes.customer_portal import customer_portal_bp
from .routes.customers import customers_bp
from .routes.dashboard import dashboard_bp
from .routes.orders import orders_bp
from .routes.products import products_bp
from .routes.reports import reports_bp
from .routes.mpesa_payments import mpesa_payments_bp
from .routes.farm_expenses import expenses_bp
from .routes.notifications import notifications_bp
from .routes import financial_summary


def create_app(test_config=None):
    """Create and configure the Flask application."""
    https_enabled = os.environ.get("FLASK_HTTPS") == "1"
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=Path(app.instance_path) / "chicken_business.db",
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        FRONTEND_URL=os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="None" if https_enabled else "Lax",
        SESSION_COOKIE_SECURE=https_enabled,
        TRUST_PROXY_HEADERS=https_enabled,
        APP_ENV=os.environ.get('APP_ENV','development'),
        MAX_CONTENT_LENGTH=131072,
    )

    if test_config is not None:
        app.config.update(test_config)

    if app.config['APP_ENV'] == 'production' and not app.config.get('TESTING'):
        if not app.config.get('DATABASE_URL') or not os.environ.get('SECRET_KEY'):
            raise RuntimeError('Production requires DATABASE_URL and a stable SECRET_KEY')
        if not https_enabled or not app.config['FRONTEND_URL'].startswith('https://'):
            raise RuntimeError('Production requires FLASK_HTTPS=1 and an HTTPS FRONTEND_URL')

    limiter.init_app(app)

    frontend_url = app.config["FRONTEND_URL"]
    if not frontend_url or frontend_url == "*":
        raise RuntimeError("FRONTEND_URL must contain one exact frontend origin")

    CORS(
        app,
        resources={r"/api/*": {"origins": [frontend_url]}},
        supports_credentials=True,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )

    @app.before_request
    def handle_api_preflight():
        """Let browsers complete CORS preflight before role checks run."""
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            return "", 204

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_customers_bp)
    app.register_blueprint(customer_orders_bp)
    app.register_blueprint(customer_portal_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(mpesa_payments_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(notifications_bp)

    @app.errorhandler(sqlite3.Error)
    def handle_database_error(error):
        app.logger.error("A database operation failed", exc_info=error)
        return jsonify({"error": "The database is temporarily unavailable"}), 500

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(error):
        return jsonify({"error": "Too many attempts. Please try again later."}), 429

    return app
