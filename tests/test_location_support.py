"""
Unit and integration tests for Inspection Location Support (Phase 4.1).

Validates:
- Saving inspection records with valid GPS coordinates.
- Saving inspection records without coordinates (allowed/optional).
- Rejecting out-of-range latitude (> 90, < -90) and longitude (> 180, < -180).
- Rejecting non-numeric coordinate strings.
- Location persistence across database reload.
- Returning location fields from GET /api/inspections and GET /api/inspections/<id>.
- Database migration idempotency preserving existing records and schema.
- Text search filtering matching area and city fields.
- Updating location metadata via PATCH.
"""

import sqlite3
import pytest
from app.server import create_app
from ai.detection.detector import DefectDetectionService
from database.db import (
    init_db,
    save_inspection,
    get_inspection_by_id,
    get_inspections,
    get_db_connection,
    update_inspection,
)


@pytest.fixture
def test_app_client(tmp_path):
    """Test client configured with a temporary database."""
    test_db = str(tmp_path / "location_test.db")
    detector = DefectDetectionService(model_path="ai/models/best.pt")
    app = create_app(detector=detector, test_config={"TESTING": True, "DATABASE_PATH": test_db})
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary SQLite database path for direct DB tests."""
    db_file = str(tmp_path / "direct_location_test.db")
    init_db(db_file)
    return db_file


# -----------------------------------------------------------------------------
# Direct Database Layer Tests
# -----------------------------------------------------------------------------

def test_save_inspection_with_valid_coordinates(temp_db_path):
    """Verifies that an inspection saves and retrieves valid coordinates."""
    data = {
        "image_name": "mumbai_expressway.jpg",
        "road_name": "Western Express Highway",
        "area": "Bandra East",
        "city": "Mumbai",
        "latitude": 19.0596,
        "longitude": 72.8441,
        "location_notes": "Near flyover south expansion joint",
        "status": "Open",
        "detections": [
            {
                "distress_category": "Longitudinal Crack",
                "class_name": "D00",
                "confidence": 0.85,
                "bbox": {"x1": 10, "y1": 20, "x2": 100, "y2": 200, "width": 90, "height": 180}
            }
        ]
    }
    saved = save_inspection(data, db_path=temp_db_path)
    assert saved["id"] is not None
    assert saved["road_name"] == "Western Express Highway"
    assert saved["area"] == "Bandra East"
    assert saved["city"] == "Mumbai"
    assert abs(saved["latitude"] - 19.0596) < 1e-4
    assert abs(saved["longitude"] - 72.8441) < 1e-4
    assert saved["location_notes"] == "Near flyover south expansion joint"


def test_save_inspection_without_coordinates(temp_db_path):
    """Verifies that coordinates can remain empty when unknown."""
    data = {
        "image_name": "unknown_location_road.jpg",
        "road_name": "Rural Link Road",
        "area": "",
        "city": "",
        "latitude": None,
        "longitude": None,
        "status": "Open",
    }
    saved = save_inspection(data, db_path=temp_db_path)
    assert saved["id"] is not None
    assert saved["latitude"] is None
    assert saved["longitude"] is None
    assert saved["road_name"] == "Rural Link Road"


def test_location_persistence_across_database_reload(temp_db_path):
    """Verifies that location fields persist accurately across reconnection."""
    record = save_inspection({
        "image_name": "delhi_ring_road.jpg",
        "road_name": "Outer Ring Road",
        "area": "Hauz Khas",
        "city": "New Delhi",
        "latitude": 28.5494,
        "longitude": 77.2001,
        "location_notes": "Lane 2 rutting and longitudinal distress",
    }, db_path=temp_db_path)

    record_id = record["id"]

    # Read from brand new connection
    fetched = get_inspection_by_id(record_id, db_path=temp_db_path)
    assert fetched is not None
    assert fetched["road_name"] == "Outer Ring Road"
    assert fetched["area"] == "Hauz Khas"
    assert fetched["city"] == "New Delhi"
    assert abs(fetched["latitude"] - 28.5494) < 1e-4
    assert abs(fetched["longitude"] - 77.2001) < 1e-4
    assert fetched["location_notes"] == "Lane 2 rutting and longitudinal distress"


def test_migration_idempotency_preserves_existing_data(temp_db_path):
    """Verifies that init_db() is idempotent and safe to run repeatedly."""
    # Insert record
    saved = save_inspection({
        "image_name": "test_migration.jpg",
        "road_name": "MG Road",
        "area": "Indiranagar",
        "city": "Bengaluru",
        "latitude": 12.9716,
        "longitude": 77.5946,
    }, db_path=temp_db_path)

    # Run init_db multiple times
    init_db(temp_db_path)
    init_db(temp_db_path)

    # Verify data is completely preserved
    re_fetched = get_inspection_by_id(saved["id"], db_path=temp_db_path)
    assert re_fetched is not None
    assert re_fetched["road_name"] == "MG Road"
    assert re_fetched["area"] == "Indiranagar"
    assert re_fetched["city"] == "Bengaluru"
    assert abs(re_fetched["latitude"] - 12.9716) < 1e-4
    assert abs(re_fetched["longitude"] - 77.5946) < 1e-4


# -----------------------------------------------------------------------------
# REST API Endpoint Validation Tests
# -----------------------------------------------------------------------------

def test_api_save_with_valid_coordinates(test_app_client):
    """Verifies POST /api/inspections accepts valid coordinates and location fields."""
    payload = {
        "image_name": "nh48_pune.jpg",
        "road_name": "NH 48 Bypass",
        "area": "Kothrud",
        "city": "Pune",
        "latitude": 18.5074,
        "longitude": 73.8077,
        "location_notes": "Shoulder crack propagation near km 22",
        "status": "In Progress",
    }
    res = test_app_client.post("/api/inspections", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "success"
    insp = data["inspection"]
    assert insp["road_name"] == "NH 48 Bypass"
    assert insp["area"] == "Kothrud"
    assert insp["city"] == "Pune"
    assert abs(insp["latitude"] - 18.5074) < 1e-4
    assert abs(insp["longitude"] - 73.8077) < 1e-4


def test_api_save_without_coordinates(test_app_client):
    """Verifies POST /api/inspections allows empty coordinates when unknown."""
    payload = {
        "image_name": "no_gps_image.jpg",
        "road_name": "Station Approach Road",
        "latitude": None,
        "longitude": "",
    }
    res = test_app_client.post("/api/inspections", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    insp = data["inspection"]
    assert insp["latitude"] is None
    assert insp["longitude"] is None


def test_api_rejects_out_of_range_latitude(test_app_client):
    """Verifies POST /api/inspections rejects latitude > 90 or < -90."""
    # Latitude > 90
    res1 = test_app_client.post("/api/inspections", json={
        "image_name": "bad_lat_pos.jpg",
        "latitude": 95.0,
        "longitude": 72.8,
    })
    assert res1.status_code == 400
    assert res1.get_json()["error_code"] == "INVALID_COORDINATES"
    assert "Latitude 95.0 is out of bounds" in res1.get_json()["message"]

    # Latitude < -90
    res2 = test_app_client.post("/api/inspections", json={
        "image_name": "bad_lat_neg.jpg",
        "latitude": -91.5,
        "longitude": 72.8,
    })
    assert res2.status_code == 400
    assert res2.get_json()["error_code"] == "INVALID_COORDINATES"


def test_api_rejects_out_of_range_longitude(test_app_client):
    """Verifies POST /api/inspections rejects longitude > 180 or < -180."""
    # Longitude > 180
    res1 = test_app_client.post("/api/inspections", json={
        "image_name": "bad_lon_pos.jpg",
        "latitude": 19.0,
        "longitude": 185.0,
    })
    assert res1.status_code == 400
    assert res1.get_json()["error_code"] == "INVALID_COORDINATES"
    assert "Longitude 185.0 is out of bounds" in res1.get_json()["message"]

    # Longitude < -180
    res2 = test_app_client.post("/api/inspections", json={
        "image_name": "bad_lon_neg.jpg",
        "latitude": 19.0,
        "longitude": -185.0,
    })
    assert res2.status_code == 400
    assert res2.get_json()["error_code"] == "INVALID_COORDINATES"


def test_api_rejects_non_numeric_coordinates(test_app_client):
    """Verifies POST /api/inspections rejects string coordinates that cannot be parsed."""
    res = test_app_client.post("/api/inspections", json={
        "image_name": "bad_coords_str.jpg",
        "latitude": "north_pole",
        "longitude": 72.0,
    })
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "INVALID_COORDINATES"


def test_api_rejects_oversized_area_and_city(test_app_client):
    """Verifies area and city length limits."""
    res_area = test_app_client.post("/api/inspections", json={
        "image_name": "oversized.jpg",
        "area": "A" * 101,
    })
    assert res_area.status_code == 400
    assert res_area.get_json()["error_code"] == "AREA_TOO_LONG"

    res_city = test_app_client.post("/api/inspections", json={
        "image_name": "oversized.jpg",
        "city": "C" * 101,
    })
    assert res_city.status_code == 400
    assert res_city.get_json()["error_code"] == "CITY_TOO_LONG"


def test_api_returns_location_fields_in_list_and_detail(test_app_client):
    """Verifies GET /api/inspections and GET /api/inspections/<id> return all location metadata."""
    save_res = test_app_client.post("/api/inspections", json={
        "image_name": "marine_drive_distress.jpg",
        "road_name": "Netaji Subhash Chandra Bose Road",
        "area": "Marine Lines",
        "city": "Mumbai",
        "latitude": 18.9438,
        "longitude": 72.8232,
        "location_notes": "Promenade seawall adjacent lane",
    })
    assert save_res.status_code == 201
    rec_id = save_res.get_json()["inspection"]["id"]

    # 1. Verify GET /api/inspections list
    list_res = test_app_client.get("/api/inspections")
    assert list_res.status_code == 200
    items = list_res.get_json()["inspections"]
    assert len(items) == 1
    assert items[0]["road_name"] == "Netaji Subhash Chandra Bose Road"
    assert items[0]["area"] == "Marine Lines"
    assert items[0]["city"] == "Mumbai"
    assert abs(items[0]["latitude"] - 18.9438) < 1e-4
    assert abs(items[0]["longitude"] - 72.8232) < 1e-4

    # 2. Verify GET /api/inspections/<id>
    detail_res = test_app_client.get(f"/api/inspections/{rec_id}")
    assert detail_res.status_code == 200
    detail = detail_res.get_json()["inspection"]
    assert detail["road_name"] == "Netaji Subhash Chandra Bose Road"
    assert detail["area"] == "Marine Lines"
    assert detail["city"] == "Mumbai"
    assert abs(detail["latitude"] - 18.9438) < 1e-4
    assert abs(detail["longitude"] - 72.8232) < 1e-4
    assert detail["location_notes"] == "Promenade seawall adjacent lane"


def test_search_filter_matches_area_and_city(test_app_client):
    """Verifies that the search query parameter 'q' filters by area and city."""
    test_app_client.post("/api/inspections", json={
        "image_name": "img1.jpg",
        "road_name": "Linking Road",
        "area": "Khar West",
        "city": "Mumbai",
    })
    test_app_client.post("/api/inspections", json={
        "image_name": "img2.jpg",
        "road_name": "FC Road",
        "area": "Shivajinagar",
        "city": "Pune",
    })

    # Search by area 'Khar'
    res_khar = test_app_client.get("/api/inspections?q=Khar")
    assert res_khar.status_code == 200
    items_khar = res_khar.get_json()["inspections"]
    assert len(items_khar) == 1
    assert items_khar[0]["area"] == "Khar West"

    # Search by city 'Pune'
    res_pune = test_app_client.get("/api/inspections?q=Pune")
    assert res_pune.status_code == 200
    items_pune = res_pune.get_json()["inspections"]
    assert len(items_pune) == 1
    assert items_pune[0]["city"] == "Pune"


def test_update_inspection_location_via_patch(test_app_client):
    """Verifies that PATCH /api/inspections/<id> can update location fields and validates coordinates."""
    save_res = test_app_client.post("/api/inspections", json={
        "image_name": "initial.jpg",
        "road_name": "Original Road",
    })
    rec_id = save_res.get_json()["inspection"]["id"]

    # Valid update
    update_res = test_app_client.patch(f"/api/inspections/{rec_id}", json={
        "road_name": "Updated Road Name",
        "area": "New Area",
        "city": "New City",
        "latitude": 20.0,
        "longitude": 75.0,
    })
    assert update_res.status_code == 200
    updated = update_res.get_json()["inspection"]
    assert updated["road_name"] == "Updated Road Name"
    assert updated["area"] == "New Area"
    assert updated["city"] == "New City"
    assert abs(updated["latitude"] - 20.0) < 1e-4
    assert abs(updated["longitude"] - 75.0) < 1e-4

    # Invalid update: latitude out of range
    invalid_res = test_app_client.patch(f"/api/inspections/{rec_id}", json={
        "latitude": 105.0,
    })
    assert invalid_res.status_code == 400
    assert invalid_res.get_json()["error_code"] == "INVALID_COORDINATES"


# -----------------------------------------------------------------------------
# Phase 2: Citizen GPS & Manual Address Tests
# -----------------------------------------------------------------------------

def test_citizen_location_privacy_and_access_control(test_app_client):
    """
    Verifies that citizen location data remains private:
    - Citizen A creates an inspection with GPS coordinates and address.
    - Citizen B is forbidden from accessing Citizen A's inspection details, images, activities, and complaint drafts (HTTP 403).
    - Citizen A is allowed to view their own inspection details.
    - Staff (Admin / Inspector) can view Citizen A's inspection to perform remediation.
    """
    # 1. Register Citizen A
    reg_a = test_app_client.post("/api/auth/register", json={
        "username": "citizen_location_a",
        "password": "Password123!",
    })
    assert reg_a.status_code == 201

    # 2. Citizen A creates inspection with private location
    save_res = test_app_client.post("/api/inspections", json={
        "image_name": "citizen_pothole.jpg",
        "road_name": "Private Lane 4",
        "area": "Residential Colony",
        "city": "Bengaluru",
        "latitude": 12.9352,
        "longitude": 77.6245,
        "location_notes": "Deep pothole outside house gate",
        "status": "Open",
    })
    assert save_res.status_code == 201
    insp_id = save_res.get_json()["inspection"]["id"]

    # Citizen A can view their own inspection
    detail_res_a = test_app_client.get(f"/api/inspections/{insp_id}")
    assert detail_res_a.status_code == 200
    assert detail_res_a.get_json()["inspection"]["road_name"] == "Private Lane 4"

    # Citizen A can view their complaint draft
    draft_res_a = test_app_client.get(f"/api/inspections/{insp_id}/complaint-draft")
    assert draft_res_a.status_code == 200

    # 3. Register Citizen B and authenticate
    test_app_client.post("/api/auth/logout")
    reg_b = test_app_client.post("/api/auth/register", json={
        "username": "citizen_location_b",
        "password": "Password123!",
    })
    assert reg_b.status_code == 201

    # Citizen B cannot access Citizen A's inspection details
    detail_res_b = test_app_client.get(f"/api/inspections/{insp_id}")
    assert detail_res_b.status_code == 403
    assert detail_res_b.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Citizen B cannot access Citizen A's complaint draft
    draft_res_b = test_app_client.get(f"/api/inspections/{insp_id}/complaint-draft")
    assert draft_res_b.status_code == 403
    assert draft_res_b.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Citizen B cannot access Citizen A's activity log
    act_res_b = test_app_client.get(f"/api/inspections/{insp_id}/activity")
    assert act_res_b.status_code == 403
    assert act_res_b.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Citizen B cannot access Citizen A's inspection images
    img_res_b = test_app_client.get(f"/api/inspections/{insp_id}/image/original")
    assert img_res_b.status_code == 403
    assert img_res_b.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # 4. Authorized staff (Admin) can view Citizen A's report for municipal dispatch
    test_app_client.post("/api/auth/logout")
    # Bootstrap or login as admin
    test_app_client.post("/api/auth/setup-admin", json={
        "username": "admin_loc_supervisor",
        "password": "Password123!",
    })
    admin_detail = test_app_client.get(f"/api/inspections/{insp_id}")
    assert admin_detail.status_code == 200
    assert admin_detail.get_json()["inspection"]["road_name"] == "Private Lane 4"
    assert abs(admin_detail.get_json()["inspection"]["latitude"] - 12.9352) < 1e-4


def test_location_fallback_never_invents_coordinates_or_addresses(test_app_client):
    """
    Verifies Phase 2 Requirement 8:
    - Never invent coordinates when only manual address is provided.
    - Never invent address strings when only GPS coordinates are provided.
    """
    # 1. Manual address only (no GPS)
    res_addr_only = test_app_client.post("/api/inspections", json={
        "image_name": "manual_addr_only.jpg",
        "road_name": "742 Evergreen Terrace",
        "area": "Springfield Suburbs",
        "city": "Springfield",
        "latitude": None,
        "longitude": None,
    })
    assert res_addr_only.status_code == 201
    insp_addr = res_addr_only.get_json()["inspection"]
    assert insp_addr["road_name"] == "742 Evergreen Terrace"
    assert insp_addr["area"] == "Springfield Suburbs"
    assert insp_addr["city"] == "Springfield"
    assert insp_addr["latitude"] is None
    assert insp_addr["longitude"] is None

    # 2. GPS only (no manual address)
    res_gps_only = test_app_client.post("/api/inspections", json={
        "image_name": "gps_only.jpg",
        "road_name": "",
        "area": "",
        "city": "",
        "latitude": 19.0760,
        "longitude": 72.8777,
    })
    assert res_gps_only.status_code == 201
    insp_gps = res_gps_only.get_json()["inspection"]
    assert abs(insp_gps["latitude"] - 19.0760) < 1e-4
    assert abs(insp_gps["longitude"] - 72.8777) < 1e-4
    assert insp_gps["road_name"] == ""
    assert insp_gps["area"] == ""
    assert insp_gps["city"] == ""


def test_inspection_not_blocked_when_location_omitted(test_app_client):
    """
    Verifies Phase 2 Requirement 8:
    Inspections are never blocked when location is denied or omitted.
    """
    res = test_app_client.post("/api/inspections", json={
        "image_name": "no_location_at_all.jpg",
        "status": "Open",
    })
    assert res.status_code == 201
    insp = res.get_json()["inspection"]
    assert insp["id"] is not None
    assert insp["latitude"] is None
    assert insp["longitude"] is None
    assert insp["road_name"] == ""


def test_home_and_road_domain_location_persistence(test_app_client):
    """
    Verifies that location data persists properly for both road and home problem workflows.
    """
    # 1. Home defect with residential location
    res_home = test_app_client.post("/api/inspections", json={
        "image_name": "living_room_crack.jpg",
        "inspection_type": "home",
        "domain": "home",
        "road_name": "Tower 4, Flat 1201",
        "area": "Living Room South Wall",
        "city": "Noida",
        "latitude": 28.5355,
        "longitude": 77.3910,
        "location_notes": "Hairline crack propagating near ceiling joint",
    })
    assert res_home.status_code == 201
    home_insp = res_home.get_json()["inspection"]
    assert home_insp["inspection_type"] == "home"
    assert home_insp["road_name"] == "Tower 4, Flat 1201"
    assert home_insp["area"] == "Living Room South Wall"
    assert abs(home_insp["latitude"] - 28.5355) < 1e-4

    # 2. Road defect with highway corridor location
    res_road = test_app_client.post("/api/inspections", json={
        "image_name": "highway_pothole.jpg",
        "inspection_type": "road",
        "domain": "road",
        "road_name": "NH 44 Expressway",
        "area": "KM Marker 108",
        "city": "Nagpur",
        "latitude": 21.1458,
        "longitude": 79.0882,
        "location_notes": "Right shoulder pothole with loose aggregate",
    })
    assert res_road.status_code == 201
    road_insp = res_road.get_json()["inspection"]
    assert road_insp["inspection_type"] == "road"
    assert road_insp["road_name"] == "NH 44 Expressway"
    assert abs(road_insp["latitude"] - 21.1458) < 1e-4

