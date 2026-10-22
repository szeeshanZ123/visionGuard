"""
Unit and integration tests for Phase 4.2: Interactive Defect Map.

Verifies:
- Querying inspections with coordinates filter (has_coords=true).
- Excluding inspections without coordinates when filtering for map markers.
- Retention of un-geotagged records in the general inspections list.
- Defect category filtering (Longitudinal, Transverse, Alligator, Pothole, Sound Surface).
- Workflow status filtering (Open, In Progress, Under Review, Repair in Progress, Resolved).
- Keyword search on road_name, area, city, and location notes.
- Graceful handling of empty datasets (returns empty list, count=0, HTTP 200).
- Extreme boundary coordinates (-90, 90, -180, 180).
- Safe handling of malformed or invalid coordinates.
"""

import pytest
from app.server import create_app
from ai.detection.detector import DefectDetectionService
from database.db import (
    init_db,
    save_inspection,
    get_inspections,
    get_db_connection,
)


@pytest.fixture
def test_app_client(tmp_path):
    """Test client configured with a temporary database."""
    test_db = str(tmp_path / "map_test.db")
    detector = DefectDetectionService(model_path="ai/models/best.pt")
    app = create_app(detector=detector, test_config={"TESTING": True, "DATABASE_PATH": test_db})
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary SQLite database path for direct DB tests."""
    db_file = str(tmp_path / "direct_map_test.db")
    init_db(db_file)
    return db_file


# -----------------------------------------------------------------------------
# 1. Coordinate-Based Filtering (Backend / Database)
# -----------------------------------------------------------------------------

def test_has_coords_filter_in_database(temp_db_path):
    """Verifies that get_inspections(has_coords=True) returns only records with valid lat/lon."""
    # 1. Geotagged record with Longitudinal Crack
    save_inspection({
        "image_name": "geo1.jpg",
        "road_name": "MG Road",
        "area": "Indiranagar",
        "city": "Bengaluru",
        "latitude": 12.9784,
        "longitude": 77.6408,
        "status": "Open",
        "defect_type": "Longitudinal Crack",
        "defect_count": 1,
    }, db_path=temp_db_path)

    # 2. Geotagged record with Pothole
    save_inspection({
        "image_name": "geo2.jpg",
        "road_name": "Ring Road",
        "area": "Lajpat Nagar",
        "city": "New Delhi",
        "latitude": 28.5678,
        "longitude": 77.2433,
        "status": "In Progress",
        "defect_type": "Pothole",
        "defect_count": 2,
    }, db_path=temp_db_path)

    # 3. Non-geotagged record (coords are None)
    save_inspection({
        "image_name": "non_geo.jpg",
        "road_name": "NH 44",
        "area": "",
        "city": "Nagpur",
        "latitude": None,
        "longitude": None,
        "status": "Resolved",
        "defect_type": "Alligator Crack",
        "defect_count": 1,
    }, db_path=temp_db_path)

    # All records in DB
    all_recs = get_inspections(db_path=temp_db_path)
    assert len(all_recs) == 3

    # Only geotagged records (for defect map)
    geo_recs = get_inspections(has_coords=True, db_path=temp_db_path)
    assert len(geo_recs) == 2
    for r in geo_recs:
        assert r["latitude"] is not None
        assert r["longitude"] is not None

    # Only non-geotagged records
    non_geo_recs = get_inspections(has_coords=False, db_path=temp_db_path)
    assert len(non_geo_recs) == 1
    assert non_geo_recs[0]["image_name"] == "non_geo.jpg"
    assert non_geo_recs[0]["latitude"] is None


# -----------------------------------------------------------------------------
# 2. REST API /api/inspections with has_coords Parameter
# -----------------------------------------------------------------------------

def test_api_inspections_has_coords(test_app_client):
    """Verifies GET /api/inspections?has_coords=true excludes un-geotagged inspections."""
    # Create geotagged record
    test_app_client.post("/api/inspections", json={
        "image_name": "map_pin1.jpg",
        "road_name": "SV Road",
        "area": "Andheri",
        "city": "Mumbai",
        "latitude": 19.1136,
        "longitude": 72.8697,
        "status": "Open",
        "defect_count": 1,
        "detections": [{
            "distress_category": "Transverse Crack",
            "class_name": "D10",
            "confidence": 0.78,
            "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50, "width": 40, "height": 40}
        }]
    })

    # Create un-geotagged record
    test_app_client.post("/api/inspections", json={
        "image_name": "map_pin2.jpg",
        "road_name": "Link Road",
        "area": "Borivali",
        "city": "Mumbai",
        "status": "Open",
        "defect_count": 0,
        "detections": []
    })

    # Total records returned by default
    res_all = test_app_client.get("/api/inspections")
    assert res_all.status_code == 200
    data_all = res_all.get_json()
    assert data_all["count"] == 2

    # Map query returns only records with coordinates
    res_map = test_app_client.get("/api/inspections?has_coords=true")
    assert res_map.status_code == 200
    data_map = res_map.get_json()
    assert data_map["count"] == 1
    assert data_map["inspections"][0]["image_name"] == "map_pin1.jpg"
    assert abs(data_map["inspections"][0]["latitude"] - 19.1136) < 1e-4
    assert abs(data_map["inspections"][0]["longitude"] - 72.8697) < 1e-4


# -----------------------------------------------------------------------------
# 3. Category, Status, and Search Filtering on Geotagged Records
# -----------------------------------------------------------------------------

def test_api_map_filtering(test_app_client):
    """Tests combined category, workflow status, and keyword filtering."""
    # 1. Pothole in Pune, Open
    test_app_client.post("/api/inspections", json={
        "image_name": "pune_pothole.jpg",
        "road_name": "FC Road",
        "area": "Shivajinagar",
        "city": "Pune",
        "latitude": 18.5314,
        "longitude": 73.8446,
        "status": "Open",
        "defect_count": 3,
        "detections": [{
            "distress_category": "Pothole",
            "class_name": "D40",
            "confidence": 0.88,
            "bbox": {"x1": 15, "y1": 25, "x2": 120, "y2": 140, "width": 105, "height": 115}
        }]
    })

    # 2. Longitudinal Crack in Pune, Resolved
    test_app_client.post("/api/inspections", json={
        "image_name": "pune_crack.jpg",
        "road_name": "JM Road",
        "area": "Deccan",
        "city": "Pune",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "status": "Resolved",
        "defect_count": 1,
        "detections": [{
            "distress_category": "Longitudinal Crack",
            "class_name": "D00",
            "confidence": 0.65,
            "bbox": {"x1": 5, "y1": 10, "x2": 50, "y2": 100, "width": 45, "height": 90}
        }]
    })

    # 3. Sound surface (0 defects) in Chennai, Open
    test_app_client.post("/api/inspections", json={
        "image_name": "chennai_sound.jpg",
        "road_name": "Anna Salai",
        "area": "Guindy",
        "city": "Chennai",
        "latitude": 13.0067,
        "longitude": 80.2022,
        "status": "Open",
        "defect_count": 0,
        "detections": []
    })

    # Filter by category: Pothole
    res_pot = test_app_client.get("/api/inspections?has_coords=true&category=Pothole")
    assert res_pot.status_code == 200
    data_pot = res_pot.get_json()
    assert data_pot["count"] == 1
    assert data_pot["inspections"][0]["road_name"] == "FC Road"

    # Filter by category: Sound (0 defects)
    res_sound = test_app_client.get("/api/inspections?has_coords=true&category=Sound")
    assert res_sound.status_code == 200
    data_sound = res_sound.get_json()
    assert data_sound["count"] == 1
    assert data_sound["inspections"][0]["city"] == "Chennai"

    # Filter by status: Resolved
    res_res = test_app_client.get("/api/inspections?has_coords=true&status=Resolved")
    assert res_res.status_code == 200
    data_res = res_res.get_json()
    assert data_res["count"] == 1
    assert data_res["inspections"][0]["road_name"] == "JM Road"

    # Filter by keyword: "Shivajinagar"
    res_kw = test_app_client.get("/api/inspections?has_coords=true&q=Shivajinagar")
    assert res_kw.status_code == 200
    data_kw = res_kw.get_json()
    assert data_kw["count"] == 1
    assert data_kw["inspections"][0]["area"] == "Shivajinagar"

    # Keyword matching city "Pune"
    res_city = test_app_client.get("/api/inspections?has_coords=true&q=Pune")
    assert res_city.status_code == 200
    data_city = res_city.get_json()
    assert data_city["count"] == 2


# -----------------------------------------------------------------------------
# 4. Empty Datasets & Boundary Coordinates
# -----------------------------------------------------------------------------

def test_empty_dataset_map_query(test_app_client):
    """Verifies that querying an empty database for map coordinates does not crash."""
    res = test_app_client.get("/api/inspections?has_coords=true")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["count"] == 0
    assert data["inspections"] == []


def test_boundary_coordinates(test_app_client):
    """Verifies that extreme valid boundary coordinates (-90, 90, -180, 180) are accepted."""
    # North Pole & Date Line East
    res_np = test_app_client.post("/api/inspections", json={
        "image_name": "north_pole.jpg",
        "road_name": "Polar Track",
        "latitude": 90.0,
        "longitude": 180.0,
        "status": "Open",
    })
    assert res_np.status_code == 201

    # South Pole & Date Line West
    res_sp = test_app_client.post("/api/inspections", json={
        "image_name": "south_pole.jpg",
        "road_name": "Amundsen Base",
        "latitude": -90.0,
        "longitude": -180.0,
        "status": "Open",
    })
    assert res_sp.status_code == 201

    # Equator & Prime Meridian
    res_eq = test_app_client.post("/api/inspections", json={
        "image_name": "equator_meridian.jpg",
        "road_name": "Null Island Highway",
        "latitude": 0.0,
        "longitude": 0.0,
        "status": "Open",
    })
    assert res_eq.status_code == 201

    # Fetch them back
    res = test_app_client.get("/api/inspections?has_coords=true")
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 3


def test_invalid_coordinates_rejected_cleanly(test_app_client):
    """Verifies out-of-range coordinates return HTTP 400 without crashing."""
    res_bad_lat = test_app_client.post("/api/inspections", json={
        "image_name": "bad_lat.jpg",
        "latitude": 90.0001,
        "longitude": 75.0,
        "status": "Open",
    })
    assert res_bad_lat.status_code == 400
    assert res_bad_lat.get_json()["error_code"] == "INVALID_COORDINATES"

    res_bad_lon = test_app_client.post("/api/inspections", json={
        "image_name": "bad_lon.jpg",
        "latitude": 20.0,
        "longitude": -180.0001,
        "status": "Open",
    })
    assert res_bad_lon.status_code == 400
    assert res_bad_lon.get_json()["error_code"] == "INVALID_COORDINATES"
