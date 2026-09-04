"""Safely create missing database objects and optionally the initial admin."""

import os
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db, is_postgres


BACKEND_DIR = Path(__file__).resolve().parent
POSTGRES_SCHEMA = BACKEND_DIR / "schema.sql"
SQLITE_SCHEMA = BACKEND_DIR / "schema_sqlite.sql"


def create_initial_admin(database):
    names = (
        "INITIAL_ADMIN_NAME",
        "INITIAL_ADMIN_USERNAME",
        "INITIAL_ADMIN_EMAIL",
        "INITIAL_ADMIN_PASSWORD",
    )
    values = {name: os.environ.get(name, "").strip() for name in names}
    if not any(values.values()):
        print("Initial admin variables not set; skipping admin creation.")
        return
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Missing initial admin variables: {', '.join(missing)}")
    if len(values["INITIAL_ADMIN_PASSWORD"]) < 8:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 8 characters.")

    username = values["INITIAL_ADMIN_USERNAME"].casefold()
    email = values["INITIAL_ADMIN_EMAIL"].lower()
    existing = database.execute(
        "SELECT admin_id FROM admins WHERE username = ? OR email = ? LIMIT 1",
        (username, email),
    ).fetchone()
    if existing:
        print("Matching initial administrator already exists; no changes made.")
        return
    if database.execute(
        "SELECT 1 FROM customers WHERE username = ? LIMIT 1", (username,)
    ).fetchone():
        raise RuntimeError("INITIAL_ADMIN_USERNAME is already used by a customer.")

    database.execute(
        """INSERT INTO admins(name, username, email, password_hash)
           VALUES (?, ?, ?, ?)""",
        (
            " ".join(values["INITIAL_ADMIN_NAME"].split()),
            username,
            email,
            generate_password_hash(values["INITIAL_ADMIN_PASSWORD"]),
        ),
    )
    print("Initial administrator created successfully.")


def reset_admin_password(database):
    """Reset one existing administrator when both recovery variables are set."""
    username = os.environ.get("RESET_ADMIN_USERNAME", "").strip()
    password = os.environ.get("RESET_ADMIN_PASSWORD", "")
    if not username or not password:
        return

    normalized_username = " ".join(username.split()).casefold()
    administrator = database.execute(
        "SELECT admin_id FROM admins WHERE username = ? LIMIT 1",
        (normalized_username,),
    ).fetchone()
    if administrator is None:
        print("No matching administrator was found; password was not changed.")
        return

    database.execute(
        "UPDATE admins SET password_hash = ? WHERE admin_id = ?",
        (
            generate_password_hash(password),
            administrator["admin_id"],
        ),
    )
    database.commit()
    print("Admin password reset completed.")


def initialize_database(app):
    with app.app_context():
        database = get_db()
        schema_file = POSTGRES_SCHEMA if is_postgres() else SQLITE_SCHEMA
        try:
            database.executescript(schema_file.read_text(encoding="utf-8"))
            create_initial_admin(database)
            reset_admin_password(database)
            database.commit()
            engine = "PostgreSQL" if is_postgres() else "SQLite"
            print(f"{engine} schema initialization completed safely.")
        except Exception:
            database.rollback()
            raise


def main() -> None:
    initialize_database(create_app())


if __name__ == "__main__":
    main()
