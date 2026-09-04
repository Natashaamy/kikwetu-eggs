"""Flask application package."""

from pathlib import Path
import os
import secrets

from flask import Flask

from .db import close_db
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


def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=Path(app.instance_path) / "chicken_business.db",
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_HTTPS") == "1",
    )

    if test_config is not None:
        app.config.update(test_config)

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

    return app
