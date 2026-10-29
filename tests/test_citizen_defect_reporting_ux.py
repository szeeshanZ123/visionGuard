"""
Tests for Phase 5: Simplified Citizen Defect Reporting UX in VisionGuard AI.

Validates:
1. Simplified Citizen Inspection Form:
   - Technical confidence slider and tiled slicing mode controls are hidden from the citizen view.
   - Default threshold is 0.25 and default mode is standard.
   - Main inspection action button is labeled "Detect Defect".
   - Target selection provides simple, nontechnical options ("Road / Street" vs. "Building / Property").
   - Plain-English capture guidelines provide clear instructions without ML jargon.
   - Optional location card is secondary and collapsible without blocking analysis.
2. Human-Centered Results Presentation:
   - Results container includes plain-language findings summary (#citizenFindingsSummary).
   - Raw model coordinates and telemetry tables are tucked inside collapsible advanced details.
   - Zero-defect state provides reassuring guidance and retry advice without application errors.
3. Post-Detection Citizen Actions:
   - Clear "Submit Report" button to persist the report into SQLite / PostgreSQL.
   - Clear "Cancel" button to reset the form and try another photo.
   - Successful submission guides citizens to track the report under "My Reports".
4. CSS & JS Contracts:
   - styles.css contains citizen findings cards, certainty badges, and zero-defect styling.
   - app.js contains certainty tier calculations, plain-language defect dictionaries, and cancel/reset handlers.
"""

import os
import json
import io
import pytest
from pathlib import Path
from PIL import Image

from app.server import create_app
from database.db import init_db, get_inspection_by_id
from database.auth import create_user, ROLE_CITIZEN

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def test_db_path(tmp_path):
    """Provides an isolated SQLite database."""
    db_file = str(tmp_path / "test_citizen_ux.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def app_and_client(test_db_path):
    """Configures a Flask test client with test configuration."""
    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db_path,
        "AUTH_ENABLED": True,
        "AUTH_ENABLED_EXPLICIT": True,
        "ENFORCE_CSRF": False,
        "SECRET_KEY": "test-citizen-ux-secret-key",
    })
    client = app.test_client()
    return app, client


# =============================================================================
# 1. HTML Template Contract Tests
# =============================================================================
class TestCitizenReportFormHtmlContract:
    def test_technical_ai_controls_hidden_with_safe_defaults(self, app_and_client):
        """Verifies confidence slider and tiled slicing mode are hidden from citizen view with safe defaults."""
        _, client = app_and_client
        res = client.get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        # Technical controls container must be hidden
        assert 'id="technicalAiControls"' in html
        assert 'style="display: none;"' in html

        # Slider and modes must still exist with safe defaults
        assert 'id="confSlider"' in html
        assert 'value="0.25"' in html
        assert 'id="inspectionModeGroup"' in html
        assert 'value="standard" checked' in html

    def test_inspect_button_renamed_to_detect_defect(self, app_and_client):
        """Verifies the primary action button is labeled 'Detect Defect'."""
        _, client = app_and_client
        res = client.get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        assert 'id="inspectBtn"' in html
        assert 'id="inspectBtnText">Detect Defect</span>' in html
        assert "Run Defect Inspection" not in html

    def test_nontechnical_defect_categories(self, app_and_client):
        """Verifies nontechnical problem selection: Road / Street vs Building / Property."""
        _, client = app_and_client
        res = client.get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        assert 'id="domainRoadBtn"' in html
        assert "Road / Street" in html
        assert 'id="domainHomeBtn"' in html
        assert "Building / Property" in html
        # Should not display technical checkpoint model names in the selector
        assert "YOLOv8 Nano (RDD2022 India)" not in html

    def test_plain_language_guidelines_and_secondary_location(self, app_and_client):
        """Verifies photo instructions and collapsible secondary location card."""
        _, client = app_and_client
        res = client.get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        assert 'id="guidelinesToggle"' in html
        assert "Photo Guidelines for Defect Reporting" in html
        assert 'id="guidelinesLightingText"' in html
        assert 'id="guidelinesOrientationText"' in html

        # Secondary collapsible location details
        assert 'id="inspectionLocationDetails"' in html
        assert "Add Location Details" in html
        assert 'id="inspectionLocationCard"' in html
        assert 'id="btnUseCurrentLocation"' in html
        assert 'id="inspLocationRoad"' in html

    def test_human_centered_results_and_post_detection_actions(self, app_and_client):
        """Verifies findings summary card, post-detection Submit/Cancel actions, and collapsed telemetry."""
        _, client = app_and_client
        res = client.get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        # Human-centered findings card
        assert 'id="citizenFindingsCard"' in html
        assert 'id="citizenFindingsSummary"' in html

        # Submit and Cancel post-detection actions
        assert 'id="saveInspectionBtn"' in html
        assert 'Submit Report' in html
        assert 'id="cancelReportBtn"' in html
        assert "Cancel & Try Another Photo" in html

        # Advanced technical coordinates collapsed inside details
        assert 'id="technicalTelemetryDetails"' in html
        assert "Technical AI Details & Coordinates (Advanced)" in html
        assert 'id="metaTable"' in html
        assert 'id="detectionsTable"' in html


# =============================================================================
# 2. CSS Stylesheet Contract Tests
# =============================================================================
class TestCitizenReportFormCssContract:
    def test_citizen_findings_css_classes_present(self):
        """Verifies required CSS rules for citizen findings, certainty badges, and zero-defect boxes."""
        css_path = PROJECT_ROOT / "app" / "static" / "css" / "styles.css"
        css = css_path.read_text(encoding="utf-8")

        assert ".citizen-findings-card" in css
        assert ".citizen-finding-item" in css
        assert ".citizen-certainty-badge" in css
        assert ".certainty-high" in css
        assert ".certainty-moderate" in css
        assert ".certainty-low" in css
        assert ".citizen-zero-defects-box" in css
        assert ".secondary-location-summary" in css
        assert ".technical-telemetry-accordion" in css


# =============================================================================
# 3. JavaScript Contract Tests
# =============================================================================
class TestCitizenReportFormJsContract:
    def test_javascript_plain_language_helpers_present(self):
        """Verifies app.js contains citizen finding meta mapper and certainty tier resolver."""
        js_path = PROJECT_ROOT / "app" / "static" / "js" / "app.js"
        js = js_path.read_text(encoding="utf-8")

        assert "function getCitizenFindingMeta" in js
        assert "function getCertaintyTier" in js
        assert "function resetCitizenInspectionForm" in js
        assert "High Certainty" in js
        assert "Moderate Certainty" in js
        assert "Low Certainty" in js

    def test_javascript_action_flow_contract(self):
        """Verifies app.js handles form locking, button renaming, cancel action, and My Reports routing."""
        js_path = PROJECT_ROOT / "app" / "static" / "js" / "app.js"
        js = js_path.read_text(encoding="utf-8")

        # Button text updates
        assert 'btnText.textContent = "Detect Defect";' in js
        assert 'btnText.textContent = "Submit Report";' in js or 'saveInspectionBtn.querySelector(".btn-text").textContent = "Submit Report";' in js

        # Cancel button wiring
        assert 'cancelReportBtn.addEventListener("click"' in js
        assert "resetCitizenInspectionForm" in js

        # Post-submit routing to My Reports for citizens
        assert 'if (currentUser && currentUser.role === "citizen")' in js
        assert 'switchView("dashboard");' in js


# =============================================================================
# 4. Backend Persistence & Zero Defect Flow Tests
# =============================================================================
class TestCitizenReportSubmissionApi:
    def test_citizen_can_submit_report_and_retrieve_under_my_reports(self, app_and_client, test_db_path):
        """Verifies full roundtrip: citizen submits inspection with default status Open and tracks it."""
        _, client = app_and_client

        # Create citizen user and log in
        user = create_user("test_citizen_flow", "Password123!", role=ROLE_CITIZEN, db_path=test_db_path)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
            sess["username"] = user["username"]
            sess["role"] = user["role"]

        # Save inspection as citizen
        save_payload = {
            "image_name": "street_crack.jpg",
            "original_image_path": "uploads/street_crack.jpg",
            "annotated_image_path": "annotated/street_crack_annotated.jpg",
            "road_name": "MG Road Corridor",
            "area": "Downtown",
            "city": "Bengaluru",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "location_notes": "Hazardous crack near crosswalk",
            "status": "Open",
            "inspection_type": "road",
            "inspection_mode": "standard",
            "confidence_threshold": 0.25,
            "detections": [
                {
                    "class_id": 0,
                    "class_name": "D00",
                    "distress_category": "Longitudinal Cracking",
                    "confidence": 0.88,
                    "bbox": {"x1": 50, "y1": 60, "x2": 200, "y2": 180, "width": 150, "height": 120},
                    "source": "global"
                }
            ]
        }

        res = client.post("/api/inspections", json=save_payload)
        assert res.status_code == 201
        data = res.get_json()
        assert data["status"] == "success"
        inspection_id = data["inspection"]["id"]

        # Verify saved record in database
        record = get_inspection_by_id(inspection_id, db_path=test_db_path)
        assert record is not None
        assert record["status"] == "Open"
        assert record["created_by_user_id"] == user["id"]
        assert record["inspection_type"] == "road"

        # Verify record appears under My Reports (my_reports=1)
        my_reports_res = client.get("/api/inspections?my_reports=1")
        assert my_reports_res.status_code == 200
        my_reports_data = my_reports_res.get_json()
        assert my_reports_data["count"] == 1
        assert my_reports_data["inspections"][0]["id"] == inspection_id
        assert my_reports_data["inspections"][0]["status"] == "Open"
        assert my_reports_data["inspections"][0]["original_image_url"] is not None
        assert my_reports_data["inspections"][0]["annotated_image_url"] is not None

