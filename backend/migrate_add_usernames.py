"""Add nullable, unique usernames without changing legacy accounts."""

from app import create_app
from app.db import get_db


def column_names(database, table):
    return {row["name"] for row in database.execute(f"PRAGMA table_info({table})")}


app = create_app()
with app.app_context():
    database = get_db()
    if "username" not in column_names(database, "customers"):
        database.execute("ALTER TABLE customers ADD COLUMN username TEXT")
    if "username" not in column_names(database, "admins"):
        database.execute("ALTER TABLE admins ADD COLUMN username TEXT")
    database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_username ON customers(username) WHERE username IS NOT NULL"
    )
    database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_admins_username ON admins(username) WHERE username IS NOT NULL"
    )
    database.commit()
    print("Username migration completed successfully.")
