"""
Unit and Integration Tests for VisionGuard AI Civic Complaint Assistance Module.

Verifies:
1. Automated generation of tailored drafts for Road and Home inspection domains.
2. Persistence and schema integrity of complaint_drafts in SQLite.
3. User editing of recipient agency, subject, and body.
4. Strict guardrail: Prevention of claiming official submission (status cannot be 'submitted').
5. Mandatory civil & legal disclaimers.
6. Cascade deletion with inspection record.
7. REST API endpoints (GET, PUT, TXT export, PDF export).
"""

import os
import json
import pytest

from database.db import init_db, save_inspection, delete_inspection
from database.complaints import (
    init_complaints_db,
    get_or_create_complaint_draft,
    update_complaint_draft,
    export_complaint_draft_pdf,
    COMPLAINT_DISCLAIMER_TEXT,
)
from app.server import create_app


@pytest.fixture
def test_db_path(tmp_path):
    db_file = str(tmp_path / "test_complaints.db")
    init_db(db_file)
    init_complaints_db(db_file)
    return db_file


@pytest.fixture
def road_inspection(test_db_path):
    data = {
        "image_name": "road_pothole_test.jpg",
        "road_name": "Grand Trunk Road, KM 102",
        "area": "Industrial Area",
        "city": "Ambala",
        "latitude": 30.3782,
        "longitude": 76.7767,
        "defect_type": "Pothole (D40)",
        "defect_count": 2,
        "confidence": 0.88,
        "confidence_threshold": 0.25,
        "inspection_mode": "standard",
        "inspection_type": "road",
        "status": "Open",
        "location_notes": "Deep cavity in right lane posing hazard to two-wheelers.",
        "detections": [
            {"class_name": "Pothole", "class_id": 3, "confidence": 0.88, "box": [100, 100, 250, 250]}
        ]
    }
    return save_inspection(data, db_path=test_db_path)


@pytest.fixture
def home_inspection(test_db_path):
    data = {
        "image_name": "home_crack_test.jpg",
        "road_name": "Apartment Complex Block B",
        "area": "Sector 14",
        "city": "Gurugram",
        "latitude": 28.4595,
        "longitude": 77.0266,
        "defect_type": "Wall Crack",
        "defect_count": 1,
        "confidence": 0.82,
        "confidence_threshold": 0.25,
        "inspection_mode": "tiled",
        "inspection_type": "home",
        "status": "Open",
        "location_notes": "Vertical masonry shear crack propagating under window sill.",
        "detections": [
            {"class_name": "Wall Crack", "class_id": 0, "confidence": 0.82, "box": [50, 80, 180, 400]}
        ]
    }
    return save_inspection(data, db_path=test_db_path)


@pytest.fixture
def test_client(test_db_path):
    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db_path,
        "AUTH_ENABLED": False,
        "ENFORCE_CSRF": False,
    })
    return app.test_client()


def test_road_complaint_draft_generation(test_db_path, road_inspection):
    insp_id = road_inspection["id"]
    draft = get_or_create_complaint_draft(insp_id, db_path=test_db_path)

    assert draft["inspection_id"] == insp_id
    assert draft["complaint_type"] == "road_distress"
    assert "Public Works Department" in draft["recipient_agency"]
    assert "Grand Trunk Road" in draft["subject"]
    assert "Pothole" in draft["subject"]
    assert draft["status"] == "draft"
    assert draft["is_official_submission"] is False
    assert COMPLAINT_DISCLAIMER_TEXT in draft["complaint_body"]


def test_home_complaint_draft_generation(test_db_path, home_inspection):
    insp_id = home_inspection["id"]
    draft = get_or_create_complaint_draft(insp_id, db_path=test_db_path)

    assert draft["inspection_id"] == insp_id
    assert draft["complaint_type"] == "building_defect"
    assert "Building Inspection" in draft["recipient_agency"]
    assert "Wall Crack" in draft["subject"]
    assert draft["status"] == "draft"
    assert draft["is_official_submission"] is False
    assert COMPLAINT_DISCLAIMER_TEXT in draft["complaint_body"]


def test_update_complaint_draft_edits(test_db_path, road_inspection):
    insp_id = road_inspection["id"]
    get_or_create_complaint_draft(insp_id, db_path=test_db_path)

    updates = {
        "recipient_agency": "State Highway Development Authority",
        "subject": "Custom Urgent Pothole Repair Request",
        "complaint_body": "User edited text describing severe hazard on highway.",
    }
    updated = update_complaint_draft(insp_id, updates, db_path=test_db_path)

    assert updated["recipient_agency"] == "State Highway Development Authority"
    assert updated["subject"] == "Custom Urgent Pothole Repair Request"
    assert "User edited text describing severe hazard" in updated["complaint_body"]
    # Verify disclaimer is automatically preserved even if user omitted it
    assert "DISCLAIMER & LEGAL NOTICE" in updated["complaint_body"]


def test_strict_guardrail_cannot_mark_as_submitted(test_db_path, road_inspection):
    insp_id = road_inspection["id"]
    get_or_create_complaint_draft(insp_id, db_path=test_db_path)

    with pytest.raises(ValueError) as excinfo:
        update_complaint_draft(insp_id, {"status": "submitted"}, db_path=test_db_path)

    assert "Cannot mark draft as 'submitted'" in str(excinfo.value)


def test_complaint_draft_cascade_deletion(test_db_path, road_inspection):
    insp_id = road_inspection["id"]
    draft = get_or_create_complaint_draft(insp_id, db_path=test_db_path)
    assert draft is not None

    deleted = delete_inspection(insp_id, db_path=test_db_path)
    assert deleted is True

    # Attempting to fetch draft should raise ValueError since parent inspection is gone
    with pytest.raises(ValueError) as excinfo:
        get_or_create_complaint_draft(insp_id, db_path=test_db_path)
    assert f"Inspection #{insp_id} does not exist" in str(excinfo.value)


def test_api_get_complaint_draft(test_client, road_inspection):
    insp_id = road_inspection["id"]
    resp = test_client.get(f"/api/inspections/{insp_id}/complaint-draft")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["draft"]["inspection_id"] == insp_id
    assert "recipient_agency" in data["draft"]
    assert "subject" in data["draft"]
    assert "complaint_body" in data["draft"]
    assert data["draft"]["status"] == "draft"


def test_api_put_complaint_draft(test_client, road_inspection):
    insp_id = road_inspection["id"]
    payload = {
        "recipient_agency": "District Road Maintenance Wing",
        "subject": "Priority Notice: Road Pothole",
        "complaint_body": "Updated body text regarding rapid repair requirements.",
    }
    resp = test_client.put(f"/api/inspections/{insp_id}/complaint-draft", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["draft"]["recipient_agency"] == "District Road Maintenance Wing"
    assert data["draft"]["subject"] == "Priority Notice: Road Pothole"


def test_api_export_complaint_draft_txt(test_client, road_inspection):
    insp_id = road_inspection["id"]
    resp = test_client.get(f"/api/inspections/{insp_id}/complaint-draft/export/txt")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["Content-Type"]
    assert f"complaint_draft_insp_{insp_id}.txt" in resp.headers["Content-Disposition"]
    text = resp.data.decode("utf-8")
    assert "SUBJECT:" in text
    assert "TO:" in text
    assert "DISCLAIMER & LEGAL NOTICE" in text


def test_api_export_complaint_draft_pdf(test_client, home_inspection):
    insp_id = home_inspection["id"]
    resp = test_client.get(f"/api/inspections/{insp_id}/complaint-draft/export/pdf")
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["Content-Type"]
    assert f"complaint_draft_insp_{insp_id}.pdf" in resp.headers["Content-Disposition"]
    assert resp.data.startswith(b"%PDF-")


def test_road_vs_home_templates_markers_and_distinct_content(test_db_path, road_inspection, home_inspection):
    """Verifies that Road and Home templates are strictly separated and contain missing info markers."""
    road_draft = get_or_create_complaint_draft(road_inspection["id"], db_path=test_db_path)
    home_draft = get_or_create_complaint_draft(home_inspection["id"], db_path=test_db_path)

    # Road template specifics
    assert "[Please enter your full name]" in road_draft["complaint_body"]
    assert "Residential Ward / Neighborhood: [Please enter your ward or locality]" in road_draft["complaint_body"]
    assert "sub-base" in road_draft["complaint_body"].lower()
    assert "two-wheeler" in road_draft["complaint_body"].lower()

    # Home template specifics
    assert "[Please enter unit or flat number]" in home_draft["complaint_body"]
    assert "[Please enter society or complex name]" in home_draft["complaint_body"]
    assert "water ingress" in home_draft["complaint_body"].lower()
    assert "spalling" in home_draft["complaint_body"].lower()


def test_complaint_draft_lifecycle_transitions(test_db_path, road_inspection):
    """Verifies transition between Draft, Ready to Submit, and Submitted states."""
    insp_id = road_inspection["id"]
    draft = get_or_create_complaint_draft(insp_id, db_path=test_db_path)
    assert draft["status"] == "draft"

    # Transition to ready_to_submit
    ready_draft = update_complaint_draft(insp_id, {"status": "ready_to_submit"}, db_path=test_db_path)
    assert ready_draft["status"] == "ready_to_submit"

    # Transition to submitted via manual citizen submission logging
    sub_data = {
        "manual_submission": True,
        "submission_channel": "CPGRAMS Portal (pgportal.gov.in)",
        "submission_reference": "CPG-2026-98124",
    }
    submitted_draft = update_complaint_draft(insp_id, sub_data, db_path=test_db_path)
    assert submitted_draft["status"] == "submitted"
    assert submitted_draft["submission_channel"] == "CPGRAMS Portal (pgportal.gov.in)"
    assert submitted_draft["submission_reference"] == "CPG-2026-98124"
    assert submitted_draft["submitted_at"] is not None


def test_complaint_draft_validation_errors(test_db_path, road_inspection):
    """Verifies that empty required fields raise validation errors."""
    insp_id = road_inspection["id"]
    get_or_create_complaint_draft(insp_id, db_path=test_db_path)

    with pytest.raises(ValueError) as exc1:
        update_complaint_draft(insp_id, {"recipient_agency": "   "}, db_path=test_db_path)
    assert "Recipient Agency / Authority is required" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        update_complaint_draft(insp_id, {"subject": ""}, db_path=test_db_path)
    assert "Subject line is required" in str(exc2.value)

    with pytest.raises(ValueError) as exc3:
        update_complaint_draft(insp_id, {"complaint_body": "   "}, db_path=test_db_path)
    assert "Complaint body is required" in str(exc3.value)


def test_location_and_contact_editing_persistence(test_db_path, road_inspection):
    """Verifies citizen editing of complainant name, contact info, and confirmed location."""
    insp_id = road_inspection["id"]
    get_or_create_complaint_draft(insp_id, db_path=test_db_path)

    updates = {
        "complainant_name": "Aarav Sharma",
        "complainant_contact": "+91 98111 22334 / aarav@example.com",
        "location_address": "Updated Highway KM 105, East Bypass",
    }
    updated = update_complaint_draft(insp_id, updates, db_path=test_db_path)

    assert updated["complainant_name"] == "Aarav Sharma"
    assert updated["complainant_contact"] == "+91 98111 22334 / aarav@example.com"
    assert "Updated Highway KM 105" in updated["inspection_location"]


def test_cross_citizen_draft_access_security(tmp_path):
    """Verifies that Citizen B cannot read, edit, or export Citizen A's complaint draft (403 Forbidden)."""
    db_file = str(tmp_path / "test_sec.db")
    init_db(db_file)
    init_complaints_db(db_file)

    # Create Citizen 1 and Citizen 2
    from database.auth import create_user
    c1 = create_user("citizen_alice", "password123", role="citizen", db_path=db_file)
    c2 = create_user("citizen_bob", "password123", role="citizen", db_path=db_file)

    # Save inspection belonging to Citizen 1
    insp_data = {
        "image_name": "alice_road.jpg",
        "road_name": "Alice Lane 4",
        "defect_type": "Pothole",
        "defect_count": 1,
        "inspection_type": "road",
        "created_by_user_id": c1["id"],
        "created_by_username": c1["username"],
    }
    alice_insp = save_inspection(insp_data, db_path=db_file)
    insp_id = alice_insp["id"]

    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": db_file,
        "AUTH_ENABLED": True,
        "ENFORCE_CSRF": False,
    })
    client = app.test_client()

    # Login as Citizen 2 (Bob)
    login_resp = client.post("/api/auth/login", json={"username": "citizen_bob", "password": "password123"})
    assert login_resp.status_code == 200

    # Bob attempts to access Alice's draft
    get_resp = client.get(f"/api/inspections/{insp_id}/complaint-draft")
    assert get_resp.status_code == 403
    assert get_resp.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Bob attempts to edit Alice's draft
    put_resp = client.put(f"/api/inspections/{insp_id}/complaint-draft", json={"subject": "Malicious edit"})
    assert put_resp.status_code == 403
    assert put_resp.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Bob attempts to export Alice's TXT draft
    txt_resp = client.get(f"/api/inspections/{insp_id}/complaint-draft/export/txt")
    assert txt_resp.status_code == 403
    assert txt_resp.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Bob attempts to export Alice's PDF draft
    pdf_resp = client.get(f"/api/inspections/{insp_id}/complaint-draft/export/pdf")
    assert pdf_resp.status_code == 403
    assert pdf_resp.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

