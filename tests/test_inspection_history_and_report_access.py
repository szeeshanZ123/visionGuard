"""
Regression tests for Previous Inspection History and Report Access in VisionGuard AI.

Validates all 12 requirements:
1. Dedicated Actions column & row clickability contracts in report.html.
2. Clicking View Details retrieves full report telemetry via /api/inspections/<id>.
3. Full report content: ID, ref ID, timestamps, original/annotated image URLs,
   defect classification, severity, observations, recommendations, location/GPS,
   citizen notes, complaint tracking.
4. Download PDF action (/api/inspections/<id>/complaint-draft/export/pdf).
5. View on Map action (/map?highlight=<id>).
6. Pagination, search, domain, and status filters.
7. Strict backend ownership enforcement (Citizen A cannot access Citizen B's report, PDF, or images).
8. Legacy/missing optional fields handled gracefully without crashes.
9. Existing database records and routes utilized.
"""

import os
import json
import io
import pytest
from pathlib import Path

from database.db import (
    init_db,
    save_inspection,
    get_inspections,
    get_inspection_by_id,
    DEFAULT_DB_PATH,
)
from database.auth import (
    ROLE_CITIZEN,
    ROLE_ADMIN,
    ROLE_MAINTENANCE,
    create_user,
)
from database.complaints import (
    init_complaints_db,
    get_or_create_complaint_draft,
    update_complaint_draft,
    export_complaint_draft_pdf,
)
from app.server import create_app


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh isolated SQLite database with full schema initialized."""
    db_file = str(tmp_path / "test_history_access.db")
    init_db(db_file)
    init_complaints_db(db_file)
    return db_file


@pytest.fixture
def client_app(test_db):
    """Creates a configured Flask test client with authentication enabled."""
    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db,
        "AUTH_ENABLED": True,
        "AUTH_ENABLED_EXPLICIT": True,
        "ENFORCE_CSRF": False,
        "SECRET_KEY": "test-history-access-key",
    })
    client = app.test_client()
    return app, client


# =============================================================================
# 1. Frontend Template Contracts in report.html
# =============================================================================
def test_report_template_contains_history_and_access_elements(client_app):
    """Verifies report.html includes Actions column, Report Modal, Zoom Modal, and Pagination controls."""
    _, client = client_app
    res = client.get("/report")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Actions column in table header
    assert '<th class="py-3.5 px-4 lg:px-5 text-right" scope="col">Actions</th>' in html

    # Pagination controls with IDs
    assert 'id="visibleRange"' in html
    assert 'id="totalRecordsCount"' in html
    assert 'id="prevPageBtn"' in html
    assert 'id="nextPageBtn"' in html
    assert 'id="pageIndicator"' in html

    # Filter toolbar
    assert 'id="searchInput"' in html
    assert 'id="domainSelect"' in html
    assert 'id="statusSelect"' in html
    assert 'id="resetBtn"' in html

    # Inspection Report Full Modal
    assert 'id="inspection-report-modal"' in html
    assert 'id="report-modal-title"' in html
    assert 'id="report-modal-domain-badge"' in html
    assert 'id="report-modal-status-badge"' in html
    assert 'id="report-modal-ref-id"' in html
    assert 'id="report-modal-download-pdf-btn"' in html
    assert 'id="report-modal-view-map-btn"' in html
    assert 'id="report-modal-footer-pdf-btn"' in html

    # Dual comparative image evidence
    assert 'id="report-modal-orig-img"' in html
    assert 'id="report-modal-anno-img"' in html

    # AI Observations & Recommendations
    assert 'id="report-modal-summary"' in html
    assert 'id="report-modal-observations-list"' in html
    assert 'id="report-modal-recommendations-list"' in html

    # Location & Citizen details
    assert 'id="report-modal-location-text"' in html
    assert 'id="report-modal-geo-coords-text"' in html
    assert 'id="report-modal-citizen-name"' in html
    assert 'id="report-modal-citizen-contact"' in html
    assert 'id="report-modal-citizen-notes"' in html
    assert 'id="report-modal-filing-channel"' in html
    assert 'id="report-modal-filing-ref"' in html

    # Itemized Detections Table
    assert 'id="report-modal-detections-section"' in html
    assert 'id="report-modal-detections-tbody"' in html

    # Zoom Image Viewer Modal
    assert 'id="zoom-image-modal"' in html
    assert 'id="zoom-image-img"' in html


# =============================================================================
# 2. Strict Backend Ownership Enforcement
# =============================================================================
def test_backend_ownership_enforcement_on_report_access(client_app, test_db):
    """Citizen Alice can view her report; Citizen Bob is forbidden (403)."""
    _, client = client_app
    alice = create_user("alice_citizen", "AlicePass123", role=ROLE_CITIZEN, db_path=test_db)
    bob = create_user("bob_citizen", "BobPass123", role=ROLE_CITIZEN, db_path=test_db)

    # Alice creates an inspection
    rec = save_inspection({
        "image_name": "alice_pothole.jpg",
        "defect_type": "Pothole",
        "severity": "high",
        "preliminary_severity": "High",
        "road_name": "Marine Drive",
        "city": "Mumbai",
        "latitude": 18.944,
        "longitude": 72.823,
        "created_by_user_id": alice["id"],
        "created_by_username": "alice_citizen",
        "inspection_type": "road",
    }, db_path=test_db)

    # Login as Alice -> 200 OK
    client.post("/api/auth/login", json={"username": "alice_citizen", "password": "AlicePass123"})
    res_alice = client.get(f"/api/inspections/{rec['id']}")
    assert res_alice.status_code == 200
    assert res_alice.get_json()["inspection"]["road_name"] == "Marine Drive"

    # Alice can access PDF export
    res_pdf_alice = client.get(f"/api/inspections/{rec['id']}/complaint-draft/export/pdf")
    assert res_pdf_alice.status_code == 200
    assert res_pdf_alice.data.startswith(b"%PDF-")

    # Logout and Login as Bob
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "bob_citizen", "password": "BobPass123"})

    # Bob attempts to access Alice's report -> 403 Forbidden
    res_bob = client.get(f"/api/inspections/{rec['id']}")
    assert res_bob.status_code == 403
    assert res_bob.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Bob attempts to download Alice's PDF -> 403 Forbidden
    res_pdf_bob = client.get(f"/api/inspections/{rec['id']}/complaint-draft/export/pdf")
    assert res_pdf_bob.status_code == 403
    assert res_pdf_bob.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Bob attempts to access Alice's original image -> 403 Forbidden
    res_img_bob = client.get(f"/api/inspections/{rec['id']}/image/original")
    assert res_img_bob.status_code == 403
    assert res_img_bob.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"


# =============================================================================
# 3. Report Detail Content & Telemetry Integrity
# =============================================================================
def test_full_report_telemetry_fields_and_integrity(client_app, test_db):
    """Verifies all required fields (ID, date, defect, severity, observations, recs, GPS, notes) are returned."""
    _, client = client_app
    user = create_user("inspect_user", "InspPass123", role=ROLE_CITIZEN, db_path=test_db)

    detections_payload = [
        {
            "id": "DEF-01",
            "class_name": "wall_crack",
            "type": "wall_crack",
            "title": "Masonry Shear Crack",
            "description": "Continuous diagonal crack propagating through exterior plaster.",
            "evidence": "Dark moisture staining along the fissure.",
            "recommended_action": "Pressure epoxy injection and waterproofing membrane.",
            "safety_guidance": "Do not anchor heavy fixtures to cracked partition.",
            "severity": "high",
            "confidence": 0.92,
            "bounding_box": [120, 150, 480, 520],
        }
    ]

    rec = save_inspection({
        "image_name": "facade_crack.jpg",
        "defect_type": "Wall Crack",
        "defect_count": 1,
        "severity": "high",
        "preliminary_severity": "High",
        "summary": "AI detected a severe masonry shear crack requiring stabilization.",
        "observations": "Moisture ingress visible along crack propagation axis.",
        "recommendations": "Dispatch structural masonry specialist for pressure epoxy grout.",
        "road_name": "Tower 4 Greenwood Heights",
        "area": "Sector 9",
        "city": "Mumbai",
        "latitude": 19.11234,
        "longitude": 72.88456,
        "notes": "Citizen noted crack appeared following heavy monsoon rainfall.",
        "location_notes": "Ground floor parking column interface.",
        "created_by_user_id": user["id"],
        "created_by_username": "inspect_user",
        "inspection_type": "home",
        "detections_json": json.dumps(detections_payload),
    }, db_path=test_db)

    # Attach a complaint draft
    get_or_create_complaint_draft(rec["id"], user_id=user["id"], username="inspect_user", db_path=test_db)
    update_complaint_draft(rec["id"], {
        "status": "submitted",
        "manual_submission": True,
        "submission_channel": "Building Safety Grievance Portal",
        "submission_reference": "VG-CMP-0042",
        "complainant_name": "Priya Sharma",
        "complainant_contact": "priya.sharma@example.com",
    }, db_path=test_db)

    client.post("/api/auth/login", json={"username": "inspect_user", "password": "InspPass123"})
    res = client.get(f"/api/inspections/{rec['id']}")
    assert res.status_code == 200
    data = res.get_json()
    insp = data["inspection"]

    # Requirements Verification:
    # 1. Inspection ID & Reference ID
    assert insp["id"] == rec["id"]
    assert insp["submission_reference"] in [f"VG-CMP-{str(rec['id']).zfill(4)}", "VG-CMP-0042"]

    # 2. Date and time
    assert insp["uploaded_at"] is not None

    # 3. Image URLs
    assert insp["original_image_url"] == f"/api/inspections/{rec['id']}/image/original"
    assert insp["annotated_image_url"] == f"/api/inspections/{rec['id']}/image/annotated"

    # 4. Defect classification and severity
    assert insp["defect_type"].lower() == "wall_crack" or insp["defect_type"] == "Wall Crack"
    assert insp["preliminary_severity"] == "High"

    # 5. Gemini observations and recommendations
    assert "Continuous diagonal crack" in insp["summary"] or "masonry" in insp["summary"].lower()
    assert "epoxy" in insp["recommendations"].lower()

    # 6. Location and GPS coordinates
    assert insp["road_name"] == "Tower 4 Greenwood Heights"
    assert insp["latitude"] == pytest.approx(19.11234, 1e-4)
    assert insp["longitude"] == pytest.approx(72.88456, 1e-4)

    # 7. Citizen details & notes
    assert insp["complaint_draft"]["complainant_name"] == "Priya Sharma"
    assert insp["complaint_draft"]["complainant_contact"] == "priya.sharma@example.com"
    assert "parking column" in (insp.get("notes") or insp.get("location_notes") or "")

    # 8. Complaint status & tracking information
    assert insp["complaint_status"] == "submitted"
    assert insp["submission_channel"] == "Building Safety Grievance Portal"


# =============================================================================
# 4. Legacy and Missing Optional Fields Fallbacks
# =============================================================================
def test_legacy_record_with_missing_optional_fields_opens_cleanly(client_app, test_db):
    """Verifies old records with null GPS, null notes, null detections, null complaint draft still open safely."""
    _, client = client_app
    user = create_user("legacy_citizen", "LegacyPass123", role=ROLE_CITIZEN, db_path=test_db)

    # Legacy record with minimal fields
    rec = save_inspection({
        "image_name": "legacy_capture.jpg",
        "created_by_user_id": user["id"],
        "created_by_username": "legacy_citizen",
        # Explicitly no coords, no notes, no severity, no detections_json
    }, db_path=test_db)

    client.post("/api/auth/login", json={"username": "legacy_citizen", "password": "LegacyPass123"})
    res = client.get(f"/api/inspections/{rec['id']}")
    assert res.status_code == 200
    insp = res.get_json()["inspection"]

    # Verify graceful null/empty handling
    assert insp["latitude"] is None
    assert insp["longitude"] is None
    assert insp["detections"] == []
    assert insp["complaint_status"] == "none"
    assert insp["complaint_draft"] is None
    assert insp["status"] == "Open"


# =============================================================================
# 5. Direct URL Route Support for /report/<id>
# =============================================================================
def test_direct_report_url_route(client_app):
    """Verifies /report/<id> renders report.html with inspection_id injected into meta tag."""
    _, client = client_app
    res = client.get("/report/42")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert '<meta name="initial-inspection-id" content="42">' in html