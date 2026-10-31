"""
Tests for Citizen Report Update System & Defect Progress Tracking.

Validates:
1. Citizen can view their own report updates and timeline (GET /api/inspections/<id>/updates).
2. Citizen can submit 'Work Started' (POST /api/inspections/<id>/updates).
3. Citizen can submit 'Road Repaired'.
4. Citizen can submit 'Issue Still Exists'.
5. Citizen can submit 'Issue Has Become Worse'.
6. Citizen can add comments to an update.
7. Citizen can upload an optional photo with the update.
8. Citizen cannot update another user's report (403 Forbidden).
9. Unauthenticated users cannot submit updates (401/403).
10. Citizen cannot directly mark a report officially Resolved (status remains un-resolved; update is pending verification).
11. Timeline clearly distinguishes citizen-reported updates from official inspector verifications.
12. Serving update photographs via GET /api/inspections/<id>/updates/<update_id>/image.
13. Invalid update type validation returns 400 Bad Request.
"""

import io
import json
import pytest

from database.db import (
    init_db,
    save_inspection,
    get_inspection_by_id,
    log_maintenance_activity,
)
from database.auth import (
    ROLE_CITIZEN,
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    create_user,
)
from app.server import create_app


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh isolated SQLite database."""
    db_file = str(tmp_path / "test_report_updates.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def client_app(test_db):
    """Creates a Flask test client with authentication enabled."""
    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db,
        "AUTH_ENABLED": True,
        "AUTH_ENABLED_EXPLICIT": True,
        "ENFORCE_CSRF": False,
        "SECRET_KEY": "test-report-updates-secret-key-32-chars-long",
    })
    client = app.test_client()
    return app, client


def register_and_login(client, username, role=ROLE_CITIZEN, db_path=None):
    """Helper to create a user and log them in via the test client session."""
    user = create_user(
        username=username,
        password="TestSecurePass123",
        role=role,
        email=f"{username}@example.com",
        db_path=db_path
    )
    client.post("/api/auth/login", json={"username": username, "password": "TestSecurePass123"})
    return user


def create_test_inspection(user, db_path, status="Open"):
    """Creates an inspection owned by the specified user."""
    return save_inspection({
        "image_name": "pothole_test.jpg",
        "file_path": "uploads/pothole_test.jpg",
        "status": status,
        "defect_type": "Pothole",
        "confidence": 0.88,
        "severity": "High",
        "road_name": "Hill Road",
        "area": "Bandra West",
        "city": "Mumbai",
        "created_by_user_id": user["id"],
        "created_by_username": user["username"],
        "notes": "Large pothole causing traffic slowdown.",
    }, db_path=db_path)


# =============================================================================
# 1. Citizen Report Update Submission & Options
# =============================================================================

def test_citizen_can_submit_work_started(client_app, test_db):
    """Citizen can submit 'Work Started' condition update."""
    app, client = client_app
    user = register_and_login(client, "citizen_alice", db_path=test_db)
    insp = create_test_inspection(user, test_db)

    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={
            "update_type": "work_started",
            "comment": "Road repair team arrived with asphalt roller."
        }
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["update"]["update_type"] == "work_started"
    assert data["update"]["update_type_label"] == "Work Started"
    assert data["update"]["verification_status"] == "pending_verification"
    assert data["update"]["comment"] == "Road repair team arrived with asphalt roller."


def test_citizen_can_submit_road_repaired(client_app, test_db):
    """Citizen can submit 'Road Repaired' condition update."""
    app, client = client_app
    user = register_and_login(client, "citizen_bob", db_path=test_db)
    insp = create_test_inspection(user, test_db)

    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={
            "update_type": "road_repaired",
            "comment": "Pothole filled and sealed with fresh bitumen."
        }
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["update"]["update_type"] == "road_repaired"
    assert data["update"]["verification_status"] == "pending_verification"


def test_citizen_can_submit_issue_still_exists(client_app, test_db):
    """Citizen can submit 'Issue Still Exists' condition update."""
    app, client = client_app
    user = register_and_login(client, "citizen_charlie", db_path=test_db)
    insp = create_test_inspection(user, test_db)

    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={
            "update_type": "issue_still_exists",
            "comment": "No repair crews seen yet."
        }
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["update"]["update_type"] == "issue_still_exists"


def test_citizen_can_submit_issue_has_become_worse(client_app, test_db):
    """Citizen can submit 'Issue Has Become Worse' condition update."""
    app, client = client_app
    user = register_and_login(client, "citizen_david", db_path=test_db)
    insp = create_test_inspection(user, test_db)

    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={
            "update_type": "issue_worse",
            "comment": "Rain filled the pothole and edges collapsed further."
        }
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["update"]["update_type"] == "issue_worse"
    assert data["update"]["update_type_label"] == "Issue Has Become Worse"


def test_citizen_update_with_optional_photo(client_app, test_db):
    """Citizen can upload an optional photograph with progress update."""
    app, client = client_app
    user = register_and_login(client, "citizen_photo", db_path=test_db)
    insp = create_test_inspection(user, test_db)

    # Valid tiny JPEG byte sequence (SOI, APP0, SOF0, SOS, EOI)
    # Minimal 1x1 valid jpeg stream
    import numpy as np
    import cv2
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    photo_bytes = buf.tobytes()

    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        data={
            "update_type": "road_repaired",
            "comment": "Repairs complete as shown in photo.",
            "image": (io.BytesIO(photo_bytes), "repair_proof.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data"
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["update"]["image_url"] is not None
    update_id = data["update"]["id"]

    # Retrieve image via the image endpoint
    img_resp = client.get(f"/api/inspections/{insp['id']}/updates/{update_id}/image")
    assert img_resp.status_code == 200
    assert img_resp.content_type == "image/jpeg"


# =============================================================================
# 2. Strict Access Control & Isolation
# =============================================================================

def test_citizen_cannot_update_another_users_report(client_app, test_db):
    """Citizen cannot update an inspection report owned by another citizen (403 Forbidden)."""
    app, client = client_app

    # Alice creates inspection
    alice = register_and_login(client, "alice_owner", db_path=test_db)
    insp = create_test_inspection(alice, test_db)
    client.post("/api/auth/logout")

    # Bob logs in and tries to update Alice's report
    register_and_login(client, "bob_attacker", db_path=test_db)
    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={"update_type": "road_repaired", "comment": "Malicious attempt"}
    )
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["error_code"] == "FORBIDDEN_REPORT_UPDATE"


def test_unauthenticated_user_cannot_submit_update(client_app, test_db):
    """Unauthenticated users cannot submit report updates (401 / redirect)."""
    app, client = client_app
    user = create_user("alice_guest", "Password123", role=ROLE_CITIZEN, db_path=test_db)
    insp = create_test_inspection(user, test_db)

    # Do not login
    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={"update_type": "work_started"}
    )
    # roles_required returns 401 when unauthenticated
    assert resp.status_code in (401, 302)


def test_invalid_update_type_rejected(client_app, test_db):
    """Submitting an invalid update type returns 400 Bad Request."""
    app, client = client_app
    user = register_and_login(client, "alice_type_test", db_path=test_db)
    insp = create_test_inspection(user, test_db)

    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={"update_type": "fabricated_status_xyz", "comment": "Invalid"}
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["error_code"] == "INVALID_UPDATE_TYPE"


# =============================================================================
# 3. Status Integrity & Official Verification Rules
# =============================================================================

def test_citizen_cannot_directly_resolve_official_inspection_status(client_app, test_db):
    """
    CRITICAL RULE:
    When a citizen submits 'Road Repaired', the official inspection workflow status
    MUST NOT be changed to 'Resolved'. It remains Open / in-progress, and the update
    is saved as pending verification.
    """
    app, client = client_app
    user = register_and_login(client, "alice_status_integrity", db_path=test_db)
    insp = create_test_inspection(user, test_db, status="Open")

    resp = client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={
            "update_type": "road_repaired",
            "comment": "Road looks fully fixed to me."
        }
    )
    assert resp.status_code == 201

    # Verify official record in database
    db_record = get_inspection_by_id(insp["id"], db_path=test_db)
    assert db_record["status"] == "Open", "Citizen update must NEVER overwrite official workflow status to Resolved!"
    assert len(db_record["citizen_updates"]) == 1
    assert db_record["citizen_updates"][0]["verification_status"] == "pending_verification"


def test_timeline_distinguishes_citizen_claims_from_official_verifications(client_app, test_db):
    """
    Timeline chronological retrieval clearly distinguishes citizen claims from official inspector verifications.
    """
    app, client = client_app
    user = register_and_login(client, "alice_timeline_user", db_path=test_db)
    insp = create_test_inspection(user, test_db)

    # 1. Citizen reports work started
    client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={"update_type": "work_started", "comment": "Contractors arrived."}
    )

    # 2. Citizen reports road repaired
    client.post(
        f"/api/inspections/{insp['id']}/updates",
        json={"update_type": "road_repaired", "comment": "Patch complete."}
    )

    # 3. Municipal inspector logs official verification activity
    log_maintenance_activity(
        inspection_id=insp["id"],
        action_type="verified",
        new_status="Resolved",
        notes="Municipal civil engineer inspected and certified asphalt grade.",
        username="lead_inspector",
        db_path=test_db
    )

    # Fetch timeline
    resp = client.get(f"/api/inspections/{insp['id']}/updates")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    timeline = data["timeline"]

    # Verify timeline elements:
    # 1. Initial report event
    initial_event = timeline[0]
    assert initial_event["event_type"] == "initial_report"

    # 2. Citizen claims
    citizen_events = [t for t in timeline if t.get("event_type") == "citizen_update"]
    assert len(citizen_events) == 2
    assert citizen_events[0]["update_type"] == "work_started"
    assert citizen_events[0]["is_citizen"] is True
    assert citizen_events[1]["update_type"] == "road_repaired"
    assert "Awaiting Verification" in citizen_events[1]["badge"]

    # 3. Official inspector verification
    official_events = [t for t in timeline if t.get("event_type") == "inspector_action"]
    assert len(official_events) >= 1
    assert any(o["verification_status"] == "verified" for o in official_events)
    assert any("Official Verification" in o["badge"] for o in official_events)

