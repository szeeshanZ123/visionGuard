"""
Unit and integration tests for Maintenance Deadlines, Follow-ups, and Notifications (Phase 4.4).

Validates:
- Validation of target repair dates (format, calendar validity, year range, empty/optional).
- Computation of maintenance deadline status (overdue, due today, upcoming, resolved, no deadline).
- Critical invariant: Resolved records are NEVER classified as overdue active repairs.
- Saving inspections with and without target repair dates.
- Chronological maintenance activity history logging on creation, status change, and date change.
- Filtering inspections by deadline urgency (?deadline=overdue, ?deadline=upcoming, etc.).
- Dashboard maintenance summary metrics (overdue, due today, upcoming, resolved, actionable).
- REST API validation, error codes, and responses.
- GET /api/inspections/<id>/activity endpoint.
- Database migration safety and backward compatibility with existing databases.
"""

import datetime
import sqlite3
import pytest

from app.server import create_app
from ai.detection.detector import DefectDetectionService
from database.db import (
    init_db,
    save_inspection,
    get_inspection_by_id,
    get_inspections,
    get_dashboard_analytics,
    update_inspection_status,
    update_inspection,
    validate_target_repair_date,
    compute_maintenance_status,
    get_inspection_activity,
    log_maintenance_activity,
)


@pytest.fixture
def test_app_client(tmp_path):
    """Test client configured with a temporary database."""
    test_db = str(tmp_path / "deadline_test.db")
    detector = DefectDetectionService(model_path="ai/models/best.pt")
    app = create_app(detector=detector, test_config={"TESTING": True, "DATABASE_PATH": test_db})
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary SQLite database path for direct DB tests."""
    db_file = str(tmp_path / "direct_deadline_test.db")
    init_db(db_file)
    return db_file


# -----------------------------------------------------------------------------
# 1. Target Repair Date Validation Tests
# -----------------------------------------------------------------------------

def test_validate_target_repair_date_valid():
    """Verifies that valid ISO YYYY-MM-DD dates are accepted and normalized."""
    valid_dates = ["2026-10-25", "2027-01-01", "2025-12-31", "  2026-11-05  "]
    for d in valid_dates:
        is_valid, norm_date, err = validate_target_repair_date(d)
        assert is_valid is True, f"Expected {d} to be valid, got error: {err}"
        assert norm_date == d.strip()
        assert err is None


def test_validate_target_repair_date_optional_empty():
    """Verifies that None or empty strings are accepted as optional (not set)."""
    for empty in [None, "", "   "]:
        is_valid, norm_date, err = validate_target_repair_date(empty)
        assert is_valid is True
        assert norm_date is None
        assert err is None


def test_validate_target_repair_date_invalid_format():
    """Verifies rejection of invalid date formats and non-calendar dates."""
    invalid_dates = [
        "25-10-2026",      # DD-MM-YYYY
        "10/25/2026",      # MM/DD/YYYY
        "2026/10/25",      # Slash separated
        "not-a-date",      # Text
        "2026-02-30",      # Feb 30 does not exist
        "2026-13-01",      # Month 13
        "2026-04-31",      # April has 30 days
        "1999-12-31",      # Prior to 2000
        "2105-01-01",      # After 2100
    ]
    for d in invalid_dates:
        is_valid, norm_date, err = validate_target_repair_date(d)
        assert is_valid is False, f"Expected {d} to be rejected"
        assert norm_date is None
        assert err is not None


# -----------------------------------------------------------------------------
# 2. Maintenance Status Computation Logic Tests
# -----------------------------------------------------------------------------

def test_compute_maintenance_status_overdue():
    """Active repair with a target date prior to ref_date must be 'overdue'."""
    ref_date = datetime.date(2026, 10, 22)
    past_date = "2026-10-15"

    for active_status in ["Open", "In Progress", "Under Review", "Repair in Progress"]:
        status_info = compute_maintenance_status(past_date, active_status, ref_date=ref_date)
        assert status_info["maintenance_urgency"] == "overdue"
        assert status_info["is_overdue"] is True
        assert status_info["days_remaining"] == -7
        assert "Overdue by 7 days" in status_info["maintenance_label"]


def test_compute_maintenance_status_due_today():
    """Active repair with a target date matching ref_date must be 'due_today'."""
    ref_date = datetime.date(2026, 10, 22)
    today_date = "2026-10-22"

    status_info = compute_maintenance_status(today_date, "Open", ref_date=ref_date)
    assert status_info["maintenance_urgency"] == "due_today"
    assert status_info["is_overdue"] is False
    assert status_info["days_remaining"] == 0
    assert status_info["maintenance_label"] == "Due Today"


def test_compute_maintenance_status_upcoming():
    """Active repair with a future target date must be 'upcoming'."""
    ref_date = datetime.date(2026, 10, 22)
    future_date = "2026-10-29"

    status_info = compute_maintenance_status(future_date, "In Progress", ref_date=ref_date)
    assert status_info["maintenance_urgency"] == "upcoming"
    assert status_info["is_overdue"] is False
    assert status_info["days_remaining"] == 7
    assert "Due in 7 days" in status_info["maintenance_label"]


def test_critical_rule_resolved_record_never_overdue():
    """
    CRITICAL RULE:
    Resolved records MUST NEVER be marked as overdue, even if target repair date is in the past!
    """
    ref_date = datetime.date(2026, 10, 22)
    past_date = "2026-09-01"  # Months in the past

    status_info = compute_maintenance_status(past_date, "Resolved", ref_date=ref_date)
    assert status_info["maintenance_urgency"] == "resolved"
    assert status_info["is_overdue"] is False, "Resolved records must NEVER be marked overdue!"
    assert status_info["maintenance_label"] == "Resolved"


def test_compute_maintenance_status_no_deadline():
    """Record without target date must be 'none' / 'no_deadline' and not overdue."""
    ref_date = datetime.date(2026, 10, 22)
    status_info = compute_maintenance_status(None, "Open", ref_date=ref_date)
    assert status_info["maintenance_urgency"] in ["none", "no_deadline"]
    assert status_info["is_overdue"] is False
    assert status_info["days_remaining"] is None
    assert status_info["maintenance_label"] == "No Target Date"


# -----------------------------------------------------------------------------
# 3. Database Persistence & Activity History Tests
# -----------------------------------------------------------------------------

def test_save_and_retrieve_target_repair_date(temp_db_path):
    """Verifies saving and retrieving an inspection with target_repair_date and initial activity log."""
    payload = {
        "image_name": "highway_pot_01.jpg",
        "road_name": "NH 48 KM 42",
        "target_repair_date": "2026-10-25",
        "status": "Open",
        "detections": [
            {
                "distress_category": "Pothole",
                "class_name": "D40",
                "confidence": 0.88,
                "bbox": {"x1": 50, "y1": 50, "x2": 150, "y2": 150, "width": 100, "height": 100}
            }
        ]
    }
    saved = save_inspection(payload, db_path=temp_db_path)
    assert saved["id"] is not None
    assert saved["target_repair_date"] == "2026-10-25"

    retrieved = get_inspection_by_id(saved["id"], db_path=temp_db_path)
    assert retrieved is not None
    assert retrieved["target_repair_date"] == "2026-10-25"
    assert retrieved["maintenance_urgency"] in ["upcoming", "due_today", "overdue"]

    # Verify initial creation activity log
    activities = get_inspection_activity(saved["id"], db_path=temp_db_path)
    assert len(activities) >= 1
    assert activities[0]["action_type"] == "created"
    assert activities[0]["new_status"] == "Open"
    assert activities[0]["new_target_date"] == "2026-10-25"


def test_backward_compatibility_saving_without_date(temp_db_path):
    """Verifies that saving an inspection without target date works seamlessly."""
    payload = {
        "image_name": "legacy_style_insp.jpg",
        "road_name": "Ring Road Sector 12",
        "status": "Open",
    }
    saved = save_inspection(payload, db_path=temp_db_path)
    assert saved["id"] is not None
    assert saved["target_repair_date"] is None
    assert saved["maintenance_urgency"] in ["none", "no_deadline"]


def test_activity_logging_on_status_and_target_date_update(temp_db_path):
    """Verifies that updating status and target repair date logs chronological events."""
    payload = {
        "image_name": "crack_corridor.jpg",
        "road_name": "Marine Drive",
        "target_repair_date": "2026-10-25",
        "status": "Open",
    }
    saved = save_inspection(payload, db_path=temp_db_path)
    insp_id = saved["id"]

    # 1. Update status to 'In Progress'
    update_inspection_status(insp_id, "In Progress", notes="Crew dispatched for asphalt sealing", db_path=temp_db_path)

    # 2. Update target repair date to '2026-10-28'
    update_inspection(insp_id, {"target_repair_date": "2026-10-28", "notes": "Extended target due to rainfall"}, db_path=temp_db_path)

    # 3. Resolve inspection
    update_inspection_status(insp_id, "Resolved", notes="Repairs completed and validated", db_path=temp_db_path)

    activities = get_inspection_activity(insp_id, db_path=temp_db_path)
    assert len(activities) >= 4

    actions = [a["action_type"] for a in activities]
    assert "created" in actions
    assert "status_change" in actions
    assert "target_date_change" in actions

    # Latest activity should be resolution
    latest = activities[-1]
    assert latest["new_status"] == "Resolved"
    assert "completed" in latest["notes"]


def test_filtering_inspections_by_deadline_urgency(temp_db_path):
    """Verifies filtering inspections using deadline_filter with a fixed ref_date."""
    fixed_ref = datetime.date(2026, 10, 22)

    # Record 1: Overdue (Open, target: 2026-10-15)
    save_inspection({
        "image_name": "overdue_1.jpg",
        "target_repair_date": "2026-10-15",
        "status": "Open"
    }, db_path=temp_db_path)

    # Record 2: Due Today (In Progress, target: 2026-10-22)
    save_inspection({
        "image_name": "due_today_1.jpg",
        "target_repair_date": "2026-10-22",
        "status": "In Progress"
    }, db_path=temp_db_path)

    # Record 3: Upcoming (Under Review, target: 2026-10-30)
    save_inspection({
        "image_name": "upcoming_1.jpg",
        "target_repair_date": "2026-10-30",
        "status": "Under Review"
    }, db_path=temp_db_path)

    # Record 4: Resolved (Resolved, target: 2026-10-10 - past date, but resolved!)
    save_inspection({
        "image_name": "resolved_past.jpg",
        "target_repair_date": "2026-10-10",
        "status": "Resolved"
    }, db_path=temp_db_path)

    # Record 5: No Deadline (Open, target: None)
    save_inspection({
        "image_name": "no_date.jpg",
        "status": "Open"
    }, db_path=temp_db_path)

    # Test filtering 'overdue'
    overdue_list = get_inspections(deadline_filter="overdue", ref_date=fixed_ref, db_path=temp_db_path)
    assert len(overdue_list) == 1
    assert overdue_list[0]["image_name"] == "overdue_1.jpg"

    # Test filtering 'due_today'
    due_today_list = get_inspections(deadline_filter="due_today", ref_date=fixed_ref, db_path=temp_db_path)
    assert len(due_today_list) == 1
    assert due_today_list[0]["image_name"] == "due_today_1.jpg"

    # Test filtering 'upcoming'
    upcoming_list = get_inspections(deadline_filter="upcoming", ref_date=fixed_ref, db_path=temp_db_path)
    assert len(upcoming_list) == 1
    assert upcoming_list[0]["image_name"] == "upcoming_1.jpg"

    # Test filtering 'resolved'
    resolved_list = get_inspections(deadline_filter="resolved", ref_date=fixed_ref, db_path=temp_db_path)
    assert len(resolved_list) == 1
    assert resolved_list[0]["image_name"] == "resolved_past.jpg"

    # Test filtering 'no_deadline'
    no_deadline_list = get_inspections(deadline_filter="no_deadline", ref_date=fixed_ref, db_path=temp_db_path)
    assert len(no_deadline_list) == 1
    assert no_deadline_list[0]["image_name"] == "no_date.jpg"


def test_dashboard_analytics_maintenance_summary(temp_db_path):
    """Verifies get_dashboard_analytics accurately compiles maintenance_summary metrics."""
    fixed_ref = datetime.date(2026, 10, 22)

    save_inspection({"image_name": "o1.jpg", "target_repair_date": "2026-10-10", "status": "Open"}, db_path=temp_db_path)
    save_inspection({"image_name": "o2.jpg", "target_repair_date": "2026-10-18", "status": "Repair in Progress"}, db_path=temp_db_path)
    save_inspection({"image_name": "t1.jpg", "target_repair_date": "2026-10-22", "status": "In Progress"}, db_path=temp_db_path)
    save_inspection({"image_name": "u1.jpg", "target_repair_date": "2026-10-25", "status": "Open"}, db_path=temp_db_path)
    save_inspection({"image_name": "r1.jpg", "target_repair_date": "2026-10-05", "status": "Resolved"}, db_path=temp_db_path)
    save_inspection({"image_name": "n1.jpg", "status": "Open"}, db_path=temp_db_path)

    stats = get_dashboard_analytics(ref_date=fixed_ref, db_path=temp_db_path)
    ms = stats.get("maintenance_summary", {})

    assert ms["overdue_count"] == 2
    assert ms["due_today_count"] == 1
    assert ms["upcoming_count"] == 1
    assert ms["resolved_count"] == 1
    assert ms["actionable_count"] == 4
    assert len(ms["actionable_maintenance"]) == 4


def test_database_migration_idempotent(temp_db_path):
    """Verifies init_db can be called multiple times without corrupting existing records or schemas."""
    save_inspection({
        "image_name": "migration_test.jpg",
        "target_repair_date": "2026-11-15",
        "status": "Open"
    }, db_path=temp_db_path)

    # Run init_db again
    init_db(temp_db_path)

    records = get_inspections(db_path=temp_db_path)
    assert len(records) == 1
    assert records[0]["target_repair_date"] == "2026-11-15"


# -----------------------------------------------------------------------------
# 4. REST API Endpoint Integration Tests
# -----------------------------------------------------------------------------

def test_api_save_inspection_with_valid_target_date(test_app_client):
    """POST /api/inspections saves valid target_repair_date."""
    payload = {
        "image_name": "test_api_date.jpg",
        "road_name": "S.V. Road",
        "target_repair_date": "2026-11-10",
        "status": "Open",
    }
    res = test_app_client.post("/api/inspections", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "success"
    assert data["inspection"]["target_repair_date"] == "2026-11-10"


def test_api_save_inspection_rejects_invalid_date(test_app_client):
    """POST /api/inspections returns 400 for invalid target_repair_date format."""
    payload = {
        "image_name": "invalid_date_test.jpg",
        "target_repair_date": "2026-02-31",  # Invalid calendar date
        "status": "Open",
    }
    res = test_app_client.post("/api/inspections", json=payload)
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert data["error_code"] == "INVALID_TARGET_REPAIR_DATE"


def test_api_get_inspections_filtering_by_deadline(test_app_client):
    """GET /api/inspections?deadline=... filters records by deadline urgency."""
    # Create two records
    test_app_client.post("/api/inspections", json={
        "image_name": "rec1.jpg",
        "target_repair_date": "2026-11-20",
        "status": "Open",
    })
    test_app_client.post("/api/inspections", json={
        "image_name": "rec2.jpg",
        "target_repair_date": "2026-11-20",
        "status": "Resolved",
    })

    # Filter resolved
    res_resolved = test_app_client.get("/api/inspections?deadline=resolved")
    assert res_resolved.status_code == 200
    data_resolved = res_resolved.get_json()
    assert data_resolved["count"] == 1
    assert data_resolved["inspections"][0]["status"] == "Resolved"


def test_api_update_inspection_status_and_target_date(test_app_client):
    """PATCH /api/inspections/<id>/status updates status and target date."""
    save_res = test_app_client.post("/api/inspections", json={
        "image_name": "patch_test.jpg",
        "target_repair_date": "2026-11-01",
        "status": "Open",
    })
    insp_id = save_res.get_json()["inspection"]["id"]

    patch_res = test_app_client.patch(f"/api/inspections/{insp_id}/status", json={
        "status": "In Progress",
        "target_repair_date": "2026-11-05",
        "notes": "Adjusted target date and dispatched crew"
    })
    assert patch_res.status_code == 200
    data = patch_res.get_json()
    assert data["inspection"]["status"] == "In Progress"
    assert data["inspection"]["target_repair_date"] == "2026-11-05"


def test_api_get_inspection_activity_history(test_app_client):
    """GET /api/inspections/<id>/activity returns chronological log."""
    save_res = test_app_client.post("/api/inspections", json={
        "image_name": "activity_test.jpg",
        "target_repair_date": "2026-11-01",
        "status": "Open",
    })
    insp_id = save_res.get_json()["inspection"]["id"]

    test_app_client.patch(f"/api/inspections/{insp_id}/status", json={
        "status": "Resolved",
        "notes": "Physical verification completed by field engineer"
    })

    res = test_app_client.get(f"/api/inspections/{insp_id}/activity")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["count"] >= 2
    assert data["activities"][1]["action_type"] in ("status_change", "resolved")


def test_api_dashboard_stats_contains_maintenance_summary(test_app_client):
    """GET /api/dashboard/stats includes maintenance_summary block."""
    res = test_app_client.get("/api/dashboard/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert "maintenance_summary" in data["stats"]
    ms = data["stats"]["maintenance_summary"]
    for field in ["overdue_count", "due_today_count", "upcoming_count", "resolved_count", "no_deadline_count"]:
        assert field in ms
