"""
Regression test suite for VisionGuard AI Production Bug Fixes:
1. Issue 1: Complaint PDF export reliability, XML escaping, Postgres compatibility, and error responses.
2. Issue 2: Citizen dashboard counts, ownership matching (ID + username), Defect Map accessibility, and isolation.
3. Issue 3: Memory safeguards, lazy home detector loading, inference serialization lock, and resolution clamping.
"""

import io
import os
import pytest
from unittest.mock import patch, MagicMock

from app.server import create_app, INFERENCE_LOCK, INSPECTION_SEMAPHORE
from ai.detection.detector import DefectDetectionService, HomeDefectDetectionService
from database.db import (
    init_db,
    save_inspection,
    get_inspections,
    get_citizen_dashboard_summary,
    get_inspection_by_id,
    get_db_connection,
)
from database.complaints import (
    init_complaints_db,
    get_or_create_complaint_draft,
    update_complaint_draft,
    export_complaint_draft_pdf,
)
from database.auth import create_user, ROLE_CITIZEN, ROLE_ADMIN


@pytest.fixture
def test_setup(tmp_path):
    """Sets up a temporary SQLite database and test Flask application."""
    db_file = str(tmp_path / "bug_fixes_test.db")
    init_db(db_file)
    init_complaints_db(db_file)

    detector = DefectDetectionService(model_path="ai/models/best.pt", lazy=True)
    home_detector = HomeDefectDetectionService(model_path="ai/models/home_best.pt", lazy=True)

    app = create_app(
        detector=detector,
        home_detector=home_detector,
        test_config={
            "TESTING": True,
            "DATABASE_PATH": db_file,
            "AUTH_ENABLED": True,
            "ENFORCE_CSRF": False,
            "SECRET_KEY": "a" * 32,
        }
    )

    # Create two citizen users
    c1 = create_user("zeeshanshaikh1", "Pass1234!", role=ROLE_CITIZEN, db_path=db_file)
    c2 = create_user("other_citizen", "Pass1234!", role=ROLE_CITIZEN, db_path=db_file)
    admin = create_user("admin_user", "Pass1234!", role=ROLE_ADMIN, db_path=db_file)

    return {
        "app": app,
        "db_path": db_file,
        "c1": c1,
        "c2": c2,
        "admin": admin,
    }


# =============================================================================
# ISSUE 1: Complaint PDF Export Regression Tests
# =============================================================================

def test_complaint_draft_pdf_export_e2e(test_setup):
    """Verifies that export_complaint_draft_pdf produces valid PDF bytes with header."""
    db_path = test_setup["db_path"]
    insp = save_inspection({
        "image_name": "road_damage_01.jpg",
        "road_name": "MG Road Expressway & Highway",
        "area": "Downtown",
        "city": "Mumbai",
        "status": "Open",
        "defect_type": "Pothole (D40)",
        "defect_count": 2,
        "created_by_user_id": test_setup["c1"]["id"],
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    pdf_bytes = export_complaint_draft_pdf(insp["id"], db_path=db_path)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_complaint_draft_pdf_special_characters_escaping(test_setup):
    """Verifies that special characters (&, <, >, quotes) in agency/subject/body do not crash ReportLab."""
    db_path = test_setup["db_path"]
    insp = save_inspection({
        "image_name": "special_chars_test.jpg",
        "road_name": "Main St & 5th Ave <Northbound>",
        "area": "Sector 9 & 10",
        "city": "Pune",
        "status": "Open",
        "defect_type": "Longitudinal Crack (D00)",
        "defect_count": 1,
        "created_by_user_id": test_setup["c1"]["id"],
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    # Update draft with complex ampersands and XML characters
    update_complaint_draft(insp["id"], {
        "recipient_agency": "Roads & Highways Department / PWD & Municipal Corp <Division A>",
        "subject": "Urgent: Deep Pothole & Road Distress <Immediate Repair Needed>",
        "complainant_name": "Zeeshan & Family <Citizens>",
        "complaint_body": "Notice regarding safety hazards & damage on Roadway <KM 12.4> & Lane 2.",
    }, db_path=db_path)

    # Must generate PDF without raising XML / ExpatError
    pdf_bytes = export_complaint_draft_pdf(insp["id"], db_path=db_path)
    assert pdf_bytes.startswith(b"%PDF-")


def test_complaint_draft_pdf_api_citizen_authorized(test_setup):
    """Verifies that a citizen can export their complaint draft via API."""
    app = test_setup["app"]
    db_path = test_setup["db_path"]
    c1 = test_setup["c1"]

    insp = save_inspection({
        "image_name": "auth_pdf_test.jpg",
        "road_name": "Kurla Road",
        "status": "Open",
        "created_by_user_id": c1["id"],
        "created_by_username": c1["username"],
    }, db_path=db_path)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = c1["id"]

    resp = client.get(f"/api/inspections/{insp['id']}/complaint-draft/export/pdf")
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers.get("Content-Type", "")
    assert f"complaint_draft_insp_{insp['id']}.pdf" in resp.headers.get("Content-Disposition", "")
    assert resp.data.startswith(b"%PDF-")


def test_complaint_draft_pdf_api_ownership_by_username(test_setup):
    """Verifies that citizen can export draft if created_by_username matches even if created_by_user_id is None."""
    app = test_setup["app"]
    db_path = test_setup["db_path"]
    c1 = test_setup["c1"]

    insp = save_inspection({
        "image_name": "auth_username_test.jpg",
        "road_name": "Bandra Kurla Complex",
        "status": "Open",
        "created_by_user_id": None,
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = c1["id"]

    resp = client.get(f"/api/inspections/{insp['id']}/complaint-draft/export/pdf")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF-")


def test_complaint_draft_pdf_api_forbidden_for_other_citizen(test_setup):
    """Verifies that a citizen cannot export another user's complaint draft (HTTP 403)."""
    app = test_setup["app"]
    db_path = test_setup["db_path"]
    c1 = test_setup["c1"]
    c2 = test_setup["c2"]

    insp = save_inspection({
        "image_name": "other_citizen_insp.jpg",
        "road_name": "Private Colony Road",
        "status": "Open",
        "created_by_user_id": c1["id"],
        "created_by_username": c1["username"],
    }, db_path=db_path)

    # c2 attempts to export c1's draft
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = c2["id"]

    resp = client.get(f"/api/inspections/{insp['id']}/complaint-draft/export/pdf")
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["error_code"] == "FORBIDDEN_REPORT_ACCESS"


def test_complaint_draft_pdf_api_returns_json_on_error(test_setup):
    """Verifies that PDF export failure returns structured JSON error instead of crashing or returning None."""
    app = test_setup["app"]
    c1 = test_setup["c1"]

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = c1["id"]

    # Non-existent inspection ID -> 404
    resp = client.get("/api/inspections/99999/complaint-draft/export/pdf")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json()["status"] == "error"


def test_complaint_draft_postgres_init_safe(test_setup):
    """Verifies that init_complaints_db skips SQLite DDL when is_postgres_backend is True."""
    db_path = test_setup["db_path"]
    with patch("database.complaints.is_postgres_backend", return_value=True):
        # Should return without executing SQLite DDL
        init_complaints_db(db_path)


# =============================================================================
# ISSUE 2: Reports and Map Counts Regression Tests
# =============================================================================

def test_citizen_summary_matching_by_username_and_id(test_setup):
    """Verifies that get_citizen_dashboard_summary counts records matched by user_id OR username."""
    db_path = test_setup["db_path"]
    c1 = test_setup["c1"]

    # Record 1: created with user_id
    save_inspection({
        "image_name": "rec1.jpg",
        "road_name": "Road 1",
        "status": "Open",
        "created_by_user_id": c1["id"],
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    # Record 2: created with username only (user_id is None)
    save_inspection({
        "image_name": "rec2.jpg",
        "road_name": "Road 2",
        "status": "Resolved",
        "created_by_user_id": None,
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    # Other citizen's record
    save_inspection({
        "image_name": "other.jpg",
        "road_name": "Road 3",
        "status": "Open",
        "created_by_user_id": 999,
        "created_by_username": "someone_else",
    }, db_path=db_path)

    summary = get_citizen_dashboard_summary(c1["id"], username="zeeshanshaikh1", db_path=db_path)
    assert summary["total"] == 2
    assert summary["open"] == 1
    assert summary["resolved"] == 1


def test_citizen_my_reports_api_filters_correctly(test_setup):
    """Verifies that /api/inspections?my_reports=1 returns citizen's reports matching ID or username."""
    app = test_setup["app"]
    db_path = test_setup["db_path"]
    c1 = test_setup["c1"]

    save_inspection({
        "image_name": "c1_rec1.jpg",
        "road_name": "Expressway 1",
        "status": "Open",
        "created_by_user_id": c1["id"],
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    save_inspection({
        "image_name": "c1_rec2.jpg",
        "road_name": "Expressway 2",
        "status": "Open",
        "created_by_user_id": None,
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    save_inspection({
        "image_name": "c2_rec.jpg",
        "road_name": "Expressway 3",
        "status": "Open",
        "created_by_user_id": test_setup["c2"]["id"],
        "created_by_username": "other_citizen",
    }, db_path=db_path)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = c1["id"]

    resp = client.get("/api/inspections?my_reports=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 2
    names = {r["image_name"] for r in data["inspections"]}
    assert names == {"c1_rec1.jpg", "c1_rec2.jpg"}


def test_citizen_defect_map_shows_all_civic_geotagged_records(test_setup):
    """Verifies that citizens can explore all published geotagged civic records on the shared Defect Map."""
    app = test_setup["app"]
    db_path = test_setup["db_path"]
    c1 = test_setup["c1"]

    # 1. Citizen's own geotagged record, approved and published
    save_inspection({
        "image_name": "my_geo.jpg",
        "road_name": "Local Road",
        "latitude": 19.0760,
        "longitude": 72.8777,
        "status": "Open",
        "publication_status": "published",
        "created_by_user_id": c1["id"],
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    # 2. Another user's public geotagged record, approved and published
    save_inspection({
        "image_name": "city_geo.jpg",
        "road_name": "Highway 1",
        "latitude": 19.1200,
        "longitude": 72.8500,
        "status": "Open",
        "publication_status": "published",
        "created_by_user_id": 999,
        "created_by_username": "city_inspector",
    }, db_path=db_path)

    # 3. Un-geotagged record (should NOT be on map)
    save_inspection({
        "image_name": "no_coords.jpg",
        "road_name": "Indoor Site",
        "latitude": None,
        "longitude": None,
        "status": "Open",
        "publication_status": "published",
    }, db_path=db_path)

    # 4. Unpublished pending_review record (should NOT be on public map)
    save_inspection({
        "image_name": "pending_geo.jpg",
        "road_name": "Unpublished Road",
        "latitude": 19.1500,
        "longitude": 72.8600,
        "status": "Open",
        "publication_status": "pending_review",
    }, db_path=db_path)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = c1["id"]

    # Shared Defect Map query
    resp = client.get("/api/public/defects?limit=500")
    assert resp.status_code == 200
    data = resp.get_json()
    # Exactly the two published geotagged records must be visible on the public Defect Map
    assert data["count"] == 2
    lats = {round(r["latitude"], 4) for r in data["defects"]}
    assert 19.0760 in lats
    assert 19.1200 in lats

    # Private fields must never leak on the public map
    for marker in data["defects"]:
        assert marker["marker_id"].startswith("PUB-")
        assert "image_name" not in marker
        assert "created_by_user_id" not in marker
        assert "created_by_username" not in marker

    # On private dashboard /api/inspections, citizen c1 only sees their own inspection
    resp_priv = client.get("/api/inspections?limit=500")
    assert resp_priv.status_code == 200
    priv_data = resp_priv.get_json()
    assert priv_data["count"] == 1
    assert priv_data["inspections"][0]["image_name"] == "my_geo.jpg"


def test_citizen_detail_view_access_by_username(test_setup):
    """Verifies that inspection detail is viewable by citizen if username matches even if user_id is None."""
    app = test_setup["app"]
    db_path = test_setup["db_path"]
    c1 = test_setup["c1"]

    insp = save_inspection({
        "image_name": "detail_username_test.jpg",
        "road_name": "Kurla West",
        "status": "Open",
        "created_by_user_id": None,
        "created_by_username": "zeeshanshaikh1",
    }, db_path=db_path)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = c1["id"]

    resp = client.get(f"/api/inspections/{insp['id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["inspection"]["id"] == insp["id"]


# =============================================================================
# ISSUE 3: Memory & Concurrency Safeguard Tests
# =============================================================================

def test_lazy_home_detector_verified_without_eager_weights():
    """Verifies that HomeDefectDetectionService(lazy=True) verifies the checkpoint without loading weights."""
    detector = HomeDefectDetectionService(model_path="ai/models/home_best.pt", lazy=True)
    assert detector.is_loaded is True
    assert "ready" in detector.status_message.lower()
    # Model should remain unloaded until detect() is invoked
    assert detector.model is None


def test_inference_lock_exists_and_serializes():
    """Verifies that INFERENCE_LOCK is initialized and provides proper mutex locking."""
    assert INFERENCE_LOCK is not None
    # Verify acquire and release works cleanly
    acquired = INFERENCE_LOCK.acquire(timeout=1.0)
    assert acquired is True
    INFERENCE_LOCK.release()

def test_inspection_semaphore_concurrency_guard(test_setup):
    """Verifies that INSPECTION_SEMAPHORE prevents concurrent inspections and returns HTTP 503."""
    app = test_setup["app"]
    client = app.test_client()
    assert INSPECTION_SEMAPHORE is not None

    with client.session_transaction() as sess:
        sess["user_id"] = test_setup["c1"]["id"]
        sess["username"] = test_setup["c1"]["username"]
        sess["role"] = test_setup["c1"]["role"]

    acquired = INSPECTION_SEMAPHORE.acquire(blocking=False)
    assert acquired is True

    try:
        with patch.object(INSPECTION_SEMAPHORE, "acquire", return_value=False):
            data = {
                "image": (io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100), "test.jpg"),
                "domain": "road",
            }
            res = client.post("/api/inspect", data=data, content_type="multipart/form-data")
            assert res.status_code == 503
            json_body = res.get_json()
            assert json_body["status"] == "error"
            assert json_body["error_code"] == "SERVER_OVERLOADED"
            assert "processing another inspection" in json_body["message"]
    finally:
        INSPECTION_SEMAPHORE.release()

