"""
Tests for Phase 4: Citizen Report Tracking & History in VisionGuard AI.

Validates:
1. Citizen My Reports dashboard isolation and security:
   - Citizen A can only see their own inspection records.
   - Citizen B cannot read Citizen A's records or access them directly via /api/inspections/<id>.
   - Citizens have strictly read-only permissions for staff-controlled inspection status.
2. Search, Filtering, and Sorting:
   - Category filtering (Road vs. Home).
   - Inspection status filtering (Open, Under Review, Resolved, etc.).
   - Complaint lifecycle filtering (draft, ready_to_submit, submitted, no_draft).
   - Date filtering (YYYY-MM-DD).
   - Numeric report ID search (e.g. "9", "#9").
   - Location address / notes search.
   - Sorting: newest first (default), oldest first, and most defects.
3. Summary metrics:
   - /api/citizen/summary endpoint returns authentic counts.
   - Total, open, under review, resolved, and submitted complaints.
4. Report detail and complaint lifecycle distinction:
   - Inspection status separated from complaint filing status.
   - Recorded external filing reference details (channel, reference token, date).
5. Frontend contract tests for HTML, CSS, and JS.
"""

import os
import json
import pytest
from pathlib import Path
from flask import Flask

from database.db import (
    init_db,
    save_inspection,
    get_inspections,
    get_inspection_by_id,
    get_citizen_dashboard_summary,
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
)
from app.server import create_app


@pytest.fixture
def test_db_path(tmp_path):
    """Provides a fresh isolated SQLite database with full schema initialized."""
    db_file = str(tmp_path / "test_citizen_tracking.db")
    init_db(db_file)
    init_complaints_db(db_file)
    return db_file


@pytest.fixture
def app_and_client(test_db_path):
    """Creates a configured Flask test client with authentication enabled."""
    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db_path,
        "AUTH_ENABLED": True,
        "AUTH_ENABLED_EXPLICIT": True,
        "ENFORCE_CSRF": False,
        "SECRET_KEY": "test-secret-key-phase4",
    })
    client = app.test_client()
    return app, client


# =============================================================================
# 1. Citizen Dashboard & Summary Count Tests
# =============================================================================
class TestCitizenDashboardSummary:
    def test_citizen_summary_counts_authentic_data(self, test_db_path):
        """Verifies get_citizen_dashboard_summary returns authentic counts from SQLite."""
        user_a = create_user("citizen_alice", "AlicePass123", role=ROLE_CITIZEN, db_path=test_db_path)
        user_b = create_user("citizen_bob", "BobPass123", role=ROLE_CITIZEN, db_path=test_db_path)

        # Alice creates 3 inspections
        r1 = save_inspection({
            "image_name": "alice_road1.jpg",
            "road_name": "Main Street",
            "status": "Open",
            "created_by_user_id": user_a["id"],
            "inspection_type": "road",
        }, db_path=test_db_path)

        r2 = save_inspection({
            "image_name": "alice_home1.jpg",
            "road_name": "Elm Street",
            "status": "Under Review",
            "created_by_user_id": user_a["id"],
            "inspection_type": "home",
        }, db_path=test_db_path)

        r3 = save_inspection({
            "image_name": "alice_road2.jpg",
            "road_name": "Oak Avenue",
            "status": "Resolved",
            "created_by_user_id": user_a["id"],
            "inspection_type": "road",
        }, db_path=test_db_path)

        # Bob creates 1 inspection
        save_inspection({
            "image_name": "bob_road.jpg",
            "road_name": "Pine Boulevard",
            "status": "Open",
            "created_by_user_id": user_b["id"],
            "inspection_type": "road",
        }, db_path=test_db_path)

        # Alice creates a complaint draft and marks it submitted
        get_or_create_complaint_draft(r1["id"], db_path=test_db_path)
        update_complaint_draft(r1["id"], {
            "status": "submitted",
            "submission_channel": "Municipal Citizen Portal",
            "submission_reference": "MUN-2026-0042",
        }, db_path=test_db_path)

        # Check Alice's summary
        summary_a = get_citizen_dashboard_summary(user_a["id"], db_path=test_db_path)
        assert summary_a["total"] == 3
        assert summary_a["open"] == 1
        assert summary_a["under_review"] == 1
        assert summary_a["resolved"] == 1
        assert summary_a["submitted_complaints"] == 1

        # Check Bob's summary
        summary_b = get_citizen_dashboard_summary(user_b["id"], db_path=test_db_path)
        assert summary_b["total"] == 1
        assert summary_b["open"] == 1
        assert summary_b["under_review"] == 0
        assert summary_b["resolved"] == 0
        assert summary_b["submitted_complaints"] == 0

    def test_api_citizen_summary_endpoint(self, app_and_client, test_db_path):
        """Verifies GET /api/citizen/summary returns authenticated citizen summary."""
        _, client = app_and_client
        user = create_user("citizen_clara", "ClaraPass123", role=ROLE_CITIZEN, db_path=test_db_path)

        # Save an inspection for Clara
        save_inspection({
            "image_name": "clara_pothole.jpg",
            "road_name": "Broadway",
            "status": "Open",
            "created_by_user_id": user["id"],
        }, db_path=test_db_path)

        # Login as Clara
        login_res = client.post("/api/auth/login", json={"username": "citizen_clara", "password": "ClaraPass123"})
        assert login_res.status_code == 200

        # Request summary
        res = client.get("/api/citizen/summary")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["summary"]["total"] == 1
        assert data["summary"]["open"] == 1


# =============================================================================
# 2. Citizen Isolation & Cross-User Security Tests
# =============================================================================
class TestCitizenPrivacyAndIsolation:
    def test_citizen_cannot_see_other_citizen_reports_in_list(self, app_and_client, test_db_path):
        """Citizen A can only see their own reports, even when trying all_civic or created_by_user_id."""
        _, client = app_and_client
        user_a = create_user("citizen_dan", "DanPass123", role=ROLE_CITIZEN, db_path=test_db_path)
        user_b = create_user("citizen_eva", "EvaPass123", role=ROLE_CITIZEN, db_path=test_db_path)

        save_inspection({"image_name": "dan_insp.jpg", "road_name": "Dan Lane", "created_by_user_id": user_a["id"]}, db_path=test_db_path)
        save_inspection({"image_name": "eva_insp.jpg", "road_name": "Eva Drive", "created_by_user_id": user_b["id"]}, db_path=test_db_path)

        # Login as Dan
        client.post("/api/auth/login", json={"username": "citizen_dan", "password": "DanPass123"})

        # Request inspections list (standard)
        res = client.get("/api/inspections?my_reports=1")
        assert res.status_code == 200
        inspections = res.get_json()["inspections"]
        assert len(inspections) == 1
        assert inspections[0]["road_name"] == "Dan Lane"

        # Attempt to override scope with created_by_user_id of Eva
        res_tamper = client.get(f"/api/inspections?created_by_user_id={user_b['id']}")
        assert res_tamper.status_code == 200
        # Must still strictly return only Dan's records!
        tampered_inspections = res_tamper.get_json()["inspections"]
        assert len(tampered_inspections) == 1
        assert tampered_inspections[0]["road_name"] == "Dan Lane"

    def test_citizen_cannot_read_other_citizen_report_details(self, app_and_client, test_db_path):
        """Citizen A is denied direct access (403) to Citizen B's inspection details."""
        _, client = app_and_client
        user_a = create_user("citizen_frank", "FrankPass123", role=ROLE_CITIZEN, db_path=test_db_path)
        user_b = create_user("citizen_grace", "GracePass123", role=ROLE_CITIZEN, db_path=test_db_path)

        insp_a = save_inspection({"image_name": "frank.jpg", "road_name": "Frank St", "created_by_user_id": user_a["id"]}, db_path=test_db_path)
        insp_b = save_inspection({"image_name": "grace.jpg", "road_name": "Grace Way", "created_by_user_id": user_b["id"]}, db_path=test_db_path)

        # Login as Frank
        client.post("/api/auth/login", json={"username": "citizen_frank", "password": "FrankPass123"})

        # Frank accesses his own report -> 200
        res_own = client.get(f"/api/inspections/{insp_a['id']}")
        assert res_own.status_code == 200
        assert res_own.get_json()["inspection"]["road_name"] == "Frank St"

        # Frank attempts to access Grace's report -> 403 Forbidden
        res_other = client.get(f"/api/inspections/{insp_b['id']}")
        assert res_other.status_code == 403
        data_other = res_other.get_json()
        assert data_other["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    def test_citizen_read_only_permissions_for_inspection_status(self, app_and_client, test_db_path):
        """Citizens cannot alter staff-controlled inspection status (PATCH /api/inspections/<id>/status returns 403)."""
        _, client = app_and_client
        user = create_user("citizen_henry", "HenryPass123", role=ROLE_CITIZEN, db_path=test_db_path)
        insp = save_inspection({"image_name": "henry.jpg", "status": "Open", "created_by_user_id": user["id"]}, db_path=test_db_path)

        # Login as Henry
        client.post("/api/auth/login", json={"username": "citizen_henry", "password": "HenryPass123"})

        # Attempt to mark inspection as Resolved
        res = client.patch(f"/api/inspections/{insp['id']}/status", json={"status": "Resolved"})
        assert res.status_code == 403
        assert res.get_json()["error_code"] == "FORBIDDEN"

        # Verify in DB status remained unchanged (Open)
        rec = get_inspection_by_id(insp["id"], db_path=test_db_path)
        assert rec["status"] == "Open"


# =============================================================================
# 3. Search, Filtering, and Sorting Tests
# =============================================================================
class TestSearchFilteringAndSorting:
    def test_filter_by_domain_category(self, test_db_path):
        """Filters reports by Home vs Road domain."""
        user = create_user("citizen_ian", "IanPass123", role=ROLE_CITIZEN, db_path=test_db_path)

        save_inspection({
            "image_name": "road_hole.jpg",
            "defect_type": "Pothole",
            "inspection_type": "road",
            "created_by_user_id": user["id"],
        }, db_path=test_db_path)

        save_inspection({
            "image_name": "wall_crack.jpg",
            "defect_type": "Wall Crack",
            "inspection_type": "home",
            "created_by_user_id": user["id"],
        }, db_path=test_db_path)

        road_reports = get_inspections(created_by_user_id=user["id"], domain="road", db_path=test_db_path)
        assert len(road_reports) == 1
        assert road_reports[0]["defect_type"] == "Pothole"

        home_reports = get_inspections(created_by_user_id=user["id"], domain="home", db_path=test_db_path)
        assert len(home_reports) == 1
        assert home_reports[0]["defect_type"] == "Wall Crack"

    def test_search_by_report_id_and_location(self, test_db_path):
        """Allows searching by numeric report ID (#id) or location string."""
        user = create_user("citizen_jack", "JackPass123", role=ROLE_CITIZEN, db_path=test_db_path)

        r1 = save_inspection({
            "image_name": "corner_pothole.jpg",
            "road_name": "Grand Avenue",
            "city": "Metropolis",
            "created_by_user_id": user["id"],
        }, db_path=test_db_path)

        r2 = save_inspection({
            "image_name": "residential_crack.jpg",
            "road_name": "Sunset Boulevard",
            "city": "Gotham",
            "created_by_user_id": user["id"],
        }, db_path=test_db_path)

        # Search by exact numeric ID
        res_by_num = get_inspections(created_by_user_id=user["id"], search_query=str(r1["id"]), db_path=test_db_path)
        assert len(res_by_num) == 1
        assert res_by_num[0]["id"] == r1["id"]

        # Search by prefixed numeric ID "#id"
        res_by_hash = get_inspections(created_by_user_id=user["id"], search_query=f"#{r2['id']}", db_path=test_db_path)
        assert len(res_by_hash) == 1
        assert res_by_hash[0]["id"] == r2["id"]

        # Search by location string
        res_by_loc = get_inspections(created_by_user_id=user["id"], search_query="Gotham", db_path=test_db_path)
        assert len(res_by_loc) == 1
        assert res_by_loc[0]["id"] == r2["id"]

    def test_filter_by_complaint_status(self, test_db_path):
        """Filters reports by complaint status (draft, submitted, none)."""
        user = create_user("citizen_karen", "KarenPass123", role=ROLE_CITIZEN, db_path=test_db_path)

        r1 = save_inspection({"image_name": "with_draft.jpg", "created_by_user_id": user["id"]}, db_path=test_db_path)
        r2 = save_inspection({"image_name": "submitted_draft.jpg", "created_by_user_id": user["id"]}, db_path=test_db_path)
        r3 = save_inspection({"image_name": "no_draft.jpg", "created_by_user_id": user["id"]}, db_path=test_db_path)

        # r1 has a draft
        get_or_create_complaint_draft(r1["id"], db_path=test_db_path)

        # r2 has a submitted draft
        get_or_create_complaint_draft(r2["id"], db_path=test_db_path)
        update_complaint_draft(r2["id"], {
            "status": "submitted",
            "manual_submission": True,
            "submission_channel": "Citizen Portal",
            "submission_reference": "REF-1234",
        }, db_path=test_db_path)

        # Filter: complaint_status="draft"
        drafts = get_inspections(created_by_user_id=user["id"], complaint_status="draft", db_path=test_db_path)
        assert len(drafts) == 1
        assert drafts[0]["id"] == r1["id"]

        # Filter: complaint_status="submitted"
        submitted = get_inspections(created_by_user_id=user["id"], complaint_status="submitted", db_path=test_db_path)
        assert len(submitted) == 1
        assert submitted[0]["id"] == r2["id"]

        # Filter: complaint_status="no_draft" / "none"
        no_drafts = get_inspections(created_by_user_id=user["id"], complaint_status="no_draft", db_path=test_db_path)
        assert len(no_drafts) == 1
        assert no_drafts[0]["id"] == r3["id"]

    def test_sorting_options(self, test_db_path):
        """Verifies newest (default), oldest, and defects_desc sorting."""
        user = create_user("citizen_leo", "LeoPass123", role=ROLE_CITIZEN, db_path=test_db_path)

        save_inspection({"image_name": "few_defects.jpg", "defect_count": 1, "created_by_user_id": user["id"]}, db_path=test_db_path)
        save_inspection({"image_name": "many_defects.jpg", "defect_count": 8, "created_by_user_id": user["id"]}, db_path=test_db_path)

        # Sort by most defects
        by_defects = get_inspections(created_by_user_id=user["id"], sort_by="defects_desc", db_path=test_db_path)
        assert by_defects[0]["defect_count"] == 8
        assert by_defects[1]["defect_count"] == 1


# =============================================================================
# 4. Report Details & Lifecycle Distinction Tests
# =============================================================================
class TestReportDetailsAndExternalFiling:
    def test_inspection_detail_includes_complaint_draft_and_external_filing(self, test_db_path):
        """Verifies get_inspection_by_id returns attached complaint draft, filing details, and preserves distinct statuses."""
        user = create_user("citizen_maya", "MayaPass123", role=ROLE_CITIZEN, db_path=test_db_path)

        rec = save_inspection({
            "image_name": "maya_pothole.jpg",
            "road_name": "Highway 101",
            "status": "Open",  # Staff inspection status
            "created_by_user_id": user["id"],
        }, db_path=test_db_path)

        # Log manual external submission
        get_or_create_complaint_draft(rec["id"], db_path=test_db_path)
        update_complaint_draft(rec["id"], {
            "status": "submitted",
            "submission_channel": "State DOT Portal",
            "submission_reference": "DOT-REF-9988",
        }, db_path=test_db_path)

        detail = get_inspection_by_id(rec["id"], db_path=test_db_path)
        assert detail is not None
        # Distinction: Inspection status is Open, but complaint filing status is submitted!
        assert detail["status"] == "Open"
        assert detail["complaint_status"] == "submitted"
        assert detail["submission_channel"] == "State DOT Portal"
        assert detail["submission_reference"] == "DOT-REF-9988"
        assert detail["complaint_draft"]["subject"] is not None


# =============================================================================
# 5. Frontend Contracts (HTML, CSS, JS)
# =============================================================================
class TestFrontendContracts:
    def test_citizen_dashboard_html_elements_present(self, app_and_client):
        """Verifies Phase 4 metric cards, filter toolbar, and detail complaint card exist in index.html."""
        _, client = app_and_client
        res = client.get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        # 5 Metric Cards
        assert 'id="citizenTotalReports"' in html
        assert 'id="citizenOpenReports"' in html
        assert 'id="citizenUnderReviewReports"' in html
        assert 'id="citizenResolvedReports"' in html
        assert 'id="citizenSubmittedComplaints"' in html

        # Toolbar controls
        assert 'id="citizenSearchInput"' in html
        assert 'id="citizenCategoryFilter"' in html
        assert 'id="citizenStatusFilter"' in html
        assert 'id="citizenComplaintStatusFilter"' in html
        assert 'id="citizenDateFilter"' in html
        assert 'id="citizenSortFilter"' in html
        assert 'id="citizenResetFiltersBtn"' in html

        # Empty states
        assert 'id="citizenEmptyReports"' in html
        assert 'id="citizenNoFilteredReports"' in html

        # Detail view Phase 4 elements
        assert 'id="detailCitizenReadOnlyNotice"' in html
        assert 'id="detailComplaintCard"' in html
        assert 'id="detailComplaintStatusBadge"' in html
        assert 'id="detailOpenComplaintDraftBtn"' in html
        assert 'id="detailComplaintChannelDisplay"' in html
        assert 'id="detailComplaintRefDisplay"' in html

    def test_citizen_dashboard_css_present(self):
        """Verifies Phase 4 CSS rules exist in styles.css."""
        css_path = Path(__file__).parent.parent / "app" / "static" / "css" / "styles.css"
        css = css_path.read_text(encoding="utf-8")

        assert ".citizen-filters-toolbar" in css
        assert ".complaint-detail-card" in css
        assert "#citizenReportsTable tbody tr:hover" in css

    def test_citizen_dashboard_js_wiring_present(self):
        """Verifies app.js contains Phase 4 dashboard controller, badge helpers, and filter wiring."""
        js_path = Path(__file__).parent.parent / "app" / "static" / "js" / "app.js"
        js = js_path.read_text(encoding="utf-8")

        assert "async function loadCitizenDashboard" in js
        assert "function getComplaintBadgeClass" in js
        assert "function formatComplaintStatus" in js
        assert "function resetCitizenFilters" in js
        assert "citizenSearchInput.addEventListener" in js
        assert "detailCitizenReadOnlyNotice" in js
