"""SQLite connection helpers for the Flask application."""

import sqlite3

from flask import current_app, g


def get_db():
    """Return one SQLite connection for the current request."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")

    return g.db


def close_db(exception=None):
    """Close the SQLite connection at the end of the request."""
    database = g.pop("db", None)

    if database is not None:
        database.close()
