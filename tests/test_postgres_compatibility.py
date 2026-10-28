"""
Automated unit tests for VisionGuard AI PostgreSQL Adapter and Migration Compatibility.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from database.postgres import (
    adapt_sql,
    sanitize_db_url,
    normalize_postgres_url,
    is_postgres_url,
    PostgresCursorWrapper,
    PostgresConnectionWrapper,
    PostgresConnectionManager,
)
from database.db import is_postgres_backend, get_db_connection, check_db_health
from scripts.migrate_sqlite_to_postgres import run_migration


class TestQueryTranslation:
    def test_adapt_sql_replaces_placeholders(self):
        sqlite_query = "SELECT * FROM defect_inspections WHERE id = ? AND status = ?;"
        pg_query = adapt_sql(sqlite_query, "postgres")
        assert pg_query == "SELECT * FROM defect_inspections WHERE id = %s AND status = %s;"

    def test_adapt_sql_preserves_quoted_question_marks(self):
        query = "SELECT * FROM defect_inspections WHERE notes = 'Is this a defect?' AND id = ?;"
        adapted = adapt_sql(query, "postgres")
        assert adapted == "SELECT * FROM defect_inspections WHERE notes = 'Is this a defect?' AND id = %s;"

    def test_adapt_sql_translates_sqlite_master(self):
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name='complaint_drafts';"
        adapted = adapt_sql(query, "postgres")
        assert "information_schema.tables" in adapted
        assert "sqlite_master" not in adapted.split("AS")[-1]  # aliased or replaced

    def test_adapt_sql_ignores_non_postgres(self):
        query = "SELECT * FROM defect_inspections WHERE id = ?;"
        assert adapt_sql(query, "sqlite") == query


class TestUrlHelpers:
    def test_sanitize_db_url_masks_password(self):
        url = "postgresql://myuser:supersecret123@ep-cool-project.neon.tech/neondb?sslmode=require"
        sanitized = sanitize_db_url(url)
        assert "supersecret123" not in sanitized
        assert ":****@" in sanitized
        assert "myuser" in sanitized
        assert "ep-cool-project.neon.tech" in sanitized

    def test_normalize_postgres_url(self):
        raw = "postgres://user:pass@host/db"
        normalized = normalize_postgres_url(raw)
        assert normalized.startswith("postgresql://")

        # Already postgresql://
        assert normalize_postgres_url("postgresql://u:p@h/d") == "postgresql://u:p@h/d"

    def test_is_postgres_url(self):
        assert is_postgres_url("postgresql://user:pass@host/db") is True
        assert is_postgres_url("postgres://user:pass@host/db") is True
        assert is_postgres_url("data/visionguard.db") is False
        assert is_postgres_url(":memory:") is False
        assert is_postgres_url(None) is False


class TestPostgresCursorWrapper:
    def test_cursor_translates_and_executes(self):
        mock_raw_cur = MagicMock()
        wrapper = PostgresCursorWrapper(mock_raw_cur)

        wrapper.execute("SELECT * FROM defect_inspections WHERE id = ?;", (42,))
        mock_raw_cur.execute.assert_called_once_with(
            "SELECT * FROM defect_inspections WHERE id = %s;",
            (42,),
        )

    def test_cursor_insert_appends_returning_id_and_sets_lastrowid(self):
        mock_raw_cur = MagicMock()
        # Mock returning id = 99
        mock_raw_cur.fetchone.return_value = (99,)
        wrapper = PostgresCursorWrapper(mock_raw_cur)

        wrapper.execute("INSERT INTO defect_inspections (image_name) VALUES (?);", ("test.jpg",))
        # Verify RETURNING id was appended
        call_args = mock_raw_cur.execute.call_args[0]
        assert "RETURNING id" in call_args[0]
        assert wrapper.lastrowid == 99

    def test_cursor_emulates_pragma_table_info(self):
        mock_raw_cur = MagicMock()
        mock_raw_cur.fetchall.return_value = [
            {"cid": 0, "name": "id", "type": "integer"},
            {"cid": 1, "name": "image_name", "type": "text"},
        ]
        wrapper = PostgresCursorWrapper(mock_raw_cur)

        wrapper.execute("PRAGMA table_info(defect_inspections);")
        call_sql = mock_raw_cur.execute.call_args[0][0]
        assert "information_schema.columns" in call_sql
        assert mock_raw_cur.execute.call_args[0][1] == ("defect_inspections",)


class TestDualBackendConfiguration:
    def test_is_postgres_backend_defaults_false(self):
        assert is_postgres_backend("data/visionguard.db") is False
        assert is_postgres_backend(":memory:") is False

    def test_is_postgres_backend_detects_url(self):
        assert is_postgres_backend("postgresql://user:pass@host/db") is True
        assert is_postgres_backend("postgres://user:pass@host/db") is True

    def test_check_db_health_sqlite(self, tmp_path):
        test_db = str(tmp_path / "health_test.db")
        health = check_db_health(test_db)
        assert health["status"] == "Healthy"
        assert health["engine"] == "sqlite"
        assert health["connected"] is True


class TestMigrationScriptDryRun:
    def test_migration_dry_run_does_not_connect_or_write(self, tmp_path):
        # Create small test SQLite db
        import sqlite3
        test_db = tmp_path / "test.db"
        conn = sqlite3.connect(str(test_db))
        conn.execute("CREATE TABLE system_metadata (key TEXT PRIMARY KEY, value TEXT);")
        conn.execute("INSERT INTO system_metadata (key, value) VALUES ('schema_version', '1.0');")
        conn.commit()
        conn.close()

        # Run dry run
        report = run_migration(
            source_db_path=str(test_db),
            target_pg_url="postgresql://fake_user:fake_pass@fake_host/fakedb",
            execute=False,
            confirm_cloud=False,
        )

        assert report["mode"] == "DRY-RUN"
        assert report["status"] == "dry_run_completed"
        assert report["tables"]["system_metadata"]["source_count"] == 1
        assert report["tables"]["system_metadata"]["migrated"] == 0
        assert os.path.exists(report["backup_path"])
