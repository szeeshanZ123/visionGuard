"""
VisionGuard AI - Maintenance Task Assignment & Work Queue Module (Phase 4.7).

Provides database models, assignment state transitions, maintenance queue queries,
assignment cancellation, reassignment with audit history, and assignment-level
permission checks.
"""

import sqlite3
import datetime
from typing import Dict, Any, List, Optional, Tuple

from database.db import (
    get_db_connection,
    init_db,
    row_to_dict,
    DEFAULT_DB_PATH,
    log_maintenance_activity,
)
from database.auth import (
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    ROLE_MAINTENANCE,
    get_user_by_id,
)

# Assignment status definitions
ASSIGNMENT_STATUS_UNASSIGNED = "unassigned"
ASSIGNMENT_STATUS_ASSIGNED = "assigned"
ASSIGNMENT_STATUS_IN_PROGRESS = "in_progress"
ASSIGNMENT_STATUS_COMPLETED = "completed"
ASSIGNMENT_STATUS_CANCELLED = "cancelled"

ALLOWED_ASSIGNMENT_STATUSES = [
    ASSIGNMENT_STATUS_UNASSIGNED,
    ASSIGNMENT_STATUS_ASSIGNED,
    ASSIGNMENT_STATUS_IN_PROGRESS,
    ASSIGNMENT_STATUS_COMPLETED,
    ASSIGNMENT_STATUS_CANCELLED,
]

ASSIGNMENT_STATUS_DISPLAY = {
    ASSIGNMENT_STATUS_UNASSIGNED: "Unassigned",
    ASSIGNMENT_STATUS_ASSIGNED: "Assigned",
    ASSIGNMENT_STATUS_IN_PROGRESS: "Work In Progress",
    ASSIGNMENT_STATUS_COMPLETED: "Completed",
    ASSIGNMENT_STATUS_CANCELLED: "Cancelled",
}


def list_active_maintenance_staff(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Returns active users belonging to the Maintenance Staff role."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, email, role, is_active, last_login_at
        FROM users
        WHERE role = ? AND is_active = 1
        ORDER BY username ASC;
    """, (ROLE_MAINTENANCE,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_inspection_assignment_history(inspection_id: int, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieves all assignment records chronologically for an inspection."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, inspection_id, assigned_to_user_id, assigned_to_username,
               assigned_by_user_id, assigned_by_username, instructions, status,
               assigned_at, updated_at, completed_at, cancelled_at, cancellation_reason
        FROM maintenance_assignments
        WHERE inspection_id = ?
        ORDER BY assigned_at ASC, id ASC;
    """, (inspection_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def assign_inspection_task(
    inspection_id: int,
    assigned_to_user_id: int,
    assigned_by_user_id: int,
    instructions: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Assigns or reassigns an inspection to an active Maintenance Staff user.
    Records audit entry in maintenance_activity_log and persists task in maintenance_assignments.
    """
    init_db(db_path)

    # 1. Validate assignee user
    assignee = get_user_by_id(assigned_to_user_id, db_path=db_path)
    if not assignee:
        raise ValueError(f"Target user with ID {assigned_to_user_id} does not exist.")
    if not assignee.get("is_active"):
        raise ValueError(f"User '{assignee['username']}' is deactivated and cannot receive new maintenance task assignments.")
    if assignee.get("role") != ROLE_MAINTENANCE:
        raise ValueError(f"User '{assignee['username']}' has role '{assignee.get('role')}'. Only Maintenance Staff can receive repair assignments.")

    # 2. Validate assigner admin
    assigner = get_user_by_id(assigned_by_user_id, db_path=db_path)
    assigner_username = assigner["username"] if assigner else "Administrator"

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 3. Fetch inspection
    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    insp_row = cursor.fetchone()
    if not insp_row:
        conn.close()
        raise ValueError(f"Inspection record #{inspection_id} not found.")

    curr_assigned_to_id = insp_row["assigned_to_user_id"]
    curr_assigned_to_name = insp_row["assigned_to_username"]
    insp_status = insp_row["status"] or "Open"
    clean_instructions = (instructions or "").strip()

    # Determine assignment status based on current inspection workflow
    initial_assignment_status = ASSIGNMENT_STATUS_ASSIGNED
    if insp_status in ["In Progress", "Repair in Progress", "Under Review", "Reopened"]:
        initial_assignment_status = ASSIGNMENT_STATUS_IN_PROGRESS
    elif insp_status == "Resolved":
        initial_assignment_status = ASSIGNMENT_STATUS_COMPLETED

    new_insp_status = "Assigned" if insp_status == "Open" else insp_status
    is_reassignment = (curr_assigned_to_id is not None and curr_assigned_to_id != assigned_to_user_id)

    # If reassigning, mark previous active assignment as cancelled/reassigned
    if is_reassignment:
        cursor.execute("""
            UPDATE maintenance_assignments
            SET status = 'cancelled',
                updated_at = CURRENT_TIMESTAMP,
                cancelled_at = CURRENT_TIMESTAMP,
                cancellation_reason = ?
            WHERE inspection_id = ? AND status IN ('assigned', 'in_progress');
        """, (f"Reassigned to {assignee['username']}", inspection_id))

    # Insert new record into maintenance_assignments
    cursor.execute("""
        INSERT INTO maintenance_assignments (
            inspection_id, assigned_to_user_id, assigned_to_username,
            assigned_by_user_id, assigned_by_username, instructions,
            status, assigned_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
    """, (
        inspection_id,
        assignee["id"],
        assignee["username"],
        assigned_by_user_id,
        assigner_username,
        clean_instructions,
        initial_assignment_status,
    ))
    assignment_id = cursor.lastrowid

    # Update defect_inspections
    cursor.execute("""
        UPDATE defect_inspections
        SET status = ?,
            assigned_to_user_id = ?,
            assigned_to_username = ?,
            assigned_by_user_id = ?,
            assigned_by_username = ?,
            assigned_at = CURRENT_TIMESTAMP,
            assignment_instructions = ?,
            assignment_status = ?,
            assignment_updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
    """, (
        new_insp_status,
        assignee["id"],
        assignee["username"],
        assigned_by_user_id,
        assigner_username,
        clean_instructions,
        initial_assignment_status,
        inspection_id,
    ))
    conn.commit()

    # Log in maintenance audit history
    if is_reassignment:
        action_type = "reassigned"
        notes_text = f"Reassigned from {curr_assigned_to_name} to {assignee['username']}."
        if clean_instructions:
            notes_text += f" Instructions: {clean_instructions}"
    else:
        action_type = "assigned"
        notes_text = f"Task assigned to {assignee['username']}."
        if clean_instructions:
            notes_text += f" Instructions: {clean_instructions}"

    cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status, notes, user_id, username
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (
        inspection_id,
        action_type,
        insp_status,
        new_insp_status,
        notes_text,
        assigned_by_user_id,
        assigner_username,
    ))
    conn.commit()

    # Return updated inspection
    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    updated_insp = row_to_dict(cursor.fetchone())
    conn.close()

    return {
        "inspection": updated_insp,
        "assignment_id": assignment_id,
        "assigned_to": assignee,
        "status": initial_assignment_status,
        "instructions": clean_instructions,
    }


def cancel_inspection_assignment(
    inspection_id: int,
    cancelled_by_user_id: int,
    cancellation_reason: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Cancels an active maintenance task assignment on an inspection record.
    Preserves audit history and updates inspection status to 'unassigned'.
    """
    init_db(db_path)
    canceller = get_user_by_id(cancelled_by_user_id, db_path=db_path)
    canceller_username = canceller["username"] if canceller else "Administrator"

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    insp_row = cursor.fetchone()
    if not insp_row:
        conn.close()
        raise ValueError(f"Inspection record #{inspection_id} not found.")

    prev_assignee_name = insp_row["assigned_to_username"] or "unassigned staff"
    insp_status = insp_row["status"] or "Open"
    clean_reason = (cancellation_reason or "Assignment cancelled by administrator.").strip()

    # Cancel open assignments in maintenance_assignments
    cursor.execute("""
        UPDATE maintenance_assignments
        SET status = 'cancelled',
            updated_at = CURRENT_TIMESTAMP,
            cancelled_at = CURRENT_TIMESTAMP,
            cancellation_reason = ?
        WHERE inspection_id = ? AND status IN ('assigned', 'in_progress');
    """, (clean_reason, inspection_id))

    new_insp_status = "Open" if insp_status == "Assigned" else insp_status

    # Cancel open assignments in maintenance_assignments
    cursor.execute("""
        UPDATE maintenance_assignments
        SET status = 'cancelled',
            updated_at = CURRENT_TIMESTAMP,
            cancelled_at = CURRENT_TIMESTAMP,
            cancellation_reason = ?
        WHERE inspection_id = ? AND status IN ('assigned', 'in_progress');
    """, (clean_reason, inspection_id))

    # Reset assignment on defect_inspections
    cursor.execute("""
        UPDATE defect_inspections
        SET status = ?,
            assigned_to_user_id = NULL,
            assigned_to_username = NULL,
            assignment_status = 'cancelled',
            assignment_instructions = NULL,
            assignment_updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
    """, (new_insp_status, inspection_id))
    conn.commit()

    # Log in activity history
    cursor.execute("""
        INSERT INTO maintenance_activity_log (
            inspection_id, action_type, previous_status, new_status, notes, user_id, username
        ) VALUES (?, 'assignment_cancelled', ?, ?, ?, ?, ?);
    """, (
        inspection_id,
        insp_status,
        new_insp_status,
        f"Assignment for {prev_assignee_name} cancelled. Reason: {clean_reason}",
        cancelled_by_user_id,
        canceller_username,
    ))
    conn.commit()

    cursor.execute("SELECT * FROM defect_inspections WHERE id = ?;", (inspection_id,))
    updated_insp = row_to_dict(cursor.fetchone())
    conn.close()

    return {
        "inspection": updated_insp,
        "message": f"Assignment for inspection #{inspection_id} successfully cancelled.",
        "cancelled_by": canceller_username,
    }


def sync_assignment_status_with_workflow(
    inspection_id: int,
    new_workflow_status: str,
    db_path: str = DEFAULT_DB_PATH
) -> None:
    """
    Synchronizes the active assignment status when an inspection status updates:
    - 'Repair in Progress' / 'Under Review' / 'Reopened' -> 'in_progress'
    - 'Resolved' -> 'completed' (sets completed_at)
    - 'Open' / 'Assigned' -> 'assigned'
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT assigned_to_user_id, assignment_status FROM defect_inspections WHERE id = ?;", (inspection_id,))
    row = cursor.fetchone()
    if not row or not row["assigned_to_user_id"]:
        conn.close()
        return

    curr_assign_status = row["assignment_status"]
    target_assign_status = curr_assign_status
    completed_clause = ""

    if new_workflow_status in ["In Progress", "Repair in Progress", "Under Review", "Reopened"]:
        if curr_assign_status in [ASSIGNMENT_STATUS_ASSIGNED, ASSIGNMENT_STATUS_COMPLETED]:
            target_assign_status = ASSIGNMENT_STATUS_IN_PROGRESS
    elif new_workflow_status == "Resolved":
        target_assign_status = ASSIGNMENT_STATUS_COMPLETED
        completed_clause = ", completed_at = CURRENT_TIMESTAMP"
    elif new_workflow_status in ["Open", "Assigned"]:
        if curr_assign_status == ASSIGNMENT_STATUS_COMPLETED:
            target_assign_status = ASSIGNMENT_STATUS_ASSIGNED

    if target_assign_status != curr_assign_status:
        cursor.execute(f"""
            UPDATE maintenance_assignments
            SET status = ?,
                updated_at = CURRENT_TIMESTAMP
                {completed_clause}
            WHERE inspection_id = ? AND status IN ('assigned', 'in_progress', 'completed');
        """, (target_assign_status, inspection_id))

        cursor.execute("""
            UPDATE defect_inspections
            SET assignment_status = ?,
                assignment_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
        """, (target_assign_status, inspection_id))
        conn.commit()

    conn.close()


def get_maintenance_work_queue(
    user_id: Optional[int] = None,
    assignment_status: Optional[str] = None,
    workflow_status: Optional[str] = None,
    urgency: Optional[str] = None,
    category: Optional[str] = None,
    domain: Optional[str] = None,
    city: Optional[str] = None,
    area: Optional[str] = None,
    search_query: Optional[str] = None,
    sort_by: Optional[str] = None,
    include_unassigned: bool = False,
    limit: int = 100,
    offset: int = 0,
    ref_date: Optional[datetime.date] = None,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """
    Retrieves assigned and actionable tasks for the Maintenance Work Queue with filtering.
    If user_id is provided, restricts results to tasks assigned to that maintenance staff member.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    conditions = []
    params = []

    # If scoped to a specific maintenance user
    if user_id is not None:
        conditions.append("assigned_to_user_id = ?")
        params.append(user_id)
    elif assignment_status and assignment_status.strip().lower() == "unassigned":
        conditions.append("(assigned_to_user_id IS NULL OR assignment_status = 'unassigned')")
    elif assignment_status and assignment_status.strip().lower() in ("all", "any"):
        pass
    elif include_unassigned:
        pass
    else:
        # Otherwise require that it has been assigned
        conditions.append("assigned_to_user_id IS NOT NULL")

    if assignment_status and assignment_status.strip() and assignment_status.lower() not in ("all", "any", "unassigned"):
        st = assignment_status.strip().lower()
        if st in ALLOWED_ASSIGNMENT_STATUSES:
            conditions.append("assignment_status = ?")
            params.append(st)

    if workflow_status and workflow_status.strip() and workflow_status.lower() != "all":
        conditions.append("status = ?")
        params.append(workflow_status.strip())

    if domain and domain.strip() and domain.lower() != "all":
        conditions.append("LOWER(COALESCE(inspection_type, 'road')) = ?")
        params.append(domain.strip().lower())

    if category and category.strip() and category.lower() != "all":
        cat = category.strip()
        conditions.append("(defect_type LIKE ? OR detections_json LIKE ?)")
        params.append(f"%{cat}%")
        params.append(f"%{cat}%")

    if city and city.strip() and city.lower() != "all":
        conditions.append("LOWER(city) = ?")
        params.append(city.strip().lower())

    if area and area.strip() and area.lower() != "all":
        conditions.append("LOWER(area) = ?")
        params.append(area.strip().lower())

    if search_query and search_query.strip():
        raw_q = search_query.strip().lstrip("#")
        q_term = f"%{search_query.strip()}%"
        if raw_q.isdigit():
            conditions.append("(id = ? OR road_name LIKE ? OR area LIKE ? OR city LIKE ? OR location_notes LIKE ? OR assignment_instructions LIKE ? OR defect_type LIKE ? OR assigned_to_username LIKE ?)")
            params.extend([int(raw_q), q_term, q_term, q_term, q_term, q_term, q_term, q_term])
        else:
            conditions.append("(road_name LIKE ? OR area LIKE ? OR city LIKE ? OR location_notes LIKE ? OR assignment_instructions LIKE ? OR defect_type LIKE ? OR assigned_to_username LIKE ?)")
            params.extend([q_term, q_term, q_term, q_term, q_term, q_term, q_term])

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    sort_clean = (sort_by or "").strip().lower()
    if sort_clean in ("newest", "latest"):
        order_clause = "ORDER BY uploaded_at DESC, id DESC"
    elif sort_clean in ("oldest", "earliest"):
        order_clause = "ORDER BY uploaded_at ASC, id ASC"
    elif sort_clean in ("priority", "urgency", "severity"):
        order_clause = """ORDER BY
            CASE
                WHEN target_repair_date IS NOT NULL AND date(target_repair_date) < date('now') THEN 1
                WHEN target_repair_date IS NOT NULL AND date(target_repair_date) = date('now') THEN 2
                WHEN defect_count > 0 THEN 3
                ELSE 4
            END,
            uploaded_at DESC, id DESC"""
    elif sort_clean in ("deadline", "target_date"):
        order_clause = "ORDER BY CASE WHEN target_repair_date IS NULL THEN 1 ELSE 0 END, target_repair_date ASC, uploaded_at DESC"
    else:
        order_clause = """ORDER BY
            CASE
                WHEN assignment_status = 'assigned' THEN 1
                WHEN assignment_status = 'in_progress' THEN 2
                WHEN assignment_status = 'completed' THEN 3
                ELSE 4
            END,
            uploaded_at DESC, id DESC"""

    query = f"""
    SELECT * FROM defect_inspections
    {where_clause}
    {order_clause}
    LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    results = [row_to_dict(r, ref_date=ref_date) for r in rows]

    # Filter by deadline urgency if specified
    if urgency and urgency.strip() and urgency.lower() != "all":
        urg = urgency.strip().lower()
        results = [r for r in results if r.get("maintenance_urgency") == urg]

    return results


def check_user_can_maintain_inspection(user: Dict[str, Any], inspection: Dict[str, Any]) -> bool:
    """
    Enforces authorization:
    - Admin: can maintain any inspection.
    - Maintenance Staff: can maintain only records assigned directly to them.
    - Inspector / others: cannot update maintenance.
    """
    if not user:
        return False
    role = user.get("role")
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_MAINTENANCE:
        assigned_id = inspection.get("assigned_to_user_id")
        return assigned_id is not None and int(assigned_id) == int(user.get("id"))
    return False
