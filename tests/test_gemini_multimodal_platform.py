"""
VisionGuard AI 2.0 — Automated Test Suite for Gemini-Powered Multimodal Platform.

Covers all 17 requirements:
1. Road defect image detection
2. Building defect image detection
3. Multiple defects in one image
4. Clean road image (zero defects detected)
5. Unclear / blurry image handling
6. Invalid image upload
7. Invalid or out-of-bounds bounding box coordinates
8. Gemini API timeout
9. Gemini quota exhaustion (HTTP 429)
10. Missing API key handling
11. OpenCV annotated image generation
12. Inspection persistence
13. Historical report access
14. Authentication enforcement
15. Complaint submission workflow with explicit confirmation
16. Duplicate complaint prevention
17. Unauthorized report access isolation
"""

import io
import os
import json
import time
import pytest
import numpy as np

from app.server import create_app
from ai.gemini_service import GeminiInspectionService
from ai.annotation_service import OpenCVAnnotationEngine
from database.auth import create_user, ROLE_ADMIN, ROLE_CITIZEN
from database.db import init_db, get_inspection_by_id
from database.complaints import get_or_create_complaint_draft, update_complaint_draft


# -----------------------------------------------------------------------------
# Mock Gemini Service Doubles
# -----------------------------------------------------------------------------
class MockGeminiService:
    def __init__(self, mode="road_multiple", model_name="gemini-2.5-flash", configured=True):
        self.mode = mode
        self.model_name = model_name
        self._configured = configured

    def is_configured(self):
        return self._configured

    def analyze_image(self, image_bytes, domain="road", timeout=30.0):
        if not self._configured:
            return {
                "status": "error",
                "error_code": "GEMINI_NOT_CONFIGURED",
                "message": "Google Gemini Vision API key is not configured.",
                "setup_guide": "Set GEMINI_API_KEY in .env",
            }

        if self.mode == "quota_exhausted":
            return {
                "status": "error",
                "error_code": "QUOTA_EXHAUSTED",
                "message": "Google Gemini Vision free-tier rate limit reached. Please wait a moment and try again.",
            }

        if self.mode == "timeout":
            return {
                "status": "error",
                "error_code": "GEMINI_API_ERROR",
                "message": "Gemini Vision request timed out after 30.0s.",
            }

        if self.mode == "clean_surface":
            return {
                "status": "success",
                "inspection_status": "none_detected",
                "domain": domain,
                "defects": [],
                "defect_count": 0,
                "summary": "Preliminary inspection identified no visible structural or roadway defects. Surface appears intact.",
                "preliminary_severity": "low",
                "requires_human_review": True,
                "safety_precautions": ["Routine maintenance only."],
                "disclaimer": "Preliminary visual assessment by Google Gemini Vision.",
            }

        if self.mode == "unclear_image":
            return {
                "status": "success",
                "inspection_status": "unclear_image",
                "domain": domain,
                "defects": [],
                "defect_count": 0,
                "summary": "The provided photograph is unclear or lacks sufficient resolution for definitive defect assessment.",
                "preliminary_severity": "uncertain",
                "requires_human_review": True,
                "safety_precautions": ["Retake photograph under clear illumination."],
                "disclaimer": "Preliminary visual assessment by Google Gemini Vision.",
            }

        if self.mode == "building_defects":
            return {
                "status": "success",
                "inspection_status": "identified",
                "domain": "home",
                "defects": [
                    {
                        "id": "D001",
                        "type": "wall_crack",
                        "title": "Wall Structural Crack",
                        "description": "Diagonal tensile crack traversing plaster substrate.",
                        "severity": "high",
                        "confidence": 0.88,
                        "evidence": "Visible shearing along mortar line.",
                        "recommended_action": "Conduct immediate masonry settlement inspection.",
                        "maintenance_priority": "High Priority (48h)",
                        "safety_guidance": "Monitor for widening; avoid drilling into cracked section.",
                        "bounding_box": {"x1": 0.20, "y1": 0.15, "x2": 0.55, "y2": 0.70},
                        "has_bounding_box": True,
                        "localization_uncertain": False,
                    },
                    {
                        "id": "D002",
                        "type": "dampness_water_damage",
                        "title": "Dampness & Water Infiltration",
                        "description": "Extensive moisture patch with visible salt efflorescence.",
                        "severity": "moderate",
                        "confidence": 0.78,
                        "evidence": "Darkened masonry discoloration with efflorescence crystallisation.",
                        "recommended_action": "Inspect exterior flashing and drainpipes for leaks.",
                        "maintenance_priority": "Scheduled Maintenance (14d)",
                        "safety_guidance": "Ensure ventilation to prevent mold propagation.",
                        "bounding_box": {"x1": 0.60, "y1": 0.40, "x2": 0.88, "y2": 0.85},
                        "has_bounding_box": True,
                        "localization_uncertain": False,
                    }
                ],
                "defect_count": 2,
                "summary": "Visual inspection identified 2 candidate building defects: wall crack and dampness.",
                "preliminary_severity": "high",
                "requires_human_review": True,
                "safety_precautions": ["Keep children away from cracked exterior masonry."],
                "disclaimer": "Preliminary visual assessment by Google Gemini Vision.",
            }

        if self.mode == "invalid_coords":
            # Test normalizing corrupt coordinates
            raw = {
                "status": "identified",
                "defects": [
                    {
                        "id": "D001",
                        "type": "pothole",
                        "severity": "high",
                        "bounding_box": {"x1": 1.5, "y1": 0.3, "x2": 0.2, "y2": 0.8}, # Invalid: x1 > 1.0 and x1 > x2
                    }
                ]
            }
            svc = GeminiInspectionService(api_key="test_key")
            return svc._validate_and_normalize_result(raw, domain="road")

        # Default: road multiple defects
        return {
            "status": "success",
            "inspection_status": "identified",
            "domain": "road",
            "defects": [
                {
                    "id": "D001",
                    "type": "pothole",
                    "title": "Deep Road Cavity / Pothole",
                    "description": "Cavity in wearing course exposing base aggregate.",
                    "severity": "critical",
                    "confidence": 0.92,
                    "evidence": "Sharp fracture edge with missing asphalt layer.",
                    "recommended_action": "Cold-mix asphalt patch within 24 hours.",
                    "maintenance_priority": "Immediate Emergency",
                    "safety_guidance": "Slow vehicular speed to 10 km/h; caution for two-wheelers.",
                    "bounding_box": {"x1": 0.15, "y1": 0.25, "x2": 0.45, "y2": 0.60},
                    "has_bounding_box": True,
                    "localization_uncertain": False,
                },
                {
                    "id": "D002",
                    "type": "alligator_crack",
                    "title": "Alligator Fatigue Cracking",
                    "description": "Interconnected fatigue fractures in wheel path.",
                    "severity": "high",
                    "confidence": 0.85,
                    "evidence": "Hexagonal interconnected crack web.",
                    "recommended_action": "Full-depth structural repair.",
                    "maintenance_priority": "High Priority (48h)",
                    "safety_guidance": "Heavy vehicles should avoid lane shoulder.",
                    "bounding_box": {"x1": 0.50, "y1": 0.35, "x2": 0.85, "y2": 0.75},
                    "has_bounding_box": True,
                    "localization_uncertain": False,
                },
                {
                    "id": "D003",
                    "type": "longitudinal_crack",
                    "title": "Longitudinal Joint Crack",
                    "description": "Linear crack parallel to pavement centerline.",
                    "severity": "moderate",
                    "confidence": 0.75,
                    "evidence": "Continuous longitudinal seam opening.",
                    "recommended_action": "Hot-pour sealant application.",
                    "maintenance_priority": "Scheduled Maintenance (14d)",
                    "safety_guidance": "Normal precautions.",
                    "bounding_box": {"x1": 0.05, "y1": 0.10, "x2": 0.18, "y2": 0.90},
                    "has_bounding_box": True,
                    "localization_uncertain": False,
                },
                {
                    "id": "D004",
                    "type": "surface_deterioration",
                    "title": "Asphalt Raveling",
                    "description": "Loss of fine aggregate creating rough surface texture.",
                    "severity": "low",
                    "confidence": 0.68,
                    "evidence": "Pebbled coarse surface texture.",
                    "recommended_action": "Slurry seal surfacing.",
                    "maintenance_priority": "Routine Monitoring",
                    "safety_guidance": "Caution in wet weather.",
                    "bounding_box": None,
                    "has_bounding_box": False,
                    "localization_uncertain": True,
                }
            ],
            "defect_count": 4,
            "summary": "Visual inspection identified 4 candidate road distress items including critical pothole and fatigue cracks.",
            "preliminary_severity": "critical",
            "requires_human_review": True,
            "safety_precautions": [
                "Slow down to prevent tire rim damage.",
                "Avoid standing water over cavities."
            ],
            "disclaimer": "Preliminary visual assessment by Google Gemini Vision.",
        }


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def gemini_test_env(tmp_path):
    test_db = str(tmp_path / "gemini_platform_test.db")
    init_db(test_db)

    admin = create_user("admin_gemini", "AdminSecret1234!", ROLE_ADMIN, email="admin@vg.io", db_path=test_db)
    alice = create_user("citizen_alice", "AliceSecret1234!", ROLE_CITIZEN, email="alice@vg.io", db_path=test_db)
    bob = create_user("citizen_bob", "BobSecret1234!", ROLE_CITIZEN, email="bob@vg.io", db_path=test_db)

    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db,
        "AUTH_ENABLED": True,
        "ENFORCE_CSRF": True,
        "SECRET_KEY": "a" * 32,
        "AI_PROVIDER": "gemini",
        "gemini_service": MockGeminiService(mode="road_multiple"),
        "annotation_engine": OpenCVAnnotationEngine(),
    })

    return {
        "app": app,
        "test_db": test_db,
        "admin": admin,
        "alice": alice,
        "bob": bob,
    }


def login_helper(client, username, password):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.get_json()}"
    return res.get_json().get("csrf_token")


def get_real_sample_jpeg():
    with open("data/evaluation_benchmark/images/benchmark_08_d20_alligator_urban.jpg", "rb") as f:
        return f.read()


# =============================================================================
# Test 1: Road Defect Image Detection
# =============================================================================
def test_01_road_defect_image(gemini_test_env):
    """Road defect photograph triggers Gemini analysis, returns structured report and overlay."""
    app = gemini_test_env["app"]
    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        img_bytes = get_real_sample_jpeg()

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(img_bytes), "road_test.jpg"), "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["domain"] == "road"
        assert data["ai_provider"] == "google_gemini"
        assert "VisionGuard Multimodal AI" in data["model_info"]["architecture"]
        assert data["defect_count"] >= 1
        assert "annotated_image" in data and len(data["annotated_image"]) > 100


# =============================================================================
# Test 2: Building Defect Image Detection
# =============================================================================
def test_02_building_defect_image(gemini_test_env):
    """Building defect photograph (wall cracks, dampness) triggers building domain analysis."""
    app = gemini_test_env["app"]
    app.gemini_service = MockGeminiService(mode="building_defects")

    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        with open("data/test_representative_home_defects/01_wall_crack_zenodo_022.jpg", "rb") as f:
            home_bytes = f.read()

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(home_bytes), "wall.jpg"), "domain": "home", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["domain"] == "home"
        assert data["defect_count"] == 2
        types = [d["type"] for d in data["defects"]]
        assert "wall_crack" in types
        assert "dampness_water_damage" in types


# =============================================================================
# Test 3: Multiple Defects in Single Image
# =============================================================================
def test_03_multiple_defects_in_single_image(gemini_test_env):
    """Identifies and itemizes multiple defects in one photo with individual IDs and bounding boxes."""
    app = gemini_test_env["app"]
    app.gemini_service = MockGeminiService(mode="road_multiple")

    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        img_bytes = get_real_sample_jpeg()

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(img_bytes), "multi.jpg"), "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["defect_count"] == 4
        ids = [d["id"] for d in data["defects"]]
        assert ids == ["D001", "D002", "D003", "D004"]


# =============================================================================
# Test 4: Clean Road Image (Zero Defects)
# =============================================================================
def test_04_clean_road_image_no_defects(gemini_test_env):
    """Clean, sound road surface returns zero defects and positive structural condition summary."""
    app = gemini_test_env["app"]
    app.gemini_service = MockGeminiService(mode="clean_surface")

    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        img_bytes = get_real_sample_jpeg()

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(img_bytes), "sound.jpg"), "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["defect_count"] == 0
        assert "no visible" in data["summary"].lower()


# =============================================================================
# Test 5: Unclear / Blurry Image
# =============================================================================
def test_05_unclear_or_blurry_image(gemini_test_env):
    """Unclear or degraded image is diagnosed as unclear without fabricating detections."""
    app = gemini_test_env["app"]
    app.gemini_service = MockGeminiService(mode="unclear_image")

    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        img_bytes = get_real_sample_jpeg()

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(img_bytes), "blurry.jpg"), "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["defect_count"] == 0
        assert "unclear" in data["summary"].lower()


# =============================================================================
# Test 6: Invalid Image Upload
# =============================================================================
def test_06_invalid_image_upload(gemini_test_env):
    """Corrupt or non-image stream is rejected with HTTP 400 INVALID_IMAGE."""
    app = gemini_test_env["app"]
    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        bad_bytes = b"not_a_real_image_payload_corrupted"

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(bad_bytes), "test.jpg"), "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code == 400
        assert res.get_json()["error_code"] == "INVALID_IMAGE"


# =============================================================================
# Test 7: Invalid Bounding Box Coordinates
# =============================================================================
def test_07_invalid_bounding_box_coordinates(gemini_test_env):
    """Degenerate or out-of-bounds coordinates are safely clamped or rejected without crashing."""
    svc = GeminiInspectionService(api_key="mock_key")
    # Coordinates where x1 > 1.0 or x1 >= x2
    norm_box, valid = svc._normalize_bounding_box({"x1": 1.2, "y1": 0.2, "x2": 0.4, "y2": 0.6})
    # Must reject invalid box
    assert not valid or norm_box["x1"] <= norm_box["x2"]


# =============================================================================
# Test 8: Gemini API Timeout Handling
# =============================================================================
def test_08_gemini_api_timeout(gemini_test_env):
    """Gemini API timeouts are caught and returned as structured JSON error."""
    app = gemini_test_env["app"]
    app.gemini_service = MockGeminiService(mode="timeout")

    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        img_bytes = get_real_sample_jpeg()

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(img_bytes), "timeout.jpg"), "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code in (500, 504)
        assert "timed out" in res.get_json()["message"].lower()


# =============================================================================
# Test 9: Gemini Quota Exhaustion (HTTP 429)
# =============================================================================
def test_09_gemini_quota_exhaustion(gemini_test_env):
    """Quota exhaustion triggers friendly HTTP 429 error explaining free tier limits."""
    app = gemini_test_env["app"]
    app.gemini_service = MockGeminiService(mode="quota_exhausted")

    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        img_bytes = get_real_sample_jpeg()

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(img_bytes), "quota.jpg"), "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code == 429
        data = res.get_json()
        assert data["error_code"] == "QUOTA_EXHAUSTED"
        assert "rate limit" in data["message"].lower()


# =============================================================================
# Test 10: Missing API Key Configuration
# =============================================================================
def test_10_missing_api_key_configuration(gemini_test_env):
    """When GEMINI_API_KEY is not configured, returns clear HTTP 400 error with setup guidance."""
    app = gemini_test_env["app"]
    app.gemini_service = MockGeminiService(configured=False)

    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        img_bytes = get_real_sample_jpeg()

        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(img_bytes), "nokey.jpg"), "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            content_type="multipart/form-data"
        )
        assert res.status_code == 400
        data = res.get_json()
        assert data["error_code"] == "GEMINI_NOT_CONFIGURED"
        assert "GEMINI_API_KEY" in data["message"]
        assert "setup_instructions" in data


# =============================================================================
# Test 11: OpenCV Annotated Image Generation
# =============================================================================
def test_11_annotated_image_generation_opencv():
    """Annotation engine generates distinct visual overlay without mutating original image array."""
    engine = OpenCVAnnotationEngine()
    original = np.zeros((480, 640, 3), dtype=np.uint8)
    defects = [
        {"id": "D001", "type": "pothole", "severity": "critical", "bounding_box": {"x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.6}}
    ]

    annotated = engine.annotate_image(original, defects, domain="road")
    assert annotated is not original
    assert np.any(annotated > 0)
    assert np.all(original == 0)  # Original array preserved untouched


# =============================================================================
# Test 12: Inspection Persistence
# =============================================================================
def test_12_inspection_persistence(gemini_test_env):
    """Citizen can persist inspection record with Gemini detections in SQLite database."""
    app = gemini_test_env["app"]
    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        payload = {
            "image_name": "persisted_crack.jpg",
            "domain": "road",
            "road_name": "Marine Drive",
            "area": "Nariman Point",
            "city": "Mumbai",
            "latitude": 18.9220,
            "longitude": 72.8230,
            "defect_count": 2,
            "detections": [
                {"id": "D001", "type": "pothole", "severity": "high"},
                {"id": "D002", "type": "alligator_crack", "severity": "moderate"}
            ],
            "csrf_token": csrf
        }
        res = client.post(
            "/api/inspections",
            json=payload,
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 201
        rec = res.get_json()["inspection"]
        assert rec["created_by_username"] == "citizen_alice"
        assert rec["defect_count"] == 2


# =============================================================================
# Test 13: Historical Report Access
# =============================================================================
def test_13_historical_report_access(gemini_test_env):
    """Citizen can access their saved inspection report via GET /api/inspections/<id>."""
    app = gemini_test_env["app"]
    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        res = client.post(
            "/api/inspections",
            json={"image_name": "hist.jpg", "domain": "road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf}
        )
        insp_id = res.get_json()["inspection"]["id"]

        get_res = client.get(f"/api/inspections/{insp_id}")
        assert get_res.status_code == 200
        assert get_res.get_json()["inspection"]["id"] == insp_id


# =============================================================================
# Test 14: Authentication Enforcement
# =============================================================================
def test_14_authentication_enforcement(gemini_test_env):
    """Unauthenticated guests cannot access private inspection APIs."""
    app = gemini_test_env["app"]
    with app.test_client() as client:
        res = client.get("/api/dashboard/stats")
        assert res.status_code == 401


# =============================================================================
# Test 15: Complaint Submission Workflow
# =============================================================================
def test_15_complaint_submission_workflow(gemini_test_env):
    """Full Option B complaint submission flow: draft retrieval, citizen update, and PDF export."""
    app = gemini_test_env["app"]
    with app.test_client() as client:
        csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        # 1. Create inspection
        res = client.post(
            "/api/inspections",
            json={"image_name": "comp_test.jpg", "road_name": "SV Road", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf}
        )
        insp_id = res.get_json()["inspection"]["id"]

        # 2. Get complaint draft
        d_res = client.get(f"/api/inspections/{insp_id}/complaint-draft")
        assert d_res.status_code == 200
        draft = d_res.get_json()["draft"]
        assert draft["status"] == "draft"

        # 3. Explicit citizen update / submission
        patch_res = client.put(
            f"/api/inspections/{insp_id}/complaint-draft",
            json={
                "complainant_name": "Alice Citizen",
                "complainant_contact": "alice@test.local",
                "status": "draft",
                "csrf_token": csrf
            },
            headers={"X-CSRF-Token": csrf}
        )
        assert patch_res.status_code == 200

        # 4. Export draft to PDF
        pdf_res = client.get(f"/api/inspections/{insp_id}/complaint-draft/export/pdf")
        assert pdf_res.status_code == 200
        assert pdf_res.headers.get("Content-Type") == "application/pdf"


# =============================================================================
# Test 16: Duplicate Complaint Prevention
# =============================================================================
def test_16_duplicate_complaint_prevention(gemini_test_env):
    """Repeated calls to create complaint draft for the same inspection return the existing draft."""
    db_path = gemini_test_env["test_db"]
    alice_id = gemini_test_env["alice"]["id"]

    # Save inspection manually
    from database.db import save_inspection
    rec = save_inspection({"image_name": "dup.jpg", "created_by_user_id": alice_id}, db_path=db_path)
    insp_id = rec["id"]

    d1 = get_or_create_complaint_draft(insp_id, user_id=alice_id, username="citizen_alice", db_path=db_path)
    d2 = get_or_create_complaint_draft(insp_id, user_id=alice_id, username="citizen_alice", db_path=db_path)
    assert d1["id"] == d2["id"]  # Same unique complaint record


# =============================================================================
# Test 17: Unauthorized Report Access Isolation
# =============================================================================
def test_17_unauthorized_report_access(gemini_test_env):
    """Citizen Bob cannot access Citizen Alice's inspection report or complaint draft."""
    app = gemini_test_env["app"]
    with app.test_client() as client:
        alice_csrf = login_helper(client, "citizen_alice", "AliceSecret1234!")
        res = client.post(
            "/api/inspections",
            json={"image_name": "alice_private.jpg", "csrf_token": alice_csrf},
            headers={"X-CSRF-Token": alice_csrf}
        )
        alice_insp_id = res.get_json()["inspection"]["id"]

    with app.test_client() as client:
        bob_csrf = login_helper(client, "citizen_bob", "BobSecret1234!")
        # Bob tries to access Alice's inspection
        get_res = client.get(f"/api/inspections/{alice_insp_id}")
        assert get_res.status_code == 403
        assert get_res.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # Bob tries to access Alice's complaint draft
        d_res = client.get(f"/api/inspections/{alice_insp_id}/complaint-draft")
        assert d_res.status_code == 403

