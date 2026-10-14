"""
Database module for VisionGuard AI.
Handles local persistence, schema migrations, and inspection history.
"""

from .db import (
    DEFAULT_DB_PATH,
    get_db_connection,
    init_db,
    check_db_health,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "get_db_connection",
    "init_db",
    "check_db_health",
]
