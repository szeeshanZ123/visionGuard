"""
Tests for Dashboard Analytics and Defect Management in VisionGuard AI.

Verifies:
1. get_dashboard_analytics on empty database (safe defaults, no divide-by-zero).
2. get_dashboard_analytics with actual saved inspections (accurate KPI counts and category distribution).
3. GET /api/dashboard/stats endpoint response and disclaimer.
4. Filtering in get_inspections and GET /api/inspections by status, category, and search query.
5. Defect management lifecycle updates including "In Progress", "Open", and "Resolved".
"""

import os
import json
import pytest
from app.server import create_app
from ai.detection.detector import DefectDetectionService
from database.db import (
    init_db,
    save_inspection,
    get_inspections,
    get_dashboard_analytics,
    update_inspection_status,
    ALLOWED_STATUSES,
)


@pytest.fixture
def test_db_path(tmp_path):
    db_file = str(tmp_path / "dash_test.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def client(tmp_path):
    test_db = str(tmp_path / "api_dash_test.db")
    init_db(test_db)
    app = create_app(
        detector=DefectDetectionService(model_path="ai/models/best.pt"),
        test_config={"TESTING": True, "DATABASE_PATH": test_db}
    )
    with app.test_client() as c:
        yield c, test_db


def test_dashboard_analytics_empty_db(test_db_path):
    """Verifies that an empty database returns accurate zero metrics and empty structures."""
    stats = get_dashboard_analytics(db_path=test_db_path)
    assert stats["total_inspections"] == 0
    assert stats["total_defects"] == 0
    assert stats["open_records"] == 0
    assert stats["in_progress_records"] == 0
    assert stats["resolved_records"] == 0
    assert stats["defect_categories"] == {
        "Longitudinal Crack": 0,
        "Transverse Crack": 0,
        "Alligator Crack": 0,
        "Pothole": 0,
    }
    assert stats["recent_inspections"] == []


def test_dashboard_analytics_with_real_records(test_db_path):
    """Verifies analytics computation against authentic defect records and statuses."""
    # Record 1: 2 defects (Longitudinal + Alligator), Open
    save_inspection({
        "image_name": "road_1.jpg",
        "road_name": "Western Express Highway KM 14",
        "location_notes": "Northbound lane outer wheelpath",
        "status": "Open",
        "detections": [
            {"class_id": 0, "class_name": "D00_longitudinal_crack", "distress_category": "Longitudinal Crack", "confidence": 0.45},
            {"class_id": 2, "class_name": "D20_alligator_crack", "distress_category": "Alligator Crack", "confidence": 0.55},
        ]
    }, db_path=test_db_path)

    # Record 2: 1 defect (Pothole), In Progress
    save_inspection({
        "image_name": "road_2.jpg",
        "road_name": "LBS Marg, Kurla West",
        "location_notes": "Near railway station junction",
        "status": "In Progress",
        "detections": [
            {"class_id": 3, "class_name": "D40_pothole", "distress_category": "Pothole", "confidence": 0.78},
        ]
    }, db_path=test_db_path)

    # Record 3: 1 defect (Transverse Crack), Under Review
    save_inspection({
        "image_name": "road_3.jpg",
        "road_name": "Eastern Freeway Pier 42",
        "location_notes": "Expansion joint settlement",
        "status": "Under Review",
        "detections": [
            {"class_id": 1, "class_name": "D10_transverse_crack", "distress_category": "Transverse Crack", "confidence": 0.62},
        ]
    }, db_path=test_db_path)

    # Record 4: 0 defects (Sound road), Resolved
    save_inspection({
        "image_name": "road_4.jpg",
        "road_name": "Bandra-Worli Sea Link",
        "location_notes": "Freshly resurfaced asphalt",
        "status": "Resolved",
        "detections": []
    }, db_path=test_db_path)

    # Record 5: 3 defects (2 Potholes, 1 Longitudinal), Repair in Progress
    save_inspection({
        "image_name": "road_5.jpg",
        "road_name": "SVT Road, Santacruz",
        "location_notes": "Heavy vehicle lane distress",
        "status": "Repair in Progress",
        "detections": [
            {"class_id": 3, "class_name": "D40_pothole", "distress_category": "Pothole", "confidence": 0.65},
            {"class_id": 3, "class_name": "D40_pothole", "distress_category": "Pothole", "confidence": 0.70},
            {"class_id": 0, "class_name": "D00_longitudinal_crack", "distress_category": "Longitudinal Crack", "confidence": 0.38},
        ]
    }, db_path=test_db_path)

    # Record 6: 1 defect (Alligator Crack), Resolved
    save_inspection({
        "image_name": "road_6.jpg",
        "road_name": "MG Road Central",
        "location_notes": "Patch repair verified administratively",
        "status": "Resolved",
        "detections": [
            {"class_id": 2, "class_name": "D20_alligator_crack", "distress_category": "Alligator Crack", "confidence": 0.81},
        ]
    }, db_path=test_db_path)

    # Query analytics
    stats = get_dashboard_analytics(db_path=test_db_path)

    assert stats["total_inspections"] == 6
    assert stats["total_defects"] == 8  # 2 + 1 + 1 + 0 + 3 + 1
    assert stats["open_records"] == 1
    assert stats["in_progress_records"] == 3  # In Progress + Under Review + Repair in Progress
    assert stats["resolved_records"] == 2

    cats = stats["defect_categories"]
    assert cats["Longitudinal Crack"] == 2
    assert cats["Transverse Crack"] == 1
    assert cats["Alligator Crack"] == 2
    assert cats["Pothole"] == 3
    assert sum(cats.values()) == 8

    # Recent inspections must be capped at 5 and sorted newest first
    assert len(stats["recent_inspections"]) == 5
    assert stats["recent_inspections"][0]["road_name"] == "MG Road Central"


def test_dashboard_api_stats_endpoint(client):
    """Verifies GET /api/dashboard/stats returns real SQLite analytics and administrative disclaimer."""
    c, test_db = client
    # Seed a record
    save_inspection({
        "image_name": "highway.jpg",
        "road_name": "NH-48 KM 88",
        "status": "In Progress",
        "detections": [
            {"class_id": 0, "class_name": "D00_longitudinal_crack", "distress_category": "Longitudinal Crack", "confidence": 0.42}
        ]
    }, db_path=test_db)

    res = c.get("/api/dashboard/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "stats" in data
    assert data["stats"]["total_inspections"] == 1
    assert data["stats"]["total_defects"] == 1
    assert data["stats"]["in_progress_records"] == 1
    assert data["stats"]["defect_categories"]["Longitudinal Crack"] == 1
    assert "disclaimer" in data
    assert "administrative workflow" in data["disclaimer"]


def test_inspections_filtering_query_params(client):
    """Verifies filtering by status, category, and search query via GET /api/inspections."""
    c, test_db = client

    save_inspection({
        "image_name": "pothole_kurla.jpg",
        "road_name": "LBS Marg, Kurla",
        "location_notes": "Deep pothole near depot",
        "status": "In Progress",
        "detections": [{"class_id": 3, "class_name": "D40_pothole", "distress_category": "Pothole", "confidence": 0.75}]
    }, db_path=test_db)

    save_inspection({
        "image_name": "crack_freeway.jpg",
        "road_name": "Eastern Freeway",
        "location_notes": "Longitudinal joint distress",
        "status": "Open",
        "detections": [{"class_id": 0, "class_name": "D00_longitudinal_crack", "distress_category": "Longitudinal Crack", "confidence": 0.50}]
    }, db_path=test_db)

    save_inspection({
        "image_name": "clean_sealink.jpg",
        "road_name": "Bandra-Worli Sea Link",
        "location_notes": "Sound surface",
        "status": "Resolved",
        "detections": []
    }, db_path=test_db)

    # 1. Filter by status: In Progress
    res_status = c.get("/api/inspections?status=In Progress")
    assert res_status.status_code == 200
    items = res_status.get_json()["inspections"]
    assert len(items) == 1
    assert items[0]["road_name"] == "LBS Marg, Kurla"

    # 2. Filter by category: Pothole
    res_cat = c.get("/api/inspections?category=Pothole")
    assert res_cat.status_code == 200
    items = res_cat.get_json()["inspections"]
    assert len(items) == 1
    assert items[0]["road_name"] == "LBS Marg, Kurla"

    # 3. Filter by category: Sound (0 defects)
    res_sound = c.get("/api/inspections?category=Sound")
    assert res_sound.status_code == 200
    items = res_sound.get_json()["inspections"]
    assert len(items) == 1
    assert items[0]["road_name"] == "Bandra-Worli Sea Link"

    # 4. Search query: Kurla
    res_q = c.get("/api/inspections?q=Kurla")
    assert res_q.status_code == 200
    items = res_q.get_json()["inspections"]
    assert len(items) == 1
    assert "Kurla" in items[0]["road_name"]

    # 5. Combined filter: Status=Open and category=Longitudinal
    res_combo = c.get("/api/inspections?status=Open&category=Longitudinal")
    assert res_combo.status_code == 200
    items = res_combo.get_json()["inspections"]
    assert len(items) == 1
    assert items[0]["road_name"] == "Eastern Freeway"


def test_status_lifecycle_in_progress_and_persistence(client):
    """Verifies updating record status to In Progress, Open, and Resolved persists across queries."""
    c, test_db = client

    rec = save_inspection({
        "image_name": "defect.jpg",
        "road_name": "Ring Road Sector 18",
        "status": "Open",
        "detections": [{"class_id": 0, "class_name": "D00_longitudinal_crack", "confidence": 0.4}]
    }, db_path=test_db)
    rec_id = rec["id"]

    # Update to In Progress
    patch_res = c.patch(f"/api/inspections/{rec_id}/status", json={
        "status": "In Progress",
        "notes": "Field survey initiated by contractor"
    })
    assert patch_res.status_code == 200
    pdata = patch_res.get_json()
    assert pdata["inspection"]["status"] == "In Progress"
    assert pdata["inspection"]["notes"] == "Field survey initiated by contractor"

    # Verify persistent state via GET
    get_res = c.get(f"/api/inspections/{rec_id}")
    assert get_res.status_code == 200
    fetched = get_res.get_json()["inspection"]
    assert fetched["status"] == "In Progress"
    assert fetched["notes"] == "Field survey initiated by contractor"

    # Update to Resolved
    res_resolved = c.patch(f"/api/inspections/{rec_id}/status", json={
        "status": "Resolved",
        "notes": "Work completed and inspected"
    })
    assert res_resolved.status_code == 200
    assert res_resolved.get_json()["inspection"]["status"] == "Resolved"
