"""Add non-negative inventory columns while preserving existing products."""

from app import create_app
from app.db import get_db


def column_names(database, table):
    return {row["name"] for row in database.execute(f"PRAGMA table_info({table})")}


app = create_app()
with app.app_context():
    database = get_db()
    try:
        columns = column_names(database, "products")
        if "stock_quantity" not in columns:
            database.execute(
                """ALTER TABLE products ADD COLUMN stock_quantity INTEGER
                   NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0)"""
            )
        if "low_stock_threshold" not in columns:
            database.execute(
                """ALTER TABLE products ADD COLUMN low_stock_threshold INTEGER
                   NOT NULL DEFAULT 10 CHECK (low_stock_threshold >= 0)"""
            )
        database.commit()
        print("Inventory migration completed successfully.")
    except Exception:
        database.rollback()
        raise
