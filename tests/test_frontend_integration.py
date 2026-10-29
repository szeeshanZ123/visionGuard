"""
Comprehensive integration tests for VisionGuard AI frontend pages and backend routing:
- landing.html (/ and /landing)
- login.html (/login)
- create_home.html (/create_home, /create, /inspect)
- map.html (/map)
- report.html (/report, /reports, /records)
- classic app (/app, /classic)
- API auth integration (login, register, status)
- Defect inspection and persistence flow
- Asset integrity and model protection
"""

import hashlib
import io
import json
import os
import pytest
import uuid
from PIL import Image

from app.server import create_app
from database.db import init_db

EXPECTED_BEST_PT_SHA256 = "01c27f61ee370392a8fa1b66f1c0a22fca4e93b3d0615ef7b932f91da6818f14"
EXPECTED_HOME_BEST_PT_SHA256 = "71c64ac75204d6d791bc107df7f7afa6115a2da9bfa3491881e8d3e753a1ed70"


@pytest.fixture
def app_instance(tmp_path):
    test_db = str(tmp_path / "test_frontend_integration.db")
    init_db(test_db)
    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db,
        "AUTH_ENABLED": False,  # Permissive role testing by default
        "ENFORCE_CSRF": False,
    })
    return app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def test_model_checkpoints_integrity():
    """Verify that production model weights are completely untouched."""
    with open("ai/models/best.pt", "rb") as f:
        best_hash = hashlib.sha256(f.read()).hexdigest()
    assert best_hash == EXPECTED_BEST_PT_SHA256, "best.pt SHA-256 hash has been modified!"

    with open("ai/models/home_best.pt", "rb") as f:
        home_hash = hashlib.sha256(f.read()).hexdigest()
    assert home_hash == EXPECTED_HOME_BEST_PT_SHA256, "home_best.pt SHA-256 hash has been modified!"


def test_landing_page_routes(client):
    """Verify landing page serves correctly with interactive navigation links."""
    # Test GET /landing
    res_landing = client.get("/landing")
    assert res_landing.status_code == 200
    html = res_landing.data.decode("utf-8")
    assert "VisionGuard" in html
    assert "/create_home" in html
    assert "/map" in html
    assert "/report" in html
    assert "/login" in html

    # Test GET /?frontend=1
    res_root = client.get("/?frontend=1")
    assert res_root.status_code == 200
    assert "VisionGuard" in res_root.data.decode("utf-8")


def test_login_page_route(client):
    """Verify login page serves correctly with sign in and registration panels."""
    res = client.get("/login")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Sign In" in html
    assert "Create Citizen Account" in html
    assert "/api/auth/login" in html or "handleSignInSubmit" in html
    assert "/api/auth/register" in html or "handleRegisterSubmit" in html
    assert "href=\"/\"" in html or "href='/'" in html


def test_create_home_inspection_studio_route(client):
    """Verify inspection studio serves correctly with dual model workflows and GPS inputs."""
    for path in ["/create_home", "/create", "/inspect"]:
        res = client.get(path)
        assert res.status_code == 200, f"Route {path} failed with {res.status_code}"
        html = res.data.decode("utf-8")
        assert "Target Inspection Workflow" in html or "Defect Ingestion" in html
        assert "Road Surface Distress" in html
        assert "Home &amp; Building Defect" in html or "Home & Building Defect" in html
        assert "loc-lat" in html
        assert "loc-lng" in html
        assert "btn-run-inspection" in html


def test_map_page_route(client):
    """Verify geospatial map page serves correctly with Leaflet and inspection pins."""
    res = client.get("/map")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Geospatial Defect Map" in html
    assert "defect-map" in html
    assert "leaflet" in html.lower()
    assert "/api/inspections" in html


def test_report_page_route(client):
    """Verify inspection records and work orders page serves correctly with table and export."""
    for path in ["/report", "/reports", "/records"]:
        res = client.get(path)
        assert res.status_code == 200, f"Route {path} failed with {res.status_code}"
        html = res.data.decode("utf-8")
        assert "Inspection Records" in html
        assert "Export CSV" in html
        assert "tableBody" in html
        assert "domainSelect" in html
        assert "statusSelect" in html


def test_classic_app_route(client):
    """Verify legacy SPA dashboard remains accessible."""
    for path in ["/app", "/classic"]:
        res = client.get(path)
        assert res.status_code == 200, f"Route {path} failed with {res.status_code}"
        html = res.data.decode("utf-8")
        assert "technicalAiControls" in html or "inspectBtn" in html or "VisionGuard" in html


def test_placeholder_static_asset(client):
    """Verify fallback image asset exists and returns HTTP 200."""
    res = client.get("/static/img/placeholder.png")
    assert res.status_code == 200
    assert "image" in res.content_type


def test_auth_status_and_flow(client):
    """Verify API auth endpoints communicate correctly with frontend."""
    # Check status initially
    res_status = client.get("/api/auth/status")
    assert res_status.status_code == 200
    data = res_status.get_json()
    assert "authenticated" in data
    assert "csrf_token" in data

    unique_user = f"citizen_test_{uuid.uuid4().hex[:6]}"
    # Register a new citizen user
    res_reg = client.post("/api/auth/register", json={
        "username": unique_user,
        "password": "Password123!",
        "email": f"{unique_user}@example.com"
    })
    assert res_reg.status_code == 201
    reg_data = res_reg.get_json()
    assert reg_data["status"] == "success"
    assert reg_data["user"]["username"] == unique_user

    # Status should now report authenticated
    res_status2 = client.get("/api/auth/status")
    assert res_status2.get_json()["authenticated"] is True
    assert res_status2.get_json()["user"]["username"] == unique_user


def test_inspection_and_persistence_flow(client):
    """Verify defect inspection API processes an image and can be persisted."""
    # Create a small valid JPEG in memory
    img = Image.new("RGB", (640, 640), color=(128, 128, 128))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_byte_arr.seek(0)

    # 1. POST /api/inspect
    res_inspect = client.post(
        "/api/inspect",
        data={
            "image": (img_byte_arr, "test_inspection.jpg"),
            "domain": "road",
            "inspection_mode": "standard",
            "confidence_threshold": "0.25",
        },
        content_type="multipart/form-data"
    )
    assert res_inspect.status_code == 200
    insp_data = res_inspect.get_json()
    assert insp_data["status"] == "success"
    assert "defect_count" in insp_data
    assert "annotated_image" in insp_data
    assert "timings" in insp_data

    # 2. POST /api/inspections to save
    res_save = client.post(
        "/api/inspections",
        json={
            "image_name": "test_inspection.jpg",
            "domain": "road",
            "road_name": "Marine Drive",
            "area": "South Ward",
            "city": "Mumbai",
            "latitude": 18.9438,
            "longitude": 72.8234,
            "defect_count": insp_data["defect_count"],
            "detections": insp_data["detections"],
            "status": "Open",
        }
    )
    assert res_save.status_code in [200, 201]

    # 3. GET /api/inspections to verify listed
    res_list = client.get("/api/inspections")
    assert res_list.status_code == 200
    list_data = res_list.get_json()
    assert list_data["count"] >= 1
    found = any(r.get("road_name") == "Marine Drive" for r in list_data["inspections"])
    assert found, "Saved inspection record not found in /api/inspections list!"
