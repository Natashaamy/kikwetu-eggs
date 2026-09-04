"""Add the M-Pesa STK Push transaction ledger to an existing database."""

from app import create_app
from app.db import get_db


app = create_app()
with app.app_context():
    database = get_db()
    try:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS mpesa_transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                merchant_request_id TEXT,
                checkout_request_id TEXT UNIQUE NOT NULL,
                phone_number TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                status TEXT NOT NULL DEFAULT 'pending' CHECK (
                    status IN ('pending', 'successful', 'failed', 'cancelled')
                ),
                result_code TEXT,
                result_description TEXT,
                mpesa_receipt_number TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
                    ON UPDATE CASCADE ON DELETE CASCADE,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                    ON UPDATE CASCADE ON DELETE RESTRICT
            );

            CREATE INDEX IF NOT EXISTS idx_mpesa_transactions_order_status
            ON mpesa_transactions(order_id, status);

            CREATE INDEX IF NOT EXISTS idx_mpesa_transactions_customer_id
            ON mpesa_transactions(customer_id);

            PRAGMA optimize;
            """
        )
        database.commit()
        print("M-Pesa transaction migration completed successfully.")
    except Exception:
        database.rollback()
        raise
