"""
Database access and schema management for VisionGuard AI.

Follows the VisionGuard AI Architecture:
- Local SQLite persistence for inspection logs, defect records, and metadata.
- Prepares table schemas for defect inspection persistence and audit logs.
"""

import sqlite3
import os
from typing import Dict, Any


DEFAULT_DB_PATH = os.path.join("data", "visionguard.db")


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Creates and returns a connection to the SQLite database."""
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initializes the database schema with necessary tables for inspection workflows."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Table for inspection records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS defect_inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_name TEXT NOT NULL,
        file_path TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'uploaded',
        defect_type TEXT,
        confidence REAL,
        severity TEXT,
        notes TEXT
    );
    """)

    # Table for system audit logs / metadata
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_metadata (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Record initialization mark
    cursor.execute("""
    INSERT OR REPLACE INTO system_metadata (key, value)
    VALUES ('schema_version', '1.0');
    """)

    conn.commit()
    conn.close()


def check_db_health(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Checks SQLite connection and reports database readiness."""
    try:
        init_db(db_path)
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) as count FROM defect_inspections;")
        inspections_count = cursor.fetchone()["count"]
        cursor.execute("SELECT value FROM system_metadata WHERE key = 'schema_version';")
        row = cursor.fetchone()
        version = row["value"] if row else "unknown"
        conn.close()
        return {
            "status": "Healthy",
            "db_path": db_path,
            "schema_version": version,
            "records_count": inspections_count,
            "connected": True
        }
    except Exception as e:
        return {
            "status": "Error",
            "db_path": db_path,
            "error": str(e),
            "connected": False
        }
