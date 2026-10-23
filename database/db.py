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
        target_repair_date TEXT,
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
        last_login_at TIMESTAMP
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

    # Record initialization mark (maintaining 1.0 schema_version for compatibility)
    cursor.execute("""
    INSERT OR REPLACE INTO system_metadata (key, value)
    VALUES ('schema_version', '1.0');
    """)

    conn.commit()
    conn.close()


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
    return [dict(r) for r in rows]


def row_to_dict(row: sqlite3.Row, ref_date: Optional[datetime.date] = None) -> Dict[str, Any]:
    """Converts a sqlite3.Row into a dict and parses detections_json, location, and maintenance deadline fields safely."""
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

    # Check for detections list
    detections = data.get("detections", [])
    if not isinstance(detections, list):
        detections = []

    if detections:
        defect_count = len(detections)
        types = sorted(list(set(d.get("distress_category") or d.get("class_name") or "Distress" for d in detections)))
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

    cursor.execute("""
    INSERT INTO defect_inspections (
        image_name, file_path, status, defect_type, confidence, notes,
        original_image_path, annotated_image_path, road_name, area, city,
        latitude, longitude, location_notes,
        inspection_mode, confidence_threshold, defect_count, detections_json,
        target_repair_date, created_by_user_id, created_by_username
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
        target_repair_date,
        data.get("created_by_user_id") or data.get("user_id"),
        data.get("created_by_username") or data.get("username"),
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
    ref_date: Optional[datetime.date] = None,
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

    # City & Area filters
    if city and city.strip():
        c_val = city.strip()
        conditions.append("LOWER(city) LIKE ?")
        params.append(f"%{c_val.lower()}%")

    if area and area.strip():
        a_val = area.strip()
        conditions.append("LOWER(area) LIKE ?")
        params.append(f"%{a_val.lower()}%")

    # Date range filters (date of inspection upload)
    if start_date and str(start_date).strip():
        st_date = str(start_date).strip()[:10]
        conditions.append("date(uploaded_at) >= ?")
        params.append(st_date)

    if end_date and str(end_date).strip():
        en_date = str(end_date).strip()[:10]
        conditions.append("date(uploaded_at) <= ?")
        params.append(en_date)

    # Maintenance deadline filter (Phase 4.4)
    ref_today = (ref_date or datetime.date.today()).isoformat()
    if deadline_filter and deadline_filter.strip():
        dl = deadline_filter.strip().lower()
        if dl == "overdue":
            # Active/unresolved defects whose target repair date has passed
            conditions.append("status != 'Resolved' AND target_repair_date IS NOT NULL AND target_repair_date != '' AND target_repair_date < ?")
            params.append(ref_today)
        elif dl == "due_today":
            conditions.append("status != 'Resolved' AND target_repair_date = ?")
            params.append(ref_today)
        elif dl == "upcoming":
            conditions.append("status != 'Resolved' AND target_repair_date > ?")
            params.append(ref_today)
        elif dl == "resolved":
            conditions.append("status = 'Resolved'")
        elif dl in ["no_deadline", "none"]:
            conditions.append("(target_repair_date IS NULL OR target_repair_date = '')")

    # Maintenance task assignment filters (Phase 4.7)
    if assigned_to_user_id is not None:
        conditions.append("assigned_to_user_id = ?")
        params.append(assigned_to_user_id)

    if assignment_status and assignment_status.strip() and assignment_status.lower() != "all":
        ast = assignment_status.strip().lower()
        if ast == "unassigned":
            conditions.append("(assigned_to_user_id IS NULL OR assignment_status = 'unassigned')")
        elif ast in ["assigned", "in_progress", "completed", "cancelled"]:
            conditions.append("assignment_status = ?")
            params.append(ast)

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

    # Defect categories breakdown
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

    conn.close()
    return res


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
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status, notes, user_id, username
        ) VALUES (?, 'status_change', ?, ?, ?, ?, ?);
        """, (inspection_id, old_status, new_status, (notes or "").strip(), user_id, username))

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

    old_status = current.get("status")
    if new_status != old_status:
        cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status, notes, user_id, username
        ) VALUES (?, 'status_change', ?, ?, ?, ?, ?);
        """, (inspection_id, old_status, new_status, (notes or "").strip(), u_id, u_name))

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
