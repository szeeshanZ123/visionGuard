"""Unit tests for SQLite database initialization and health checks."""

import os
import sqlite3
import pytest
from src.database.db import get_db_connection, init_db, check_db_health


def test_database_initialization(tmp_path):
    """Verifies that init_db creates all required tables and sets schema version."""
    test_db_path = str(tmp_path / "test_visionguard.db")

    init_db(test_db_path)
    assert os.path.exists(test_db_path)

    conn = get_db_connection(test_db_path)
    cursor = conn.cursor()

    # Verify tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row["name"] for row in cursor.fetchall()]

    assert "defect_inspections" in tables
    assert "system_metadata" in tables

    # Verify schema version record
    cursor.execute("SELECT value FROM system_metadata WHERE key = 'schema_version';")
    row = cursor.fetchone()
    assert row is not None
    assert row["value"] == "1.0"

    conn.close()


def test_database_health_check(tmp_path):
    """Verifies that check_db_health reports accurate status."""
    test_db_path = str(tmp_path / "health_check.db")
    health = check_db_health(test_db_path)

    assert health["connected"] is True
    assert health["status"] == "Healthy"
    assert health["schema_version"] == "1.0"
    assert health["records_count"] == 0
