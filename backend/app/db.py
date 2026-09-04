"""Database helpers supporting PostgreSQL in deployment and SQLite locally."""

import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal

from flask import current_app, g


def _normalize_value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


class CursorAdapter:
    def __init__(self, cursor, postgres):
        self._cursor = cursor
        self._postgres = postgres

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._normalize_row(self._cursor.fetchone())

    def fetchall(self):
        return [self._normalize_row(row) for row in self._cursor.fetchall()]

    def _normalize_row(self, row):
        if row is None or not self._postgres:
            return row
        return {key: _normalize_value(value) for key, value in row.items()}


class DatabaseAdapter:
    """Expose the small connection API used by the existing routes."""

    def __init__(self, connection, postgres=False):
        self.connection = connection
        self.postgres = postgres

    def _sql(self, statement):
        return re.sub(r"\?", "%s", statement) if self.postgres else statement

    def execute(self, statement, parameters=()):
        try:
            return CursorAdapter(
                self.connection.execute(self._sql(statement), parameters),
                self.postgres,
            )
        except Exception as error:
            self._raise_database_error(error)

    def executescript(self, script):
        try:
            if self.postgres:
                cursor = None
                for statement in (part.strip() for part in script.split(";")):
                    if statement:
                        cursor = self.connection.execute(statement)
                return CursorAdapter(cursor, True) if cursor is not None else None
            return self.connection.executescript(script)
        except Exception as error:
            self._raise_database_error(error)

    def begin(self):
        if self.postgres:
            if self.connection.info.transaction_status.name == "IDLE":
                self.connection.execute("BEGIN")
        elif not self.connection.in_transaction:
            self.connection.execute("BEGIN IMMEDIATE")

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()

    @staticmethod
    def _raise_database_error(error):
        try:
            import psycopg
            if isinstance(error, psycopg.IntegrityError):
                raise sqlite3.IntegrityError("Database constraint failed") from error
            if isinstance(error, psycopg.Error):
                raise sqlite3.Error("Database operation failed") from error
        except ImportError:
            pass
        raise error


def get_db():
    """Return one request-scoped PostgreSQL or local SQLite connection."""
    if "db" not in g:
        database_url = current_app.config.get("DATABASE_URL")
        if database_url:
            import psycopg
            from psycopg.rows import dict_row

            if database_url.startswith("postgres://"):
                database_url = "postgresql://" + database_url[len("postgres://"):]
            try:
                connection = psycopg.connect(database_url, row_factory=dict_row)
            except psycopg.Error as error:
                raise sqlite3.Error("Database connection failed") from error
            g.db = DatabaseAdapter(connection, postgres=True)
        else:
            connection = sqlite3.connect(current_app.config["DATABASE"])
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            g.db = DatabaseAdapter(connection)
    return g.db


def is_postgres():
    return bool(current_app.config.get("DATABASE_URL"))


def item_summary_expression():
    """Return the database-specific text aggregation used by order lists."""
    if is_postgres():
        return "STRING_AGG(products.name || ' × ' || CAST(order_items.quantity AS TEXT), ', ')"
    return "GROUP_CONCAT(products.name || ' × ' || order_items.quantity, ', ')"


def close_db(exception=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()
