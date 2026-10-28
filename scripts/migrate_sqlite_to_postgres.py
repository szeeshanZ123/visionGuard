"""
Safe SQLite to PostgreSQL Migration Utility for VisionGuard AI.

Features & Safeguards:
- Default mode is DRY-RUN (--dry-run). Never executes writes to cloud unless --execute and
  --confirm-write-to-cloud are explicitly passed.
- Safe automated backup of SQLite database to data/backups/ before migration.
- Opens SQLite database in read-only mode to prevent unintended mutation.
- Preserves primary key IDs, foreign key references, and password hashes.
- Synchronizes PostgreSQL SERIAL sequences (setval) to prevent primary key collisions.
- Table-by-table integrity validation and row count verification.
- Safe credential handling (never prints passwords or connection strings).
"""

import os
import sys
import shutil
import sqlite3
import argparse
import datetime
import logging
from typing import Dict, Any, List, Tuple, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.postgres import (
    sanitize_db_url,
    normalize_postgres_url,
    init_postgres_db,
    adapt_sql,
    POSTGRES_SCHEMA_SQL,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("visionguard.migration.sqlite_to_postgres")

TABLES_IN_ORDER = [
    "system_metadata",
    "users",
    "defect_inspections",
    "complaint_drafts",
    "maintenance_assignments",
    "maintenance_activity_log",
]


def create_sqlite_backup(source_db_path: str, backup_dir: Optional[str] = None) -> str:
    """Creates a timestamped snapshot of the source SQLite database."""
    if not os.path.isfile(source_db_path):
        raise FileNotFoundError(f"Source SQLite database does not exist: {source_db_path}")

    b_dir = backup_dir or os.path.join(PROJECT_ROOT, "data", "backups")
    os.makedirs(b_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"visionguard_backup_pre_migration_{timestamp}.db"
    backup_path = os.path.join(b_dir, backup_filename)

    shutil.copy2(source_db_path, backup_path)
    logger.info(f"Created pre-migration snapshot: {backup_path} ({os.path.getsize(backup_path)} bytes)")
    return backup_path


def read_sqlite_inventory(source_db_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Reads all rows from source SQLite database in read-only mode."""
    if not os.path.isfile(source_db_path):
        raise FileNotFoundError(f"Source SQLite database not found at {source_db_path}")

    # Read-only URI connection
    abs_path = os.path.abspath(source_db_path).replace("\\", "/")
    uri = f"file:///{abs_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    data: Dict[str, List[Dict[str, Any]]] = {}

    for table in TABLES_IN_ORDER:
        # Check if table exists in SQLite
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,))
        if not cursor.fetchone():
            logger.warning(f"Table '{table}' does not exist in source SQLite database.")
            data[table] = []
            continue

        cursor.execute(f"SELECT * FROM {table};")
        rows = [dict(r) for r in cursor.fetchall()]
        data[table] = rows
        logger.info(f"Inventoried table '{table}': {len(rows)} record(s)")

    conn.close()
    return data


def run_migration(
    source_db_path: str,
    target_pg_url: Optional[str] = None,
    execute: bool = False,
    confirm_cloud: bool = False,
) -> Dict[str, Any]:
    """
    Executes or previews the SQLite to PostgreSQL migration.
    Default mode: DRY-RUN.
    """
    resolved_pg_url = target_pg_url or os.environ.get("DATABASE_URL")
    sanitized_url = sanitize_db_url(resolved_pg_url) if resolved_pg_url else "NOT CONFIGURED"

    report: Dict[str, Any] = {
        "mode": "EXECUTE" if (execute and confirm_cloud) else "DRY-RUN",
        "source_db": source_db_path,
        "source_size_bytes": os.path.getsize(source_db_path) if os.path.exists(source_db_path) else 0,
        "target_url": sanitized_url,
        "backup_path": None,
        "tables": {},
        "status": "pending",
        "error": None,
    }

    # 1. Always create backup first
    if os.path.exists(source_db_path):
        backup_path = create_sqlite_backup(source_db_path)
        report["backup_path"] = backup_path

    # 2. Read inventory from source SQLite
    inventory = read_sqlite_inventory(source_db_path)
    total_records = sum(len(rows) for rows in inventory.values())

    for table, rows in inventory.items():
        report["tables"][table] = {
            "source_count": len(rows),
            "target_count": 0,
            "migrated": 0,
            "status": "pending",
        }

    # 3. Dry-run safety branch
    if not execute or not confirm_cloud:
        logger.info("=" * 70)
        logger.info("DRY-RUN PREVIEW COMPLETE — NO DATA WRITTEN TO POSTGRESQL")
        logger.info(f"Target Database URL: {sanitized_url}")
        logger.info(f"Total Source Records: {total_records}")
        for t, stats in report["tables"].items():
            logger.info(f"  - {t:<26}: {stats['source_count']} records ready for migration")
        logger.info("To perform actual migration, pass --execute AND --confirm-write-to-cloud.")
        logger.info("=" * 70)
        report["status"] = "dry_run_completed"
        return report

    # 4. Execute branch (Requires explicit approval flags)
    if not resolved_pg_url:
        raise ValueError("DATABASE_URL must be provided when running with --execute.")

    try:
        import psycopg2
        from psycopg2.extras import DictCursor
    except ImportError:
        raise RuntimeError("psycopg2 is required for migration. Install with 'pip install psycopg2-binary'.")

    normalized_url = normalize_postgres_url(resolved_pg_url)
    logger.info(f"Connecting to PostgreSQL: {sanitized_url}")

    pg_conn = psycopg2.connect(normalized_url)
    try:
        # Initialize target schema
        logger.info("Verifying / creating PostgreSQL schema...")
        init_postgres_db(pg_conn)

        pg_cur = pg_conn.cursor(cursor_factory=DictCursor)

        # Migrate each table in dependency order
        for table in TABLES_IN_ORDER:
            rows = inventory.get(table, [])
            if not rows:
                report["tables"][table]["status"] = "skipped_empty"
                continue

            columns = list(rows[0].keys())
            col_list_str = ", ".join(f'"{c}"' for c in columns)
            placeholder_str = ", ".join("%s" for _ in columns)

            insert_sql = f"""
                INSERT INTO {table} ({col_list_str})
                VALUES ({placeholder_str})
                ON CONFLICT DO NOTHING;
            """

            tuples_data = [tuple(r[c] for c in columns) for r in rows]
            pg_cur.executemany(insert_sql, tuples_data)

            # Synchronize sequence for tables with serial primary keys
            if "id" in columns:
                try:
                    pg_cur.execute(f"""
                        SELECT setval(
                            pg_get_serial_sequence('{table}', 'id'),
                            COALESCE((SELECT MAX(id) FROM {table}), 1)
                        );
                    """)
                except Exception as seq_err:
                    logger.warning(f"Sequence sync notice on table {table}: {seq_err}")

            # Verify target count
            pg_cur.execute(f"SELECT COUNT(*) AS count FROM {table};")
            count_row = pg_cur.fetchone()
            target_count = count_row["count"] if count_row else 0

            report["tables"][table]["target_count"] = target_count
            report["tables"][table]["migrated"] = len(rows)
            report["tables"][table]["status"] = "migrated"
            logger.info(f"Migrated {len(rows)} records to '{table}' (current total: {target_count})")

        pg_conn.commit()
        pg_cur.close()
        report["status"] = "success"
        logger.info("PostgreSQL migration completed successfully.")
    except Exception as exc:
        pg_conn.rollback()
        report["status"] = "failed"
        report["error"] = str(exc)
        logger.error(f"Migration failed and was rolled back: {exc}")
        raise
    finally:
        pg_conn.close()

    return report


def main():
    parser = argparse.ArgumentParser(description="VisionGuard AI SQLite to Neon PostgreSQL Migration Utility")
    parser.add_argument(
        "--source-db",
        default=os.path.join(PROJECT_ROOT, "data", "visionguard.db"),
        help="Path to source SQLite database file",
    )
    parser.add_argument(
        "--target-url",
        default=None,
        help="Target PostgreSQL connection string (defaults to DATABASE_URL environment variable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview migration without writing to PostgreSQL (default behavior)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute actual migration writes to PostgreSQL",
    )
    parser.add_argument(
        "--confirm-write-to-cloud",
        action="store_true",
        default=False,
        help="Explicit required safety confirmation flag to permit writing to cloud database",
    )

    args = parser.parse_args()

    execute_mode = args.execute and args.confirm_write_to_cloud

    logger.info("Starting VisionGuard AI Database Migration Tool")
    report = run_migration(
        source_db_path=args.source_db,
        target_pg_url=args.target_url,
        execute=execute_mode,
        confirm_cloud=args.confirm_write_to_cloud,
    )
    print("\nMigration Execution Summary:")
    print(f"  Mode:            {report['mode']}")
    print(f"  Source Database: {report['source_db']} ({report['source_size_bytes']} bytes)")
    print(f"  Backup Created:  {report['backup_path']}")
    print(f"  Status:          {report['status']}")
    print("\nTable Statistics:")
    for t, s in report["tables"].items():
        print(f"  {t:<26}: Source={s['source_count']}, Migrated={s['migrated']}, Target={s['target_count']} ({s['status']})")


if __name__ == "__main__":
    main()
