"""Interactively create the first administrator account."""

import argparse
import getpass
import sqlite3

from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db


parser = argparse.ArgumentParser(description="Create a Chicken Business admin")
parser.add_argument("--name", required=True)
parser.add_argument("--email", required=True)
args = parser.parse_args()
password = getpass.getpass("Admin password (minimum 8 characters): ")
confirmation = getpass.getpass("Confirm password: ")
if len(password) < 8:
    raise SystemExit("Password must be at least 8 characters.")
if password != confirmation:
    raise SystemExit("Passwords do not match.")

app = create_app()
with app.app_context():
    try:
        database = get_db()
        name = " ".join(args.name.strip().split())
        if not name:
            raise SystemExit("Admin name is required.")
        username = name.casefold()
        database.execute("BEGIN IMMEDIATE")
        username_exists = database.execute(
            "SELECT 1 FROM customers WHERE username = ? UNION ALL SELECT 1 FROM admins WHERE username = ? LIMIT 1",
            (username, username),
        ).fetchone()
        if username_exists:
            database.rollback()
            raise SystemExit("An account with this name already exists.")
        database.execute(
            "INSERT INTO admins(name, username, email, password_hash) VALUES (?, ?, ?, ?)",
            (name, username, args.email.strip().lower(), generate_password_hash(password)),
        )
        database.commit()
        print("Administrator created successfully.")
    except sqlite3.IntegrityError:
        raise SystemExit("The username or email is already in use.")
