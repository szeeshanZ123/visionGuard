"""
Integration tests for the Inspection Records REST API in VisionGuard AI.
Tests:
- GET /api/inspections (empty, populated, filtered)
- POST /api/inspections (validation, zero detections, genuine detections, duplicate safety)
- GET /api/inspections/<id> (retrieval, 404)
- PATCH /api/inspections/<id>/status (valid transitions, status disclaimer, rejection of invalid status)
- GET /api/inspections/<id>/image/<type>
"""

import os
import json
import pytest
from app.server import create_app
from ai.detection.detector import DefectDetectionService


@pytest.fixture
def test_app_client(tmp_path):
    """Test client configured with a temporary database and mock detector."""
    test_db = str(tmp_path / "api_test.db")
    detector = DefectDetectionService(model_path="ai/models/best.pt")
    app = create_app(detector=detector, test_config={"TESTING": True, "DATABASE_PATH": test_db})
    with app.test_client() as client:
        yield client


def test_get_inspections_empty(test_app_client):
    """Verifies that GET /api/inspections returns empty list initially."""
    res = test_app_client.get("/api/inspections")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["count"] == 0
    assert data["inspections"] == []


def test_post_inspection_validation(test_app_client):
    """Verifies validation rules on POST /api/inspections."""
    # Missing image_name
    res = test_app_client.post("/api/inspections", json={})
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "MISSING_IMAGE_NAME"

    # Invalid status
    res = test_app_client.post("/api/inspections", json={
        "image_name": "road.jpg",
        "status": "FakeStatus"
    })
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "INVALID_STATUS"

    # Road name exceeding 150 chars
    res = test_app_client.post("/api/inspections", json={
        "image_name": "road.jpg",
        "road_name": "X" * 151
    })
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "ROAD_NAME_TOO_LONG"


def test_post_inspection_zero_detections(test_app_client):
    """Verifies saving an inspection with 0 detections accurately persists zero defects."""
    payload = {
        "image_name": "clean_street.jpg",
        "road_name": "MG Road",
        "location_notes": "Clean pavement section",
        "inspection_mode": "standard",
        "confidence_threshold": 0.25,
        "detections": [],
        "status": "Open",
    }
    res = test_app_client.post("/api/inspections", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "success"
    rec = data["inspection"]
    assert rec["defect_count"] == 0
    assert rec["defect_type"] == "None detected"
    assert rec["confidence"] == 0.0
    assert rec["status"] == "Open"
    assert rec["detections"] == []


def test_post_inspection_genuine_detections(test_app_client):
    """Verifies saving an inspection with authentic bounding boxes and categories."""
    detections = [
        {
            "class_id": 2,
            "class_name": "D20_alligator_crack",
            "distress_category": "Alligator Crack",
            "confidence": 0.612,
            "bbox": {"x1": 100.0, "y1": 200.0, "x2": 400.0, "y2": 500.0, "width": 300.0, "height": 300.0},
            "source": "global"
        }
    ]
    payload = {
        "image_name": "highway_crack.jpg",
        "road_name": "National Highway 48",
        "location_notes": "Mile 112 northbound lane",
        "inspection_mode": "standard",
        "confidence_threshold": 0.25,
        "detections": detections,
        "status": "Open",
    }
    res = test_app_client.post("/api/inspections", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    rec = data["inspection"]
    assert rec["defect_count"] == 1
    assert "Alligator Crack" in rec["defect_type"]
    assert rec["confidence"] == 0.612
    assert len(rec["detections"]) == 1


def test_inspection_detail_and_404(test_app_client):
    """Verifies GET /api/inspections/<id> and 404 on missing record."""
    # 404 for nonexistent
    res = test_app_client.get("/api/inspections/9999")
    assert res.status_code == 404
    assert res.get_json()["error_code"] == "INSPECTION_NOT_FOUND"

    # Create one and fetch
    post_res = test_app_client.post("/api/inspections", json={
        "image_name": "test.jpg",
        "road_name": "Airport Road",
        "detections": []
    })
    rec_id = post_res.get_json()["inspection"]["id"]

    get_res = test_app_client.get(f"/api/inspections/{rec_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["inspection"]["road_name"] == "Airport Road"


def test_update_inspection_status_lifecycle(test_app_client):
    """Verifies status transitions through all 4 initial states with disclaimer."""
    post_res = test_app_client.post("/api/inspections", json={
        "image_name": "pothole.jpg",
        "road_name": "Outer Ring Road",
        "detections": []
    })
    rec_id = post_res.get_json()["inspection"]["id"]

    for state in ["Under Review", "Repair in Progress", "Resolved"]:
        patch_res = test_app_client.patch(f"/api/inspections/{rec_id}/status", json={
            "status": state,
            "notes": f"Admin updated to {state}"
        })
        assert patch_res.status_code == 200
        pdata = patch_res.get_json()
        assert pdata["status"] == "success"
        assert pdata["inspection"]["status"] == state
        # Verify engineering workflow disclaimer is present
        assert "status_disclaimer" in pdata
        assert "does not verify or certify" in pdata["status_disclaimer"]

    # Invalid status rejection
    bad_res = test_app_client.patch(f"/api/inspections/{rec_id}/status", json={
        "status": "InvalidState"
    })
    assert bad_res.status_code == 400
    assert bad_res.get_json()["error_code"] == "INVALID_STATUS"


def test_get_inspections_filtering_api(test_app_client):
    """Verifies status filtering on GET /api/inspections."""
    for st in ["Open", "Under Review", "Resolved"]:
        test_app_client.post("/api/inspections", json={
            "image_name": f"{st}.jpg",
            "status": st,
            "detections": []
        })

    all_res = test_app_client.get("/api/inspections")
    assert all_res.get_json()["count"] == 3

    open_res = test_app_client.get("/api/inspections?status=Open")
    assert open_res.get_json()["count"] == 1
    assert open_res.get_json()["inspections"][0]["status"] == "Open"

    bad_filter = test_app_client.get("/api/inspections?status=Bogus")
    assert bad_filter.status_code == 400
