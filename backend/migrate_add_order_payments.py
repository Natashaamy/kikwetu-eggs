"""Add simple payment-tracking fields to existing orders."""

from app import create_app
from app.db import get_db


app = create_app()
with app.app_context():
    database = get_db()
    try:
        columns = {row["name"] for row in database.execute("PRAGMA table_info(orders)")}
        if "payment_status" not in columns:
            database.execute("""ALTER TABLE orders ADD COLUMN payment_status TEXT
                              NOT NULL DEFAULT 'unpaid'
                              CHECK (payment_status IN ('unpaid', 'paid'))""")
        if "payment_method" not in columns:
            database.execute("""ALTER TABLE orders ADD COLUMN payment_method TEXT
                              CHECK (payment_method IN ('cash', 'mpesa', 'bank_transfer'))""")
        if "paid_at" not in columns:
            database.execute("ALTER TABLE orders ADD COLUMN paid_at TEXT")
        database.commit()
        print("Order payment migration completed successfully.")
    except Exception:
        database.rollback()
        raise
