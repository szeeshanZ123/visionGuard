"""
Database access and schema management for VisionGuard AI.

Follows the VisionGuard AI Architecture:
- Local SQLite persistence for inspection logs, defect records, and metadata.
- Prepares table schemas for defect inspection persistence, location metadata,
  maintenance deadlines, and chronological audit activity logs.
"""

import sqlite3
import os
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "data", "visionguard.db")
ALLOWED_STATUSES = ["Open", "In Progress", "Under Review", "Assigned", "Repair in Progress", "Resolved", "Reopened"]
DEFAULT_STATUS = "Open"


def is_postgres_backend(db_path: Optional[str] = None) -> bool:
    """Checks whether the designated database target is PostgreSQL."""
    if db_path and (db_path.startswith("postgres://") or db_path.startswith("postgresql://")):
        return True
    if db_path is None or db_path == DEFAULT_DB_PATH:
        env_url = (os.environ.get("DATABASE_URL") or "").strip().lower()
        if env_url.startswith("postgres://") or env_url.startswith("postgresql://"):
            return True
    return False


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> Any:
    """
    Creates and returns a database connection.
    Supports PostgreSQL when DATABASE_URL or db_path specifies postgres:// or postgresql://,
    otherwise defaults to local SQLite persistence anchored to PROJECT_ROOT.
    """
    if is_postgres_backend(db_path):
        from database.postgres import get_wrapped_postgres_connection
        pg_url = db_path if (db_path and ("postgres://" in db_path or "postgresql://" in db_path)) else os.environ.get("DATABASE_URL")
        return get_wrapped_postgres_connection(pg_url)

    if db_path == ":memory:" or db_path.startswith("file:") or os.path.isabs(db_path):
        resolved_db = db_path
    else:
        resolved_db = os.path.join(PROJECT_ROOT, db_path)

    if resolved_db != ":memory:" and not resolved_db.startswith("file:"):
        db_dir = os.path.dirname(resolved_db)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(resolved_db)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initializes the database schema with necessary tables for inspection workflows."""
    if is_postgres_backend(db_path):
        from database.postgres import init_postgres_db
        conn = get_db_connection(db_path)
        raw_conn = getattr(conn, "_raw_conn", conn)
        init_postgres_db(raw_conn)
        conn.close()
        return

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Table for inspection records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS defect_inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_name TEXT NOT NULL,
        file_path TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'Open',
        defect_type TEXT,
        confidence REAL,
        severity TEXT,
        notes TEXT,
        original_image_path TEXT,
        annotated_image_path TEXT,
        road_name TEXT,
        area TEXT,
        city TEXT,
        latitude REAL,
        longitude REAL,
        location_notes TEXT,
        inspection_mode TEXT DEFAULT 'standard',
        confidence_threshold REAL DEFAULT 0.25,
        defect_count INTEGER DEFAULT 0,
        detections_json TEXT DEFAULT '[]',
        target_repair_date TEXT,
        publication_status TEXT DEFAULT 'pending_review',
        published_at TIMESTAMP,
        published_by_user_id INTEGER,
        published_by_username TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Safe schema migration: check existing columns and add missing ones without dropping data
    cursor.execute("PRAGMA table_info(defect_inspections);")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    columns_to_add = [
        ("original_image_path", "TEXT"),
        ("annotated_image_path", "TEXT"),
        ("road_name", "TEXT"),
        ("area", "TEXT"),
        ("city", "TEXT"),
        ("latitude", "REAL"),
        ("longitude", "REAL"),
        ("location_notes", "TEXT"),
        ("inspection_mode", "TEXT DEFAULT 'standard'"),
        ("confidence_threshold", "REAL DEFAULT 0.25"),
        ("defect_count", "INTEGER DEFAULT 0"),
        ("detections_json", "TEXT DEFAULT '[]'"),
        ("target_repair_date", "TEXT"),
        ("updated_at", "TIMESTAMP"),
        ("created_by_user_id", "INTEGER"),
        ("created_by_username", "TEXT"),
        ("assigned_to_user_id", "INTEGER"),
        ("assigned_to_username", "TEXT"),
        ("assigned_by_user_id", "INTEGER"),
        ("assigned_by_username", "TEXT"),
        ("assigned_at", "TIMESTAMP"),
        ("assignment_instructions", "TEXT"),
        ("assignment_status", "TEXT DEFAULT 'unassigned'"),
        ("assignment_updated_at", "TIMESTAMP"),
        ("inspection_type", "TEXT DEFAULT 'road'"),
        ("publication_status", "TEXT DEFAULT 'pending_review'"),
        ("published_at", "TIMESTAMP"),
        ("published_by_user_id", "INTEGER"),
        ("published_by_username", "TEXT"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE defect_inspections ADD COLUMN {col_name} {col_type};")

    # Table for chronological maintenance audit activity history (Phase 4.4 & 4.6)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS maintenance_activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inspection_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        previous_status TEXT,
        new_status TEXT,
        previous_target_date TEXT,
        new_target_date TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER,
        username TEXT,
        FOREIGN KEY (inspection_id) REFERENCES defect_inspections(id) ON DELETE CASCADE
    );
    """)

    # Safe schema migration for maintenance_activity_log (Phase 4.6 user attribution)
    cursor.execute("PRAGMA table_info(maintenance_activity_log);")
    existing_log_cols = {row["name"] for row in cursor.fetchall()}
    for log_col, log_type in [("user_id", "INTEGER"), ("username", "TEXT")]:
        if log_col not in existing_log_cols:
            cursor.execute(f"ALTER TABLE maintenance_activity_log ADD COLUMN {log_col} {log_type};")

    # Table for maintenance task assignments and reassignments (Phase 4.7)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS maintenance_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inspection_id INTEGER NOT NULL,
        assigned_to_user_id INTEGER NOT NULL,
        assigned_to_username TEXT NOT NULL,
        assigned_by_user_id INTEGER NOT NULL,
        assigned_by_username TEXT NOT NULL,
        instructions TEXT,
        status TEXT NOT NULL DEFAULT 'assigned',
        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        cancelled_at TIMESTAMP,
        cancellation_reason TEXT,
        FOREIGN KEY (inspection_id) REFERENCES defect_inspections(id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_to_user_id) REFERENCES users(id),
        FOREIGN KEY (assigned_by_user_id) REFERENCES users(id)
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_insp ON maintenance_assignments(inspection_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_user_st ON maintenance_assignments(assigned_to_user_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspections_assigned ON defect_inspections(assigned_to_user_id, assignment_status);")

    # Table for user accounts, credentials, and roles (Phase 4.6)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'inspector',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP,
        google_sub TEXT,
        google_email TEXT,
        auth_provider TEXT DEFAULT 'local',
        avatar_url TEXT
    );
    """)

    # Safe additive indexes for case-insensitive username and email uniqueness
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_nocase ON users(username COLLATE NOCASE);")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_nocase ON users(email COLLATE NOCASE) WHERE email IS NOT NULL AND email != '';")

    # Safe additive schema migration for users table (Google OAuth columns)
    cursor.execute("PRAGMA table_info(users);")
    existing_user_cols = {row["name"] for row in cursor.fetchall()}
    user_columns_to_add = [
        ("google_sub", "TEXT"),
        ("google_email", "TEXT"),
        ("auth_provider", "TEXT DEFAULT 'local'"),
        ("avatar_url", "TEXT"),
    ]
    for col_name, col_type in user_columns_to_add:
        if col_name not in existing_user_cols:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")

    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub) WHERE google_sub IS NOT NULL AND google_sub != '';")

    # Table for civic complaint assistance drafts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS complaint_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inspection_id INTEGER NOT NULL UNIQUE,
        complaint_type TEXT NOT NULL DEFAULT 'road_distress',
        recipient_agency TEXT NOT NULL,
        subject TEXT NOT NULL,
        complaint_body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        created_by_user_id INTEGER,
        created_by_username TEXT,
        complainant_name TEXT,
        complainant_contact TEXT,
        submission_channel TEXT,
        submission_reference TEXT,
        submitted_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (inspection_id) REFERENCES defect_inspections(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_complaint_drafts_insp ON complaint_drafts(inspection_id);")

    # Ensure schema migrations for complaint_drafts columns if existing DB
    cursor.execute("PRAGMA table_info(complaint_drafts);")
    existing_cd_cols = {col[1] for col in cursor.fetchall()}
    for col_name, col_type in [
        ("complainant_name", "TEXT"),
        ("complainant_contact", "TEXT"),
        ("submission_channel", "TEXT"),
        ("submission_reference", "TEXT"),
        ("submitted_at", "TIMESTAMP"),
    ]:
        if col_name not in existing_cd_cols:
            cursor.execute(f"ALTER TABLE complaint_drafts ADD COLUMN {col_name} {col_type};")

    # Table for citizen report updates and progress tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inspection_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inspection_id INTEGER NOT NULL,
        user_id INTEGER,
        username TEXT,
        update_type TEXT NOT NULL,
        comment TEXT,
        image_path TEXT,
        verification_status TEXT DEFAULT 'pending_verification',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (inspection_id) REFERENCES defect_inspections(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspection_updates_insp ON inspection_updates (inspection_id);")

    # Table for system audit logs / metadata
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_metadata (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Record initialization mark (maintaining 1.0 schema_version for compatibility)
    cursor.execute("""
    INSERT OR REPLACE INTO system_metadata (key, value)
    VALUES ('schema_version', '1.0');
    """)

    conn.commit()
    conn.close()

    # For default production/application database, run one-time auto-publish migration on eligible geotagged records
    if db_path == DEFAULT_DB_PATH:
        migrate_publish_eligible_historical_inspections(db_path)



def migrate_historical_report_ownership(db_path: str = DEFAULT_DB_PATH) -> int:
    """
    Backfills missing or orphaned created_by_user_id on historical defect_inspections
    and complaint_drafts by matching created_by_username to authentic users in the database.
    Ensures that stable integer user IDs are preferred and authoritative across environments.
    Returns the total number of records successfully migrated.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    migrated_count = 0
    try:
        is_pg = is_postgres_backend(db_path)
        if is_pg:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='users';")
            if not cursor.fetchone():
                return 0
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
            if not cursor.fetchone():
                return 0

        # Backfill defect_inspections where created_by_user_id is NULL or orphaned (not in users)
        cursor.execute("""
            UPDATE defect_inspections
            SET created_by_user_id = (
                SELECT u.id FROM users u
                WHERE LOWER(u.username) = LOWER(defect_inspections.created_by_username)
                LIMIT 1
            )
            WHERE (created_by_user_id IS NULL OR created_by_user_id NOT IN (SELECT id FROM users))
              AND created_by_username IS NOT NULL
              AND TRIM(created_by_username) != ''
              AND EXISTS (
                  SELECT 1 FROM users u
                  WHERE LOWER(u.username) = LOWER(defect_inspections.created_by_username)
              );
        """)
        rc = getattr(cursor, "rowcount", 0)
        migrated_count += rc if rc and rc > 0 else 0

        # Backfill complaint_drafts if table exists
        has_cd = False
        if is_pg:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='complaint_drafts';")
            has_cd = bool(cursor.fetchone())
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='complaint_drafts';")
            has_cd = bool(cursor.fetchone())

        if has_cd:
            cursor.execute("""
                UPDATE complaint_drafts
                SET created_by_user_id = (
                    SELECT u.id FROM users u
                    WHERE LOWER(u.username) = LOWER(complaint_drafts.created_by_username)
                    LIMIT 1
                )
                WHERE (created_by_user_id IS NULL OR created_by_user_id NOT IN (SELECT id FROM users))
                  AND created_by_username IS NOT NULL
                  AND TRIM(created_by_username) != ''
                  AND EXISTS (
                      SELECT 1 FROM users u
                      WHERE LOWER(u.username) = LOWER(complaint_drafts.created_by_username)
                  );
            """)
            rc_cd = getattr(cursor, "rowcount", 0)
            migrated_count += rc_cd if rc_cd and rc_cd > 0 else 0

        conn.commit()
    except Exception as exc:
        # Avoid crashing startup if migration encounters non-fatal schema mismatch
        pass
    finally:
        conn.close()

    return migrated_count


def migrate_publish_eligible_historical_inspections(db_path: str = DEFAULT_DB_PATH) -> int:
    """
    Publishes authentic geotagged historical inspection records that were stuck in pending_review
    so they reflect accurately on the Geospatial Defect Map across local and cloud environments.
    Strictly excludes records lacking valid coordinates or marked as 'hidden'.
    """
    if is_postgres_backend(db_path):
        import database.postgres as pg
        return pg.migrate_publish_eligible_historical_inspections()

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    migrated_count = 0
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='defect_inspections';")
        if not cursor.fetchone():
            return 0

        cursor.execute("""
            UPDATE defect_inspections
            SET publication_status = 'published',
                published_at = COALESCE(published_at, CURRENT_TIMESTAMP)
            WHERE (publication_status IS NULL OR LOWER(publication_status) = 'pending_review')
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
              AND (latitude != 0.0 OR longitude != 0.0)
              AND (latitude BETWEEN -90.0 AND 90.0)
              AND (longitude BETWEEN -180.0 AND 180.0)
              AND LOWER(COALESCE(publication_status, '')) != 'hidden';
        """)
        rc = getattr(cursor, "rowcount", 0)
        migrated_count = rc if rc and rc > 0 else 0
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to auto-publish eligible historical inspections: {e}")
    finally:
        conn.close()
    return migrated_count


def validate_target_repair_date(date_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates optional target repair date.
    Returns: (is_valid, parsed_date_str_or_none, error_message_or_none)
    """
    if date_str is None or str(date_str).strip() == "":
        return True, None, None

    val = str(date_str).strip()
    try:
        dt = datetime.datetime.strptime(val[:10], "%Y-%m-%d")
        if dt.year < 2000 or dt.year > 2100:
            return False, None, "Target repair date year must be between 2000 and 2100."
        return True, dt.date().isoformat(), None
    except (ValueError, TypeError):
        return False, None, "Target repair date must be a valid calendar date in YYYY-MM-DD format."


def compute_maintenance_status(
    target_repair_date_str: Optional[str],
    status: str,
    ref_date: Optional[datetime.date] = None
) -> Dict[str, Any]:
    """
    Computes maintenance urgency and deadline classification.
    Adheres strictly to the rule: Resolved records are NEVER classified as overdue active repairs.
    """
    if ref_date is None:
        ref_date = datetime.date.today()

    if status == "Resolved":
        return {
            "urgency": "resolved",
            "maintenance_urgency": "resolved",
            "label": "Resolved",
            "maintenance_label": "Resolved",
            "is_overdue": False,
            "days_remaining": None,
        }

    if not target_repair_date_str or not str(target_repair_date_str).strip():
        return {
            "urgency": "none",
            "maintenance_urgency": "none",
            "label": "No Target Date",
            "maintenance_label": "No Target Date",
            "is_overdue": False,
            "days_remaining": None,
        }

    try:
        due_date = datetime.datetime.strptime(str(target_repair_date_str)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {
            "urgency": "none",
            "maintenance_urgency": "none",
            "label": "Invalid Date",
            "maintenance_label": "Invalid Date",
            "is_overdue": False,
            "days_remaining": None,
        }

    delta_days = (due_date - ref_date).days
    if delta_days < 0:
        overdue_by = abs(delta_days)
        lbl = f"Overdue by {overdue_by} day{'s' if overdue_by != 1 else ''}"
        return {
            "urgency": "overdue",
            "maintenance_urgency": "overdue",
            "label": lbl,
            "maintenance_label": lbl,
            "is_overdue": True,
            "days_remaining": delta_days,
        }
    elif delta_days == 0:
        return {
            "urgency": "due_today",
            "maintenance_urgency": "due_today",
            "label": "Due Today",
            "maintenance_label": "Due Today",
            "is_overdue": False,
            "days_remaining": 0,
        }
    else:
        lbl = f"Due in {delta_days} day{'s' if delta_days != 1 else ''}"
        return {
            "urgency": "upcoming",
            "maintenance_urgency": "upcoming",
            "label": lbl,
            "maintenance_label": lbl,
            "is_overdue": False,
            "days_remaining": delta_days,
        }


def log_maintenance_activity(
    inspection_id: int,
    action_type: str,
    previous_status: Optional[str] = None,
    new_status: Optional[str] = None,
    previous_target_date: Optional[str] = None,
    new_target_date: Optional[str] = None,
    notes: Optional[str] = None,
    created_at: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> int:
    """Records a chronological maintenance audit activity entry."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if created_at:
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status,
            previous_target_date, new_target_date, notes, created_at,
            user_id, username
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            inspection_id, action_type, previous_status, new_status,
            previous_target_date, new_target_date, (notes or "").strip(), created_at,
            user_id, username
        ))
    else:
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status,
            previous_target_date, new_target_date, notes,
            user_id, username
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            inspection_id, action_type, previous_status, new_status,
            previous_target_date, new_target_date, (notes or "").strip(),
            user_id, username
        ))

    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def get_inspection_activity(inspection_id: int, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Returns chronological maintenance activity logs for an inspection record."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, inspection_id, action_type, previous_status, new_status,
           previous_target_date, new_target_date, notes, created_at,
           user_id, username
    FROM maintenance_activity_log
    WHERE inspection_id = ?
    ORDER BY created_at ASC, id ASC;
    """, (inspection_id,))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("created_at"), (datetime.datetime, datetime.date)):
            item["created_at"] = item["created_at"].isoformat()
        result.append(item)
    return result


ALLOWED_CITIZEN_UPDATE_TYPES = {
    "work_started": "Work Started",
    "road_repaired": "Road Repaired",
    "issue_still_exists": "Issue Still Exists",
    "issue_worse": "Issue Has Become Worse",
    "issue_has_become_worse": "Issue Has Become Worse",
}


def add_inspection_update(
    inspection_id: int,
    update_type: str,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    comment: Optional[str] = None,
    image_path: Optional[str] = None,
    verification_status: str = "pending_verification",
    db_path: str = DEFAULT_DB_PATH
) -> int:
    """Inserts a citizen progress update for an existing inspection."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO inspection_updates (
        inspection_id, user_id, username, update_type,
        comment, image_path, verification_status
    ) VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (
        inspection_id, user_id, username, update_type,
        (comment or "").strip() if comment else None,
        image_path,
        verification_status or "pending_verification"
    ))
    update_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return update_id


def get_inspection_updates(
    inspection_id: int,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """Returns all citizen progress updates for an inspection ordered chronologically."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, inspection_id, user_id, username, update_type,
           comment, image_path, verification_status, created_at
    FROM inspection_updates
    WHERE inspection_id = ?
    ORDER BY created_at ASC, id ASC;
    """, (inspection_id,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("created_at"), (datetime.datetime, datetime.date)):
            item["created_at"] = item["created_at"].isoformat()
        item["update_type_label"] = ALLOWED_CITIZEN_UPDATE_TYPES.get(item.get("update_type"), item.get("update_type"))
        result.append(item)
    return result


def get_inspection_update_by_id(
    update_id: int,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """Fetches a specific inspection update by ID."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, inspection_id, user_id, username, update_type,
           comment, image_path, verification_status, created_at
    FROM inspection_updates
    WHERE id = ?;
    """, (update_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    if isinstance(item.get("created_at"), (datetime.datetime, datetime.date)):
        item["created_at"] = item["created_at"].isoformat()
    item["update_type_label"] = ALLOWED_CITIZEN_UPDATE_TYPES.get(item.get("update_type"), item.get("update_type"))
    return item


def get_latest_updates_for_inspections(
    inspection_ids: List[int],
    db_path: str = DEFAULT_DB_PATH
) -> Dict[int, Dict[str, Any]]:
    """
    Retrieves the most recent citizen progress update for a list of inspection IDs.
    Returns a dictionary mapping inspection_id -> latest_update_dict.
    """
    if not inspection_ids:
        return {}
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in inspection_ids)
    query = f"""
    SELECT id, inspection_id, user_id, username, update_type,
           comment, image_path, verification_status, created_at
    FROM inspection_updates
    WHERE inspection_id IN ({placeholders})
    ORDER BY id ASC;
    """
    result = {}
    try:
        cursor.execute(query, tuple(inspection_ids))
        rows = cursor.fetchall()
        for r in rows:
            d = dict(r)
            if isinstance(d.get("created_at"), (datetime.datetime, datetime.date)):
                d["created_at"] = d["created_at"].isoformat()
            d["update_type_label"] = ALLOWED_CITIZEN_UPDATE_TYPES.get(d.get("update_type"), d.get("update_type"))
            result[d["inspection_id"]] = d
    except Exception as e:
        logger.warning(f"Could not fetch batch updates: {e}")
    finally:
        conn.close()
    return result


def row_to_dict(row: Any, ref_date: Optional[datetime.date] = None) -> Dict[str, Any]:
    """Converts a database row into a dict and parses detections_json, location, and maintenance deadline fields safely."""
    d = dict(row)
    # Convert datetime fields to ISO strings for cross-backend JSON serialization safety
    for dt_key in ("uploaded_at", "updated_at", "assigned_at", "assignment_updated_at", "submitted_at", "created_at", "published_at"):
        if isinstance(d.get(dt_key), (datetime.datetime, datetime.date)):
            d[dt_key] = d[dt_key].isoformat()

    # Parse detections_json
    raw_json = d.get("detections_json")
    if raw_json:
        try:
            d["detections"] = json.loads(raw_json)
        except Exception:
            d["detections"] = []
    else:
        d["detections"] = []

    # Convenience aliases for Gemini inspection telemetry
    sev = d.get("severity") or d.get("preliminary_severity")
    if not sev and d.get("detections"):
        for det in d["detections"]:
            if det.get("severity"):
                sev = det["severity"]
                break
    if not sev and d.get("defect_count", 0) > 0:
        sev = "Moderate"
    d["severity"] = sev
    d["preliminary_severity"] = sev.title() if isinstance(sev, str) else sev

    if not d.get("summary") and d.get("detections"):
        for det in d["detections"]:
            if det.get("description"):
                d["summary"] = det["description"]
                break
    if not d.get("observations") and d.get("detections"):
        obs_pts = [det.get("evidence") or det.get("inspection_points") for det in d["detections"] if det.get("evidence") or det.get("inspection_points")]
        if obs_pts:
            d["observations"] = " • ".join(obs_pts)
    if not d.get("recommendations") and d.get("detections"):
        rec_pts = [det.get("recommended_action") for det in d["detections"] if det.get("recommended_action")]
        if rec_pts:
            d["recommendations"] = " • ".join(rec_pts)

    # Ensure latitude and longitude are float or None
    lat = d.get("latitude")
    if lat is not None:
        try:
            d["latitude"] = float(lat)
        except (ValueError, TypeError):
            d["latitude"] = None
    else:
        d["latitude"] = None

    lon = d.get("longitude")
    if lon is not None:
        try:
            d["longitude"] = float(lon)
        except (ValueError, TypeError):
            d["longitude"] = None
    else:
        d["longitude"] = None

    d["road_name"] = d.get("road_name") or ""
    d["area"] = d.get("area") or ""
    d["city"] = d.get("city") or ""
    d["location_notes"] = d.get("location_notes") or d.get("notes") or ""

    # Maintenance deadline fields (Phase 4.4)
    raw_target_date = d.get("target_repair_date")
    status = d.get("status") or DEFAULT_STATUS
    m_info = compute_maintenance_status(raw_target_date, status, ref_date=ref_date)
    d["target_repair_date"] = raw_target_date if (raw_target_date and str(raw_target_date).strip()) else None
    d["maintenance_urgency"] = m_info["urgency"]
    d["maintenance_label"] = m_info["label"]
    d["is_overdue"] = m_info["is_overdue"]
    d["days_remaining"] = m_info["days_remaining"]

    # Maintenance task assignment fields (Phase 4.7)
    d["assigned_to_user_id"] = d.get("assigned_to_user_id")
    d["assigned_to_username"] = d.get("assigned_to_username")
    d["assigned_by_user_id"] = d.get("assigned_by_user_id")
    d["assigned_by_username"] = d.get("assigned_by_username")
    d["assigned_at"] = d.get("assigned_at")
    d["assignment_instructions"] = d.get("assignment_instructions") or ""
    d["assignment_status"] = d.get("assignment_status") or "unassigned"
    d["assignment_updated_at"] = d.get("assignment_updated_at")

    # Complaint & Civic Filing tracking fields (Phase 4)
    d["complaint_draft_id"] = d.get("complaint_draft_id")
    d["complaint_status"] = d.get("complaint_status") or "none"
    d["submission_channel"] = d.get("complaint_submission_channel") or d.get("submission_channel")
    d["submission_reference"] = d.get("complaint_submission_reference") or d.get("submission_reference")
    d["submitted_at"] = d.get("complaint_submitted_at") or d.get("submitted_at")

    # Public Defect Map publication lifecycle fields
    d["publication_status"] = d.get("publication_status") or "pending_review"
    d["published_at"] = d.get("published_at")
    d["published_by_user_id"] = d.get("published_by_user_id")
    d["published_by_username"] = d.get("published_by_username")

    return d


def save_inspection(data: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Persists an authentic inspection record into defect_inspections.
    Returns the created inspection dictionary.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    image_name = data.get("image_name") or data.get("filename") or "unnamed_image.jpg"
    original_image_path = data.get("original_image_path") or data.get("file_path") or ""
    annotated_image_path = data.get("annotated_image_path") or data.get("processed_file_path") or ""
    road_name = (data.get("road_name") or "").strip()
    area = (data.get("area") or "").strip()
    city = (data.get("city") or "").strip()
    location_notes = (data.get("location_notes") or data.get("notes") or "").strip()
    inspection_mode = data.get("inspection_mode", "standard")

    # Coordinates validation & conversion
    lat_raw = data.get("latitude")
    latitude = None
    if lat_raw is not None and str(lat_raw).strip() != "":
        try:
            latitude = round(float(lat_raw), 6)
        except (ValueError, TypeError):
            latitude = None

    lon_raw = data.get("longitude")
    longitude = None
    if lon_raw is not None and str(lon_raw).strip() != "":
        try:
            longitude = round(float(lon_raw), 6)
        except (ValueError, TypeError):
            longitude = None

    # Target repair date validation (Phase 4.4)
    target_repair_date_raw = data.get("target_repair_date")
    is_valid_date, target_repair_date, date_err = validate_target_repair_date(target_repair_date_raw)
    if not is_valid_date:
        conn.close()
        raise ValueError(date_err)

    try:
        confidence_threshold = float(data.get("confidence_threshold", 0.25))
    except (TypeError, ValueError):
        confidence_threshold = 0.25

    status = data.get("status", DEFAULT_STATUS)
    if status not in ALLOWED_STATUSES:
        status = DEFAULT_STATUS

    # Check for detections list or detections_json
    detections = data.get("detections")
    if not detections and data.get("detections_json"):
        try:
            detections = json.loads(data["detections_json"])
        except Exception:
            detections = []
    if not isinstance(detections, list):
        detections = []

    if detections:
        defect_count = len(detections)
        types = sorted(list(set(d.get("distress_category") or d.get("class_name") or d.get("type") or "Distress" for d in detections)))
        defect_type = ", ".join(types)
        top_conf = max(float(d.get("confidence", 0.0)) for d in detections)
    elif "defect_count" in data:
        defect_count = int(data.get("defect_count", 0))
        defect_type = data.get("defect_type") or ("Distress" if defect_count > 0 else "None detected")
        top_conf = float(data.get("confidence") or data.get("top_confidence") or (0.8 if defect_count > 0 else 0.0))
    else:
        defect_count = 0
        defect_type = data.get("defect_type") or "None detected"
        top_conf = 0.0

    detections_json = json.dumps(detections)

    # Check for duplicate save by matching original_image_path if provided
    if original_image_path:
        cursor.execute(
            "SELECT * FROM defect_inspections WHERE original_image_path = ? AND original_image_path != '' LIMIT 1;",
            (original_image_path,)
        )
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return row_to_dict(existing)

    # Inspection domain / type (road vs home)
    inspection_type = (data.get("inspection_type") or data.get("domain") or "road").strip().lower()
    if inspection_type not in ("road", "home"):
        inspection_type = "road"

    severity_val = data.get("severity") or data.get("preliminary_severity")
    if not severity_val and detections:
        for d in detections:
            if d.get("severity"):
                severity_val = d["severity"]
                break

    pub_status = (data.get("publication_status") or "pending_review").strip().lower()
    if pub_status not in ("pending_review", "published", "hidden"):
        pub_status = "pending_review"
    published_at = data.get("published_at")
    published_by_user_id = data.get("published_by_user_id")
    published_by_username = data.get("published_by_username")

    cursor.execute("""
    INSERT INTO defect_inspections (
        image_name, file_path, status, defect_type, confidence, severity, notes,
        original_image_path, annotated_image_path, road_name, area, city,
        latitude, longitude, location_notes,
        inspection_mode, confidence_threshold, defect_count, detections_json,
        target_repair_date, created_by_user_id, created_by_username, inspection_type,
        publication_status, published_at, published_by_user_id, published_by_username
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        image_name,
        original_image_path,
        status,
        defect_type,
        round(top_conf, 4),
        severity_val,
        location_notes,
        original_image_path,
        annotated_image_path,
        road_name,
        area,
        city,
        latitude,
        longitude,
        location_notes,
        inspection_mode,
        round(confidence_threshold, 4),
        defect_count,
        detections_json,
        target_repair_date,
        data.get("created_by_user_id") or data.get("user_id"),
        data.get("created_by_username") or data.get("username"),
        inspection_type,
        pub_status,
        published_at,
        published_by_user_id,
        published_by_username,
    ))

    inserted_id = cursor.lastrowid
    conn.commit()

    # Log initial creation in maintenance audit history
    u_id = data.get("created_by_user_id") or data.get("user_id")
    u_name = data.get("created_by_username") or data.get("username")
    cursor.execute("""
    INSERT INTO maintenance_activity_log (
        inspection_id, action_type, new_status, new_target_date, notes, user_id, username
    ) VALUES (?, 'created', ?, ?, ?, ?, ?);
    """, (
        inserted_id,
        status,
        target_repair_date,
        location_notes or "Inspection record created and persisted in SQLite.",
        u_id,
        u_name,
    ))
    conn.commit()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inserted_id,))
    new_row = cursor.fetchone()
    conn.close()

    return row_to_dict(new_row)


def get_inspections(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    category: Optional[str] = None,
    search_query: Optional[str] = None,
    has_coords: Optional[bool] = None,
    deadline_filter: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    city: Optional[str] = None,
    area: Optional[str] = None,
    assigned_to_user_id: Optional[int] = None,
    assignment_status: Optional[str] = None,
    created_by_user_id: Optional[int] = None,
    created_by_username: Optional[str] = None,
    ref_date: Optional[datetime.date] = None,
    domain: Optional[str] = None,
    inspection_type: Optional[str] = None,
    complaint_status: Optional[str] = None,
    publication_status: Optional[str] = None,
    sort_by: Optional[str] = "newest",
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """Retrieves saved inspections with optional filters, ordered chronologically newest first."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Check if complaint_drafts table exists
    if is_postgres_backend(db_path):
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='complaint_drafts';")
        has_complaints_table = bool(cursor.fetchone())
    else:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='complaint_drafts';")
        has_complaints_table = bool(cursor.fetchone())

    conditions = []
    params = []

    target_type = inspection_type or domain
    if target_type and target_type.strip() and target_type.strip().lower() != "all":
        conditions.append("LOWER(COALESCE(di.inspection_type, 'road')) = ?")
        params.append(target_type.strip().lower())

    if status and status.strip():
        st = status.strip()
        if st in ALLOWED_STATUSES:
            conditions.append("di.status = ?")
            params.append(st)
        elif st.lower() in ["in progress group", "in-progress", "active"]:
            conditions.append("di.status IN ('In Progress', 'Repair in Progress', 'Under Review', 'Assigned', 'Reopened')")

    if category and category.strip():
        cat = category.strip()
        if cat.lower() in ["sound", "none", "clean"]:
            conditions.append("(di.defect_count = 0 OR di.defect_type LIKE '%None%')")
        else:
            conditions.append("(di.defect_type LIKE ? OR di.detections_json LIKE ?)")
            params.append(f"%{cat}%")
            params.append(f"%{cat}%")

    if search_query and search_query.strip():
        raw_q = search_query.strip().lstrip("#")
        q_term = f"%{search_query.strip()}%"
        if raw_q.isdigit():
            conditions.append("(di.id = ? OR di.road_name LIKE ? OR di.area LIKE ? OR di.city LIKE ? OR di.location_notes LIKE ? OR di.image_name LIKE ?)")
            params.extend([int(raw_q), q_term, q_term, q_term, q_term, q_term])
        else:
            conditions.append("(di.road_name LIKE ? OR di.area LIKE ? OR di.city LIKE ? OR di.location_notes LIKE ? OR di.image_name LIKE ?)")
            params.extend([q_term, q_term, q_term, q_term, q_term])

    if has_coords is True:
        conditions.append("di.latitude IS NOT NULL AND di.longitude IS NOT NULL")
    elif has_coords is False:
        conditions.append("(di.latitude IS NULL OR di.longitude IS NULL)")

    # City & Area filters
    if city and city.strip():
        c_val = city.strip()
        conditions.append("LOWER(di.city) LIKE ?")
        params.append(f"%{c_val.lower()}%")

    if area and area.strip():
        a_val = area.strip()
        conditions.append("LOWER(di.area) LIKE ?")
        params.append(f"%{a_val.lower()}%")

    # Date range filters (date of inspection upload)
    if start_date and str(start_date).strip():
        st_date = str(start_date).strip()[:10]
        conditions.append("date(di.uploaded_at) >= ?")
        params.append(st_date)

    if end_date and str(end_date).strip():
        en_date = str(end_date).strip()[:10]
        conditions.append("date(di.uploaded_at) <= ?")
        params.append(en_date)

    # Maintenance deadline filter (Phase 4.4)
    ref_today = (ref_date or datetime.date.today()).isoformat()
    if deadline_filter and deadline_filter.strip():
        dl = deadline_filter.strip().lower()
        if dl == "overdue":
            conditions.append("di.status != 'Resolved' AND di.target_repair_date IS NOT NULL AND di.target_repair_date != '' AND di.target_repair_date < ?")
            params.append(ref_today)
        elif dl == "due_today":
            conditions.append("di.status != 'Resolved' AND di.target_repair_date = ?")
            params.append(ref_today)
        elif dl == "upcoming":
            conditions.append("di.status != 'Resolved' AND di.target_repair_date > ?")
            params.append(ref_today)
        elif dl == "resolved":
            conditions.append("di.status = 'Resolved'")
        elif dl in ["no_deadline", "none"]:
            conditions.append("(di.target_repair_date IS NULL OR di.target_repair_date = '')")

    # Maintenance task assignment filters (Phase 4.7)
    if assigned_to_user_id is not None:
        conditions.append("di.assigned_to_user_id = ?")
        params.append(assigned_to_user_id)

    if assignment_status and assignment_status.strip() and assignment_status.lower() != "all":
        ast = assignment_status.strip().lower()
        if ast == "unassigned":
            conditions.append("(di.assigned_to_user_id IS NULL OR di.assignment_status = 'unassigned')")
        elif ast in ["assigned", "in_progress", "completed", "cancelled"]:
            conditions.append("di.assignment_status = ?")
            params.append(ast)

    if created_by_user_id is not None and created_by_username and str(created_by_username).strip():
        conditions.append("(di.created_by_user_id = ? OR (di.created_by_user_id IS NULL AND di.created_by_username IS NOT NULL AND LOWER(di.created_by_username) = LOWER(?)))")
        params.extend([created_by_user_id, str(created_by_username).strip()])
    elif created_by_user_id is not None:
        conditions.append("di.created_by_user_id = ?")
        params.append(created_by_user_id)
    elif created_by_username and str(created_by_username).strip():
        conditions.append("(di.created_by_username IS NOT NULL AND LOWER(di.created_by_username) = LOWER(?))")
        params.append(str(created_by_username).strip())

    # Complaint filing status filter (Phase 4)
    if complaint_status and complaint_status.strip() and complaint_status.strip().lower() != "all" and has_complaints_table:
        cst = complaint_status.strip().lower()
        if cst in ("none", "uncreated", "no_draft"):
            conditions.append("(cd.id IS NULL OR cd.status IS NULL)")
        else:
            conditions.append("LOWER(COALESCE(cd.status, '')) = ?")
            params.append(cst)

    # Defect marker publication status filter (Public Defect Map)
    if publication_status and publication_status.strip() and publication_status.strip().lower() != "all":
        conditions.append("LOWER(COALESCE(di.publication_status, 'pending_review')) = ?")
        params.append(publication_status.strip().lower())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Sorting
    sort_by_val = (sort_by or "newest").strip().lower()
    if sort_by_val in ("oldest", "asc"):
        order_clause = "ORDER BY di.uploaded_at ASC, di.id ASC"
    elif sort_by_val in ("defects_desc", "defects"):
        order_clause = "ORDER BY di.defect_count DESC, di.uploaded_at DESC, di.id DESC"
    else:
        order_clause = "ORDER BY di.uploaded_at DESC, di.id DESC"

    if has_complaints_table:
        cursor.execute("PRAGMA table_info(complaint_drafts);")
        cd_cols = {col[1] for col in cursor.fetchall()}
        sub_ch_col = "cd.submission_channel AS complaint_submission_channel" if "submission_channel" in cd_cols else "NULL AS complaint_submission_channel"
        sub_ref_col = "cd.submission_reference AS complaint_submission_reference" if "submission_reference" in cd_cols else "NULL AS complaint_submission_reference"
        sub_at_col = "cd.submitted_at AS complaint_submitted_at" if "submitted_at" in cd_cols else "NULL AS complaint_submitted_at"
        query = f"""
        SELECT di.*,
               cd.id AS complaint_draft_id,
               cd.status AS complaint_status,
               {sub_ch_col},
               {sub_ref_col},
               {sub_at_col}
        FROM defect_inspections di
        LEFT JOIN complaint_drafts cd ON di.id = cd.inspection_id
        {where_clause}
        {order_clause}
        LIMIT ? OFFSET ?;
        """
    else:
        query = f"""
        SELECT di.*
        FROM defect_inspections di
        {where_clause}
        {order_clause}
        LIMIT ? OFFSET ?;
        """

    params.extend([limit, offset])

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(r, ref_date=ref_date) for r in rows]


def get_dashboard_analytics(
    ref_date: Optional[datetime.date] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """Calculates summary metrics, defect category distribution, and maintenance deadlines from actual SQLite records."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Total inspections count
    cursor.execute("SELECT COUNT(*) as count FROM defect_inspections;")
    total_inspections = cursor.fetchone()["count"]

    # Total detected defects (sum across all inspections)
    cursor.execute("SELECT COALESCE(SUM(defect_count), 0) as total_defects FROM defect_inspections;")
    total_defects = cursor.fetchone()["total_defects"]

    # Workflow status distribution
    cursor.execute("SELECT COUNT(*) as count FROM defect_inspections WHERE status = 'Open';")
    open_records = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM defect_inspections WHERE status IN ('In Progress', 'Repair in Progress', 'Under Review');")
    in_progress_records = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM defect_inspections WHERE status = 'Resolved';")
    resolved_records = cursor.fetchone()["count"]

    # Defect categories breakdown (Road domain)
    category_counts = {
        "Longitudinal Crack": 0,
        "Transverse Crack": 0,
        "Alligator Crack": 0,
        "Pothole": 0,
    }

    # Building defect categories breakdown (Home domain)
    building_category_counts = {
        "Wall Crack": 0,
        "Dampness": 0,
        "Peeling Paint": 0,
        "Spalling": 0,
    }

    cursor.execute("SELECT detections_json, defect_type FROM defect_inspections WHERE defect_count > 0;")
    rows = cursor.fetchall()

    for row in rows:
        dets_raw = row["detections_json"]
        parsed = False
        if dets_raw:
            try:
                dets = json.loads(dets_raw)
                if isinstance(dets, list) and len(dets) > 0:
                    parsed = True
                    for d in dets:
                        cat = (d.get("distress_category") or "").lower()
                        cls_name = (d.get("class_name") or "").lower()
                        if "longitudinal" in cat or "d00" in cls_name:
                            category_counts["Longitudinal Crack"] += 1
                        elif "transverse" in cat or "d10" in cls_name:
                            category_counts["Transverse Crack"] += 1
                        elif "alligator" in cat or "d20" in cls_name:
                            category_counts["Alligator Crack"] += 1
                        elif "pothole" in cat or "d40" in cls_name:
                            category_counts["Pothole"] += 1
                        elif "wall" in cat or "wall_crack" in cls_name:
                            building_category_counts["Wall Crack"] += 1
                        elif "damp" in cat or "water" in cat or "damp" in cls_name:
                            building_category_counts["Dampness"] += 1
                        elif "peel" in cat or "paint" in cat or "plaster" in cat or "peel" in cls_name:
                            building_category_counts["Peeling Paint"] += 1
                        elif "spall" in cat or "surface" in cat or "spall" in cls_name:
                            building_category_counts["Spalling"] += 1
            except Exception:
                parsed = False

        if not parsed:
            dt = (row["defect_type"] or "").lower()
            if "longitudinal" in dt:
                category_counts["Longitudinal Crack"] += 1
            if "transverse" in dt:
                category_counts["Transverse Crack"] += 1
            if "alligator" in dt:
                category_counts["Alligator Crack"] += 1
            if "pothole" in dt:
                category_counts["Pothole"] += 1
            if "wall" in dt:
                building_category_counts["Wall Crack"] += 1
            if "damp" in dt or "water" in dt:
                building_category_counts["Dampness"] += 1
            if "peel" in dt or "paint" in dt or "plaster" in dt:
                building_category_counts["Peeling Paint"] += 1
            if "spall" in dt:
                building_category_counts["Spalling"] += 1

    # Maintenance Deadlines Metrics (Phase 4.4)
    today_str = (ref_date or datetime.date.today()).isoformat()

    cursor.execute("""
    SELECT COUNT(*) as count FROM defect_inspections
    WHERE status != 'Resolved' AND target_repair_date IS NOT NULL AND target_repair_date != '' AND target_repair_date < ?;
    """, (today_str,))
    overdue_count = cursor.fetchone()["count"]

    cursor.execute("""
    SELECT COUNT(*) as count FROM defect_inspections
    WHERE status != 'Resolved' AND target_repair_date = ?;
    """, (today_str,))
    due_today_count = cursor.fetchone()["count"]

    cursor.execute("""
    SELECT COUNT(*) as count FROM defect_inspections
    WHERE status != 'Resolved' AND target_repair_date > ?;
    """, (today_str,))
    upcoming_count = cursor.fetchone()["count"]

    cursor.execute("""
    SELECT COUNT(*) as count FROM defect_inspections
    WHERE target_repair_date IS NULL OR target_repair_date = '';
    """)
    no_deadline_count = cursor.fetchone()["count"]

    # Actionable upcoming / overdue records list (top 5)
    cursor.execute("""
    SELECT * FROM defect_inspections
    WHERE status != 'Resolved' AND target_repair_date IS NOT NULL AND target_repair_date != ''
    ORDER BY target_repair_date ASC
    LIMIT 5;
    """)
    actionable_rows = cursor.fetchall()
    actionable_maintenance = [row_to_dict(r, ref_date=ref_date) for r in actionable_rows]

    # Recent inspections (newest 5)
    cursor.execute("""
    SELECT * FROM defect_inspections
    ORDER BY uploaded_at DESC, id DESC
    LIMIT 5;
    """)
    recent_rows = cursor.fetchall()
    recent_inspections = [row_to_dict(r, ref_date=ref_date) for r in recent_rows]

    conn.close()

    return {
        "total_inspections": total_inspections,
        "total_defects": total_defects,
        "open_records": open_records,
        "in_progress_records": in_progress_records,
        "resolved_records": resolved_records,
        "defect_categories": category_counts,
        "building_defect_categories": building_category_counts,
        "recent_inspections": recent_inspections,
        "maintenance_summary": {
            "overdue_count": overdue_count,
            "due_today_count": due_today_count,
            "upcoming_count": upcoming_count,
            "resolved_count": resolved_records,
            "no_deadline_count": no_deadline_count,
            "actionable_count": overdue_count + due_today_count + upcoming_count,
            "actionable_maintenance": actionable_maintenance,
        }
    }


def get_inspection_by_id(
    inspection_id: int,
    ref_date: Optional[datetime.date] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """Fetches full details of a single inspection record by ID, including activity history."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    res = row_to_dict(row, ref_date=ref_date)
    cursor.execute("""
    SELECT * FROM maintenance_activity_log
    WHERE inspection_id = ?
    ORDER BY created_at ASC, id ASC;
    """, (inspection_id,))
    res["activity_log"] = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT * FROM maintenance_assignments
    WHERE inspection_id = ?
    ORDER BY assigned_at ASC, id ASC;
    """, (inspection_id,))
    res["assignments"] = [dict(r) for r in cursor.fetchall()]

    if res.get("assigned_to_user_id"):
        cursor.execute("SELECT is_active FROM users WHERE id = ?;", (res["assigned_to_user_id"],))
        u_row = cursor.fetchone()
        res["assigned_to_user_active"] = bool(u_row["is_active"]) if u_row else False
    else:
        res["assigned_to_user_active"] = None

    # Attach complaint draft summary if complaint_drafts table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='complaint_drafts';")
    if cursor.fetchone():
        cursor.execute("SELECT * FROM complaint_drafts WHERE inspection_id = ?;", (inspection_id,))
        cd_row = cursor.fetchone()
        if cd_row:
            cd_dict = dict(cd_row)
            res["complaint_draft"] = cd_dict
            res["complaint_status"] = cd_dict.get("status") or "none"
            res["submission_channel"] = cd_dict.get("submission_channel")
            res["submission_reference"] = cd_dict.get("submission_reference")
            res["submitted_at"] = cd_dict.get("submitted_at")
        else:
            res["complaint_draft"] = None
            res["complaint_status"] = "none"
    else:
        res["complaint_draft"] = None
        res["complaint_status"] = "none"

    conn.close()

    # Attach citizen reported updates
    res["citizen_updates"] = get_inspection_updates(inspection_id, db_path=db_path)

    return res


def get_citizen_dashboard_summary(
    user_id: int,
    username: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, int]:
    """Calculates summary counts for a citizen's own inspections and complaint submissions."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if username and str(username).strip():
        norm_u = str(username).strip()
        owner_filter = "(created_by_user_id = ? OR (created_by_user_id IS NULL AND created_by_username IS NOT NULL AND LOWER(created_by_username) = LOWER(?)))"
        owner_params = (user_id, norm_u)
        join_owner_filter = "(di.created_by_user_id = ? OR (di.created_by_user_id IS NULL AND di.created_by_username IS NOT NULL AND LOWER(di.created_by_username) = LOWER(?)))"
    else:
        owner_filter = "created_by_user_id = ?"
        owner_params = (user_id,)
        join_owner_filter = "di.created_by_user_id = ?"

    cursor.execute(f"SELECT COUNT(*) as count FROM defect_inspections WHERE {owner_filter};", owner_params)
    total = cursor.fetchone()["count"]

    cursor.execute(f"SELECT COUNT(*) as count FROM defect_inspections WHERE {owner_filter} AND status = 'Open';", owner_params)
    open_count = cursor.fetchone()["count"]

    cursor.execute(f"SELECT COUNT(*) as count FROM defect_inspections WHERE {owner_filter} AND status IN ('Under Review', 'In Progress', 'Repair in Progress', 'Assigned', 'Reopened');", owner_params)
    under_review_count = cursor.fetchone()["count"]

    cursor.execute(f"SELECT COUNT(*) as count FROM defect_inspections WHERE {owner_filter} AND status = 'Resolved';", owner_params)
    resolved_count = cursor.fetchone()["count"]

    submitted_complaints = 0
    if is_postgres_backend(db_path):
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='complaint_drafts';")
        has_table = bool(cursor.fetchone())
    else:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='complaint_drafts';")
        has_table = bool(cursor.fetchone())

    if has_table:
        cursor.execute(f"""
        SELECT COUNT(*) as count FROM complaint_drafts cd
        JOIN defect_inspections di ON cd.inspection_id = di.id
        WHERE {join_owner_filter} AND cd.status = 'submitted';
        """, owner_params)
        submitted_complaints = cursor.fetchone()["count"]

    conn.close()

    return {
        "total": total,
        "open": open_count,
        "under_review": under_review_count,
        "resolved": resolved_count,
        "submitted_complaints": submitted_complaints,
    }


def update_inspection_status(
    inspection_id: int,
    new_status: str,
    notes: Optional[str] = None,
    target_repair_date: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Updates the status and optional notes/target repair date of an inspection record.
    Logs transition activity to maintenance_activity_log.
    """
    if new_status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'. Must be one of: {ALLOWED_STATUSES}")

    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, status, notes, target_repair_date FROM defect_inspections WHERE id = ?;", (inspection_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    old_status = row["status"]
    old_target_date = row["target_repair_date"]
    updated_notes = notes if notes is not None else row["notes"]

    # Phase 5 Server-side Lifecycle & Evidence Validations
    if new_status == "Resolved":
        clean_notes = (notes or "").strip()
        if not clean_notes:
            conn.close()
            raise ValueError("A resolution note detailing repair actions and verification evidence is required before marking an inspection as Resolved.")

    if new_status == "Reopened":
        clean_notes = (notes or "").strip()
        if not clean_notes:
            conn.close()
            raise ValueError("Notes explaining the reason for reopening are required before marking an inspection as Reopened.")

    if old_status == "Resolved" and new_status not in ["Resolved", "Reopened", "Under Review"]:
        conn.close()
        raise ValueError(f"Cannot transition directly from 'Resolved' to '{new_status}'. The inspection must be marked as 'Reopened' first.")

    new_target_date = old_target_date
    if target_repair_date is not None:
        is_valid_date, parsed_date, date_err = validate_target_repair_date(target_repair_date)
        if not is_valid_date:
            conn.close()
            raise ValueError(date_err)
        new_target_date = parsed_date

    cursor.execute("""
    UPDATE defect_inspections
    SET status = ?, notes = ?, location_notes = ?, target_repair_date = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (new_status, updated_notes, updated_notes, new_target_date, inspection_id))

    # Log activity
    if new_status != old_status:
        if new_status == "Resolved":
            action_type = "resolved"
        elif new_status == "Reopened":
            action_type = "reopened"
        else:
            action_type = "status_change"
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status, notes, user_id, username
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (inspection_id, action_type, old_status, new_status, (notes or "").strip(), user_id, username))
    elif notes and notes.strip() != (row["notes"] or "").strip():
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status, notes, user_id, username
        ) VALUES (?, 'repair_notes_added', ?, ?, ?, ?, ?);
        """, (inspection_id, old_status, old_status, (notes or "").strip(), user_id, username))

    if new_target_date != old_target_date:
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_target_date, new_target_date, notes, user_id, username
        ) VALUES (?, 'target_date_change', ?, ?, ?, ?, ?);
        """, (inspection_id, old_target_date, new_target_date, (notes or "").strip(), user_id, username))

    conn.commit()

    if new_status != old_status:
        try:
            from database.assignments import sync_assignment_status_with_workflow
            sync_assignment_status_with_workflow(inspection_id, new_status, db_path=db_path)
        except Exception:
            pass

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    updated_row = cursor.fetchone()
    conn.close()

    return row_to_dict(updated_row)


def update_inspection(
    inspection_id: int,
    data: Dict[str, Any],
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Updates an inspection record with status, location, target deadline, and/or notes.
    Logs transition events to maintenance_activity_log.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    current = dict(row)
    new_status = data.get("status") if "status" in data else current["status"]
    if new_status not in ALLOWED_STATUSES:
        conn.close()
        raise ValueError(f"Invalid status '{new_status}'. Must be one of: {ALLOWED_STATUSES}")

    road_name = data.get("road_name") if "road_name" in data else current.get("road_name")
    area = data.get("area") if "area" in data else current.get("area")
    city = data.get("city") if "city" in data else current.get("city")

    if "latitude" in data:
        lat_raw = data.get("latitude")
        latitude = round(float(lat_raw), 6) if (lat_raw is not None and str(lat_raw).strip() != "") else None
    else:
        latitude = current.get("latitude")

    if "longitude" in data:
        lon_raw = data.get("longitude")
        longitude = round(float(lon_raw), 6) if (lon_raw is not None and str(lon_raw).strip() != "") else None
    else:
        longitude = current.get("longitude")

    # Target repair date (Phase 4.4)
    old_target_date = current.get("target_repair_date")
    if "target_repair_date" in data:
        is_valid_date, parsed_date, date_err = validate_target_repair_date(data.get("target_repair_date"))
        if not is_valid_date:
            conn.close()
            raise ValueError(date_err)
        new_target_date = parsed_date
    else:
        new_target_date = old_target_date

    notes = data.get("notes") if "notes" in data else (data.get("location_notes") if "location_notes" in data else current.get("notes"))

    old_status = current.get("status")

    # Phase 5 Server-side Lifecycle & Evidence Validations
    if new_status == "Resolved":
        clean_notes = (notes or "").strip()
        if not clean_notes:
            conn.close()
            raise ValueError("A resolution note detailing repair actions and verification evidence is required before marking an inspection as Resolved.")

    if new_status == "Reopened":
        clean_notes = (notes or "").strip()
        if not clean_notes:
            conn.close()
            raise ValueError("Notes explaining the reason for reopening are required before marking an inspection as Reopened.")

    if old_status == "Resolved" and new_status not in ["Resolved", "Reopened", "Under Review"]:
        conn.close()
        raise ValueError(f"Cannot transition directly from 'Resolved' to '{new_status}'. The inspection must be marked as 'Reopened' first.")

    cursor.execute("""
    UPDATE defect_inspections
    SET status = ?, road_name = ?, area = ?, city = ?, latitude = ?, longitude = ?,
        notes = ?, location_notes = ?, target_repair_date = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (
        new_status,
        (road_name or "").strip() if road_name else "",
        (area or "").strip() if area else "",
        (city or "").strip() if city else "",
        latitude,
        longitude,
        (notes or "").strip() if notes else "",
        (notes or "").strip() if notes else "",
        new_target_date,
        inspection_id
    ))

    # Activity log
    u_id = user_id or data.get("user_id")
    u_name = username or data.get("username")

    if new_status != old_status:
        if new_status == "Resolved":
            action_type = "resolved"
        elif new_status == "Reopened":
            action_type = "reopened"
        else:
            action_type = "status_change"
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status, notes, user_id, username
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (inspection_id, action_type, old_status, new_status, (notes or "").strip(), u_id, u_name))
    elif notes and (notes or "").strip() != (current.get("notes") or "").strip():
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status, notes, user_id, username
        ) VALUES (?, 'repair_notes_added', ?, ?, ?, ?, ?);
        """, (inspection_id, old_status, old_status, (notes or "").strip(), u_id, u_name))

    if new_target_date != old_target_date:
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_target_date, new_target_date, notes, user_id, username
        ) VALUES (?, 'target_date_change', ?, ?, ?, ?, ?);
        """, (inspection_id, old_target_date, new_target_date, (notes or "").strip(), u_id, u_name))

    conn.commit()

    if new_status != old_status:
        try:
            from database.assignments import sync_assignment_status_with_workflow
            sync_assignment_status_with_workflow(inspection_id, new_status, db_path=db_path)
        except Exception:
            pass

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    updated_row = cursor.fetchone()
    conn.close()
    return row_to_dict(updated_row)


def update_inspection_publication_status(
    inspection_id: int,
    publication_status: str,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Updates the publication status of an inspection record ('pending_review', 'published', 'hidden').
    Restricted to authorized administrators and inspectors.
    Logs transition activity to maintenance_activity_log.
    """
    clean_status = (publication_status or "").strip().lower()
    if clean_status not in ("pending_review", "published", "hidden"):
        raise ValueError(f"Invalid publication status '{publication_status}'. Must be one of: 'pending_review', 'published', 'hidden'.")

    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    old_pub_status = row["publication_status"] or "pending_review"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    published_at_val = now_iso if clean_status == "published" else (row["published_at"] if clean_status == old_pub_status else None)

    cursor.execute("""
    UPDATE defect_inspections
    SET publication_status = ?,
        published_at = ?,
        published_by_user_id = ?,
        published_by_username = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (
        clean_status,
        published_at_val,
        user_id,
        username,
        inspection_id
    ))

    # Log to maintenance audit trail
    cursor.execute("""
    INSERT INTO maintenance_activity_log (
        inspection_id, action_type, previous_status, new_status, notes, user_id, username
    ) VALUES (?, 'publication_status_change', ?, ?, ?, ?, ?);
    """, (
        inspection_id,
        old_pub_status,
        clean_status,
        f"Defect marker publication status updated to '{clean_status}' by {username or 'Authority'}.",
        user_id,
        username
    ))

    conn.commit()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    updated_row = cursor.fetchone()
    conn.close()

    return row_to_dict(updated_row)


def delete_inspection(inspection_id: int, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Deletes an inspection record by ID. Returns True if row was deleted."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM complaint_drafts WHERE inspection_id = ?;", (inspection_id,))
    cursor.execute("DELETE FROM defect_inspections WHERE id = ?;", (inspection_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def check_db_health(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Checks database connection and reports database readiness and engine type."""
    is_pg = is_postgres_backend(db_path)
    engine_name = "postgres" if is_pg else "sqlite"
    display_path = db_path
    if is_pg:
        from database.postgres import sanitize_db_url
        raw_url = db_path if (db_path and ("postgres://" in db_path or "postgresql://" in db_path)) else (os.environ.get("DATABASE_URL") or "")
        display_path = sanitize_db_url(raw_url)

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
            "engine": engine_name,
            "db_path": display_path,
            "schema_version": version,
            "records_count": inspections_count,
            "connected": True
        }
    except Exception as e:
        return {
            "status": "Error",
            "engine": engine_name,
            "db_path": display_path,
            "error": str(e),
            "connected": False
        }
