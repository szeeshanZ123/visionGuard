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
ALLOWED_STATUSES = ["Open", "In Progress", "Under Review", "Repair in Progress", "Resolved"]
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
        area TEXT,
        city TEXT,
        latitude REAL,
        longitude REAL,
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
        ("area", "TEXT"),
        ("city", "TEXT"),
        ("latitude", "REAL"),
        ("longitude", "REAL"),
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
    """Converts a sqlite3.Row into a dict and parses detections_json and location fields safely."""
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
        original_image_path, annotated_image_path, road_name, area, city,
        latitude, longitude, location_notes,
        inspection_mode, confidence_threshold, defect_count, detections_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
        area,
        city,
        latitude,
        longitude,
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
    category: Optional[str] = None,
    search_query: Optional[str] = None,
    has_coords: Optional[bool] = None,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """Retrieves saved inspections with optional filters, ordered chronologically newest first."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    conditions = []
    params = []

    if status and status.strip():
        st = status.strip()
        if st in ALLOWED_STATUSES:
            conditions.append("status = ?")
            params.append(st)
        elif st.lower() in ["in progress group", "in-progress", "active"]:
            conditions.append("status IN ('In Progress', 'Repair in Progress', 'Under Review')")

    if category and category.strip():
        cat = category.strip()
        if cat.lower() in ["sound", "none", "clean"]:
            conditions.append("(defect_count = 0 OR defect_type LIKE '%None%')")
        else:
            conditions.append("(defect_type LIKE ? OR detections_json LIKE ?)")
            params.append(f"%{cat}%")
            params.append(f"%{cat}%")

    if search_query and search_query.strip():
        q_term = f"%{search_query.strip()}%"
        conditions.append("(road_name LIKE ? OR area LIKE ? OR city LIKE ? OR location_notes LIKE ? OR image_name LIKE ?)")
        params.extend([q_term, q_term, q_term, q_term, q_term])

    if has_coords is True:
        conditions.append("latitude IS NOT NULL AND longitude IS NOT NULL")
    elif has_coords is False:
        conditions.append("(latitude IS NULL OR longitude IS NULL)")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
    SELECT * FROM defect_inspections
    {where_clause}
    ORDER BY uploaded_at DESC, id DESC
    LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def get_dashboard_analytics(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Calculates summary metrics and defect category distribution from actual SQLite records."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Total inspections count
    cursor.execute("SELECT COUNT(*) as count FROM defect_inspections;")
    total_inspections = cursor.fetchone()["count"]

    # Total detected defects (sum across all inspections)
    cursor.execute("SELECT COALESCE(SUM(defect_count), 0) as total_defects FROM defect_inspections;")
    total_defects = cursor.fetchone()["total_defects"]

    # Status counts
    cursor.execute("SELECT COUNT(*) as count FROM defect_inspections WHERE status = 'Open';")
    open_records = cursor.fetchone()["count"]

    cursor.execute("""
    SELECT COUNT(*) as count FROM defect_inspections 
    WHERE status IN ('In Progress', 'Repair in Progress', 'Under Review');
    """)
    in_progress_records = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM defect_inspections WHERE status = 'Resolved';")
    resolved_records = cursor.fetchone()["count"]

    # Defect category breakdown:
    # 4 authentic classes: Longitudinal Crack, Transverse Crack, Alligator Crack, Pothole
    category_counts = {
        "Longitudinal Crack": 0,
        "Transverse Crack": 0,
        "Alligator Crack": 0,
        "Pothole": 0,
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

    # Recent inspections (newest 5)
    cursor.execute("""
    SELECT * FROM defect_inspections
    ORDER BY uploaded_at DESC, id DESC
    LIMIT 5;
    """)
    recent_rows = cursor.fetchall()
    recent_inspections = [row_to_dict(r) for r in recent_rows]

    conn.close()

    return {
        "total_inspections": total_inspections,
        "total_defects": total_defects,
        "open_records": open_records,
        "in_progress_records": in_progress_records,
        "resolved_records": resolved_records,
        "defect_categories": category_counts,
        "recent_inspections": recent_inspections,
    }


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


def update_inspection(
    inspection_id: int,
    data: Dict[str, Any],
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Updates an inspection record with status and/or location metadata.
    Returns the updated record or None if record does not exist.
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

    notes = data.get("notes") if "notes" in data else (data.get("location_notes") if "location_notes" in data else current.get("notes"))

    cursor.execute("""
    UPDATE defect_inspections
    SET status = ?, road_name = ?, area = ?, city = ?, latitude = ?, longitude = ?,
        notes = ?, location_notes = ?, updated_at = CURRENT_TIMESTAMP
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
        inspection_id
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
