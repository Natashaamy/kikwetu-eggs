"""Compatibility entry point; the main initializer handles all engines."""

from app import create_app
from init_db import initialize_database


initialize_database(create_app())
