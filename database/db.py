"""
Database access and schema management for VisionGuard AI.

Follows the VisionGuard AI Architecture:
- Local SQLite persistence for inspection logs, defect records, and metadata.
- Prepares table schemas for defect inspection persistence and audit logs.
"""

import sqlite3
import os
import json
from typing import Dict, Any, List, Optional


DEFAULT_DB_PATH = os.path.join("data", "visionguard.db")
ALLOWED_STATUSES = ["Open", "Under Review", "Repair in Progress", "Resolved"]
DEFAULT_STATUS = "Open"


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
        status TEXT NOT NULL DEFAULT 'Open',
        defect_type TEXT,
        confidence REAL,
        severity TEXT,
        notes TEXT,
        original_image_path TEXT,
        annotated_image_path TEXT,
        road_name TEXT,
        location_notes TEXT,
        inspection_mode TEXT DEFAULT 'standard',
        confidence_threshold REAL DEFAULT 0.25,
        defect_count INTEGER DEFAULT 0,
        detections_json TEXT DEFAULT '[]',
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
        ("location_notes", "TEXT"),
        ("inspection_mode", "TEXT DEFAULT 'standard'"),
        ("confidence_threshold", "REAL DEFAULT 0.25"),
        ("defect_count", "INTEGER DEFAULT 0"),
        ("detections_json", "TEXT DEFAULT '[]'"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE defect_inspections ADD COLUMN {col_name} {col_type};")

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


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Converts a sqlite3.Row into a dict and parses detections_json safely."""
    d = dict(row)
    # Parse detections_json
    raw_json = d.get("detections_json")
    if raw_json:
        try:
            d["detections"] = json.loads(raw_json)
        except Exception:
            d["detections"] = []
    else:
        d["detections"] = []
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
    location_notes = (data.get("location_notes") or data.get("notes") or "").strip()
    inspection_mode = data.get("inspection_mode", "standard")

    try:
        confidence_threshold = float(data.get("confidence_threshold", 0.25))
    except (TypeError, ValueError):
        confidence_threshold = 0.25

    status = data.get("status", DEFAULT_STATUS)
    if status not in ALLOWED_STATUSES:
        status = DEFAULT_STATUS

    # Check for detections list
    detections = data.get("detections", [])
    if not isinstance(detections, list):
        detections = []

    defect_count = len(detections)

    # Summarize defect types and top confidence
    if defect_count > 0:
        types = sorted(list(set(d.get("distress_category") or d.get("class_name") or "Distress" for d in detections)))
        defect_type = ", ".join(types)
        top_conf = max(float(d.get("confidence", 0.0)) for d in detections)
    else:
        defect_type = "None detected"
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

    cursor.execute("""
    INSERT INTO defect_inspections (
        image_name, file_path, status, defect_type, confidence, notes,
        original_image_path, annotated_image_path, road_name, location_notes,
        inspection_mode, confidence_threshold, defect_count, detections_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        image_name,
        original_image_path,
        status,
        defect_type,
        round(top_conf, 4),
        location_notes,
        original_image_path,
        annotated_image_path,
        road_name,
        location_notes,
        inspection_mode,
        round(confidence_threshold, 4),
        defect_count,
        detections_json,
    ))

    inserted_id = cursor.lastrowid
    conn.commit()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inserted_id,))
    new_row = cursor.fetchone()
    conn.close()

    return row_to_dict(new_row)


def get_inspections(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """Retrieves saved inspections, ordered chronologically newest first."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if status and status in ALLOWED_STATUSES:
        cursor.execute("""
        SELECT * FROM defect_inspections
        WHERE status = ?
        ORDER BY uploaded_at DESC, id DESC
        LIMIT ? OFFSET ?;
        """, (status, limit, offset))
    else:
        cursor.execute("""
        SELECT * FROM defect_inspections
        ORDER BY uploaded_at DESC, id DESC
        LIMIT ? OFFSET ?;
        """, (limit, offset))

    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def get_inspection_by_id(inspection_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Fetches full details of a single inspection record by ID."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    row = cursor.fetchone()
    conn.close()

    return row_to_dict(row) if row else None


def update_inspection_status(
    inspection_id: int,
    new_status: str,
    notes: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Updates the status and optional notes of an inspection record.
    Returns the updated record or None if record does not exist.
    """
    if new_status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'. Must be one of: {ALLOWED_STATUSES}")

    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, notes FROM defect_inspections WHERE id = ?;", (inspection_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    updated_notes = notes if notes is not None else row["notes"]

    cursor.execute("""
    UPDATE defect_inspections
    SET status = ?, notes = ?, location_notes = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (new_status, updated_notes, updated_notes, inspection_id))

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
    cursor.execute("DELETE FROM defect_inspections WHERE id = ?;", (inspection_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


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
