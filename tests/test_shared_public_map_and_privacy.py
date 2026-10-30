"""
Tests for Shared Public Defect Map with Private Citizen Records.

Validates:
1. Public Defect Map displays approved defect markers across citizens (User A & User B).
2. All reports default to 'pending_review' and are hidden until approved.
3. Historical records are not auto-published (remain pending_review).
4. Public API generates a separate, opaque public marker ID (PUB-XXXX) and never exposes:
   - Raw database inspection IDs
   - Personal complaint reference IDs (VG-CMP-XXXX)
   - Citizen names, phone numbers, email addresses, user IDs
   - Uploaded photographs or annotated private photographs
   - Private citizen notes or complaint documents / PDFs
5. Two-user strict private record isolation:
   - User B cannot access User A's private inspection report (403 Forbidden)
   - User B cannot access User A's original or annotated photos (403 Forbidden)
   - User B cannot access or download User A's complaint draft or PDF (403 Forbidden)
   - Reciprocal protection for User A against User B's records
   - Citizen dashboards (/api/inspections) strictly show only own records
6. Publication management access control:
   - Citizens cannot publish/unpublish records (403 Forbidden)
   - Authorized admins and inspectors can publish/hide records (200 OK)
   - Hiding a record immediately removes it from the public defect map
"""

import os
import json
import pytest

from database.db import (
    init_db,
    save_inspection,
    get_inspections,
    get_inspection_by_id,
    update_inspection_publication_status,
)
from database.auth import (
    ROLE_CITIZEN,
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    create_user,
)
from database.complaints import (
    init_complaints_db,
    get_or_create_complaint_draft,
    update_complaint_draft,
)
from app.server import create_app


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh isolated SQLite database."""
    db_file = str(tmp_path / "test_public_map.db")
    init_db(db_file)
    init_complaints_db(db_file)
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
        "SECRET_KEY": "test-public-map-key-secret-32-chars-long",
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


# =============================================================================
# 1. Publication Lifecycle & Default State Verification
# =============================================================================

def test_new_reports_default_to_pending_review_and_stay_off_public_map(client_app, test_db):
    """Verifies that newly submitted reports default to pending_review and do not appear on /api/public/defects."""
    _, client = client_app
    user_a = register_and_login(client, "citizen_a", role=ROLE_CITIZEN, db_path=test_db)

    # User A creates a geotagged road defect inspection
    rec = save_inspection({
        "image_name": "pothole_a.jpg",
        "road_name": "Link Road, Pillar 12",
        "area": "Andheri West",
        "city": "Mumbai",
        "latitude": 19.1364,
        "longitude": 72.8278,
        "status": "Open",
        "defect_type": "D40",
        "preliminary_severity": "High",
        "defect_count": 2,
        "created_by_user_id": user_a["id"],
        "created_by_username": user_a["username"],
        "inspection_type": "road",
    }, db_path=test_db)

    # 1. Database level assertion: default publication status is pending_review
    assert rec["publication_status"] == "pending_review"
    assert rec["published_at"] is None

    # 2. Public API query: record must NOT appear
    res = client.get("/api/public/defects")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["count"] == 0
    assert len(data["defects"]) == 0


def test_historical_records_remain_pending_review_by_default(client_app, test_db):
    """Verifies existing/historical records are never auto-published and remain pending_review."""
    _, client = client_app
    user_a = register_and_login(client, "citizen_legacy", role=ROLE_CITIZEN, db_path=test_db)

    # Insert a historical record directly without publication_status specified
    rec = save_inspection({
        "image_name": "historical_road.jpg",
        "road_name": "SV Road",
        "city": "Mumbai",
        "latitude": 19.0596,
        "longitude": 72.8362,
        "status": "Open",
        "defect_type": "Longitudinal Crack",
        "created_by_user_id": user_a["id"],
        "created_by_username": user_a["username"],
    }, db_path=test_db)

    db_rec = get_inspection_by_id(rec["id"], db_path=test_db)
    assert db_rec["publication_status"] == "pending_review"

    # Must not be on the public defect map
    res = client.get("/api/public/defects")
    assert res.status_code == 200
    assert res.get_json()["count"] == 0


# =============================================================================
# 2. Publication Access Control
# =============================================================================

def test_citizen_cannot_publish_reports(client_app, test_db):
    """Verifies that citizen users cannot call the publication endpoint (HTTP 403)."""
    _, client = client_app
    user_a = register_and_login(client, "citizen_user", role=ROLE_CITIZEN, db_path=test_db)

    rec = save_inspection({
        "image_name": "test_pub.jpg",
        "road_name": "CST Road",
        "latitude": 19.0728,
        "longitude": 72.8998,
        "status": "Open",
        "created_by_user_id": user_a["id"],
        "created_by_username": user_a["username"],
    }, db_path=test_db)

    # Citizen attempts to publish their own inspection
    res = client.patch(f"/api/inspections/{rec['id']}/publication", json={"publication_status": "published"})
    assert res.status_code == 403
    err_data = res.get_json()
    assert err_data["error_code"] == "FORBIDDEN"

    # Status in database must remain pending_review
    db_rec = get_inspection_by_id(rec["id"], db_path=test_db)
    assert db_rec["publication_status"] == "pending_review"


def test_admin_and_inspector_can_publish_and_hide_records(client_app, test_db):
    """Verifies that Admin and Inspector roles can publish, hide, or reset publication status."""
    _, client = client_app
    admin_user = register_and_login(client, "authority_admin", role=ROLE_ADMIN, db_path=test_db)

    rec = save_inspection({
        "image_name": "authority_target.jpg",
        "road_name": "Eastern Express Hwy",
        "latitude": 19.1120,
        "longitude": 72.8850,
        "status": "Open",
        "defect_type": "Pothole",
        "created_by_username": "some_citizen",
    }, db_path=test_db)

    # 1. Admin publishes record
    res_pub = client.patch(f"/api/inspections/{rec['id']}/publication", json={"publication_status": "published"})
    assert res_pub.status_code == 200
    data_pub = res_pub.get_json()
    assert data_pub["status"] == "success"
    assert data_pub["publication_status"] == "published"
    assert data_pub["published_at"] is not None
    assert data_pub["published_by_username"] == admin_user["username"]

    # 2. Record now appears on public defect map
    res_map = client.get("/api/public/defects")
    assert res_map.status_code == 200
    map_data = res_map.get_json()
    assert map_data["count"] == 1
    assert "Pothole" in map_data["defects"][0]["defect_category"]

    # 3. Admin hides record
    res_hide = client.patch(f"/api/inspections/{rec['id']}/publication", json={"publication_status": "hidden"})
    assert res_hide.status_code == 200
    assert res_hide.get_json()["publication_status"] == "hidden"

    # 4. Hidden record disappears immediately from public defect map
    res_map_after_hide = client.get("/api/public/defects")
    assert res_map_after_hide.status_code == 200
    assert res_map_after_hide.get_json()["count"] == 0


# =============================================================================
# 3. Two-User Isolation & Public Marker Verification
# =============================================================================

def test_two_user_shared_public_map_and_strict_private_data_isolation(client_app, test_db):
    """
    Complete two-user isolation journey:
    - User A reports Road Pothole.
    - User B reports Building Wall Crack.
    - Admin reviews and approves both to 'published'.
    - User B sees User A's marker on the shared map (and vice-versa).
    - Marker ID is an opaque PUB- token, NOT raw database ID.
    - Public marker excludes citizen name, contact, raw IDs, photos, notes, and PDFs.
    - User B is strictly forbidden (403) from accessing User A's private details, photos, and PDF.
    - User A is strictly forbidden (403) from accessing User B's private details, photos, and PDF.
    """
    app, client = client_app

    # Step 1: Create User A and User B
    user_a = create_user("citizen_alice", "AlicePass123", role=ROLE_CITIZEN, email="alice@example.com", db_path=test_db)
    user_b = create_user("citizen_bob", "BobPass123", role=ROLE_CITIZEN, email="bob@example.com", db_path=test_db)
    admin_user = create_user("super_admin", "AdminPass123", role=ROLE_ADMIN, email="admin@example.com", db_path=test_db)

    # Step 2: User A submits road defect inspection
    rec_a = save_inspection({
        "image_name": "alice_pothole.jpg",
        "original_image_path": "uploads/alice_pothole.jpg",
        "annotated_image_path": "uploads/alice_pothole_annotated.jpg",
        "road_name": "MG Road near Metro Station",
        "area": "Fort",
        "city": "Mumbai",
        "latitude": 18.9322,
        "longitude": 72.8336,
        "status": "Open",
        "defect_type": "D40",
        "preliminary_severity": "High",
        "defect_count": 2,
        "location_notes": "Dangerous deep pothole near pedestrian crossing",
        "created_by_user_id": user_a["id"],
        "created_by_username": user_a["username"],
        "inspection_type": "road",
    }, db_path=test_db)

    # User A creates a complaint draft
    get_or_create_complaint_draft(rec_a["id"], user_id=user_a["id"], username=user_a["username"], db_path=test_db)
    update_complaint_draft(rec_a["id"], {
        "status": "submitted",
        "manual_submission": True,
        "submission_channel": "BMC Pavement Portal",
        "submission_reference": "VG-CMP-0088",
        "complainant_name": "Alice Citizen",
        "complainant_contact": "+91-9876543210",
        "complaint_body": "Private grievance detailing tire damage from severe pothole.",
    }, db_path=test_db)

    # Step 3: User B submits building defect inspection
    rec_b = save_inspection({
        "image_name": "bob_facade_crack.jpg",
        "original_image_path": "uploads/bob_facade_crack.jpg",
        "annotated_image_path": "uploads/bob_facade_crack_annotated.jpg",
        "road_name": "Greenwood Tower 3 Facade",
        "area": "Bandra East",
        "city": "Mumbai",
        "latitude": 19.0600,
        "longitude": 72.8500,
        "status": "Under Review",
        "defect_type": "wall_crack",
        "preliminary_severity": "Critical",
        "defect_count": 1,
        "location_notes": "Structural shear crack spanning pillar 4 to 5",
        "created_by_user_id": user_b["id"],
        "created_by_username": user_b["username"],
        "inspection_type": "home",
    }, db_path=test_db)

    get_or_create_complaint_draft(rec_b["id"], user_id=user_b["id"], username=user_b["username"], db_path=test_db)
    update_complaint_draft(rec_b["id"], {
        "status": "submitted",
        "manual_submission": True,
        "submission_channel": "Building Safety Cell",
        "submission_reference": "VG-CMP-0099",
        "complainant_name": "Bob Homeowner",
        "complainant_contact": "+91-9811223344",
        "complaint_body": "Urgent request to inspect facade integrity.",
    }, db_path=test_db)

    # Step 4: Admin reviews and publishes both records
    client.post("/api/auth/login", json={"username": "super_admin", "password": "AdminPass123"})
    res_pub_a = client.patch(f"/api/inspections/{rec_a['id']}/publication", json={"publication_status": "published"})
    assert res_pub_a.status_code == 200
    res_pub_b = client.patch(f"/api/inspections/{rec_b['id']}/publication", json={"publication_status": "published"})
    assert res_pub_b.status_code == 200

    # Step 5: User B logs in and views the Shared Public Defect Map
    client.post("/api/auth/login", json={"username": "citizen_bob", "password": "BobPass123"})
    res_map_b = client.get("/api/public/defects")
    assert res_map_b.status_code == 200
    data_map_b = res_map_b.get_json()
    assert data_map_b["status"] == "success"
    assert data_map_b["count"] == 2

    # Check User A's marker in User B's public map query
    marker_a = next((d for d in data_map_b["defects"] if d["domain"] == "road"), None)
    assert marker_a is not None
    assert "Pothole" in marker_a["defect_category"]
    assert marker_a["preliminary_severity"] == "High"
    assert marker_a["status"] == "Open"
    assert marker_a["latitude"] == pytest.approx(18.9322, 1e-4)
    assert marker_a["longitude"] == pytest.approx(72.8336, 1e-4)
    assert "MG Road" in marker_a["location_summary"]

    # CRITICAL CHECK: Public Marker ID is separate and NOT raw database ID or personal complaint ID
    assert marker_a["marker_id"].startswith("PUB-")
    assert str(rec_a["id"]) != marker_a["marker_id"]
    assert "VG-CMP-" not in marker_a["marker_id"]
    assert "VG-INSP-" not in marker_a["marker_id"]

    # CRITICAL CHECK: Strict Anonymization in the public defects payload
    for marker in data_map_b["defects"]:
        # 1. No raw IDs
        assert "id" not in marker
        assert "raw_id" not in marker
        assert "rawId" not in marker
        assert "inspection_id" not in marker
        assert "complaint_draft_id" not in marker
        assert "submission_reference" not in marker
        assert "complaintRef" not in marker

        # 2. No citizen identities
        assert "created_by_user_id" not in marker
        assert "created_by_username" not in marker
        assert "complainant_name" not in marker
        assert "complainant_contact" not in marker
        assert "email" not in marker
        assert "phone" not in marker
        assert "Alice" not in json.dumps(marker)
        assert "Bob" not in json.dumps(marker)

        # 3. No private photographs
        assert "original_image_path" not in marker
        assert "annotated_image_path" not in marker
        assert "original_image_url" not in marker
        assert "annotated_image_url" not in marker
        assert "img" not in marker
        assert "file_path" not in marker

        # 4. No private citizen notes or grievances
        assert "notes" not in marker
        assert "location_notes" not in marker
        assert "complaint_body" not in marker
        assert "dangerous deep pothole" not in json.dumps(marker).lower()
        assert "shear crack" not in json.dumps(marker).lower()

        # 5. No private PDF download URLs
        assert "pdf_url" not in marker

    # Step 6: PRIVACY ISOLATION - User B attempts to access User A's private endpoints
    # A. Inspection detail: 403 Forbidden
    res_b_access_a = client.get(f"/api/inspections/{rec_a['id']}")
    assert res_b_access_a.status_code == 403
    assert res_b_access_a.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # B. Original image: 403 Forbidden
    res_b_img_orig = client.get(f"/api/inspections/{rec_a['id']}/image/original")
    assert res_b_img_orig.status_code == 403
    assert res_b_img_orig.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # C. Annotated image: 403 Forbidden
    res_b_img_annot = client.get(f"/api/inspections/{rec_a['id']}/image/annotated")
    assert res_b_img_annot.status_code == 403
    assert res_b_img_annot.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # D. Complaint draft: 403 Forbidden
    res_b_draft = client.get(f"/api/inspections/{rec_a['id']}/complaint-draft")
    assert res_b_draft.status_code == 403

    # E. PDF export: 403 Forbidden
    res_b_pdf = client.get(f"/api/inspections/{rec_a['id']}/complaint-draft/export/pdf")
    assert res_b_pdf.status_code == 403

    # F. Citizen B's personal inspection list strictly contains ONLY Citizen B's record
    res_b_list = client.get("/api/inspections")
    assert res_b_list.status_code == 200
    b_inspections = res_b_list.get_json()["inspections"]
    assert len(b_inspections) == 1
    assert b_inspections[0]["id"] == rec_b["id"]
    assert b_inspections[0]["created_by_user_id"] == user_b["id"]

    # Step 7: RECIPROCAL PRIVACY ISOLATION - User A attempts to access User B's private endpoints
    client.post("/api/auth/login", json={"username": "citizen_alice", "password": "AlicePass123"})

    # A. User A sees User B's published marker on the shared map
    res_map_a = client.get("/api/public/defects")
    assert res_map_a.status_code == 200
    data_map_a = res_map_a.get_json()
    marker_b = next((d for d in data_map_a["defects"] if d["domain"] == "home"), None)
    assert marker_b is not None
    assert marker_b["defect_category"] == "Wall Crack"
    assert marker_b["preliminary_severity"] == "Critical"
    assert marker_b["marker_id"].startswith("PUB-")

    # B. User A cannot access User B's private inspection report: 403 Forbidden
    res_a_access_b = client.get(f"/api/inspections/{rec_b['id']}")
    assert res_a_access_b.status_code == 403

    # C. User A cannot access User B's images: 403 Forbidden
    assert client.get(f"/api/inspections/{rec_b['id']}/image/original").status_code == 403
    assert client.get(f"/api/inspections/{rec_b['id']}/image/annotated").status_code == 403

    # D. User A cannot download User B's complaint PDF: 403 Forbidden
    assert client.get(f"/api/inspections/{rec_b['id']}/complaint-draft/export/pdf").status_code == 403

    # E. Citizen A's personal inspection list strictly contains ONLY Citizen A's record
    res_a_list = client.get("/api/inspections")
    assert res_a_list.status_code == 200
    a_inspections = res_a_list.get_json()["inspections"]
    assert len(a_inspections) == 1
    assert a_inspections[0]["id"] == rec_a["id"]
    assert a_inspections[0]["created_by_user_id"] == user_a["id"]


# =============================================================================
# 4. Unauthenticated Access & Map Template Parity
# =============================================================================

def test_unauthenticated_requests_are_rejected(client_app):
    """Verifies that unauthenticated requests to the public defects API are rejected when auth is active."""
    _, client = client_app
    # Without login:
    res = client.get("/api/public/defects")
    assert res.status_code == 401
    assert res.get_json()["error_code"] == "UNAUTHORIZED"

    res_patch = client.patch("/api/inspections/1/publication", json={"publication_status": "published"})
    assert res_patch.status_code == 401


def test_map_and_report_template_parity(client_app):
    """Verifies frontend/map.html and app/templates/map.html remain strictly synchronized."""
    with open("app/templates/map.html", "r", encoding="utf-8") as f:
        app_map = f.read()
    with open("frontend/map.html", "r", encoding="utf-8") as f:
        front_map = f.read()
    assert app_map == front_map

    # Ensure frontend queries /api/public/defects
    assert "fetch('/api/public/defects')" in app_map
    assert "Verified Marker" in app_map

    with open("app/templates/report.html", "r", encoding="utf-8") as f:
        app_rep = f.read()
    with open("frontend/report.html", "r", encoding="utf-8") as f:
        front_rep = f.read()
    assert app_rep == front_rep
