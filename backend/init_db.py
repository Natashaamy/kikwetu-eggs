"""Create the initial SQLite database from schema.sql."""

import argparse
import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = BACKEND_DIR / "instance" / "chicken_business.db"
SCHEMA_FILE = BACKEND_DIR / "schema.sql"


def initialize_database(database_path: Path) -> None:
    """Create the database directory and execute the project's SQL schema."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_FILE.read_text(encoding="utf-8")

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(schema)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the SQLite database.")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"Database path (default: {DEFAULT_DATABASE})",
    )
    args = parser.parse_args()

    database_path = args.database.resolve()
    initialize_database(database_path)
    print(f"Database initialized at: {database_path}")


if __name__ == "__main__":
    main()
