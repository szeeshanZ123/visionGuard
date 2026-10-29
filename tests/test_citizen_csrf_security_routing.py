"""
Comprehensive security, CSRF enforcement, citizen access control, and navigation tests
for VisionGuard AI.
"""

import io
import os
import json
import secrets
import pytest
from app.server import create_app
from database.auth import create_user, ROLE_ADMIN, ROLE_CITIZEN, ROLE_INSPECTOR
from database.db import init_db, get_db_connection, save_inspection


@pytest.fixture
def auth_security_app(tmp_path):
    """Configures test app with auth and CSRF enforcement active."""
    test_db = str(tmp_path / "security_test.db")
    init_db(test_db)

    # Seed users
    admin = create_user("admin_user", "AdminPass1234!", ROLE_ADMIN, email="admin@vg.test", db_path=test_db)
    citizen_alice = create_user("citizen_alice", "AlicePass1234!", ROLE_CITIZEN, email="alice@vg.test", db_path=test_db)
    citizen_bob = create_user("citizen_bob", "BobPass1234!", ROLE_CITIZEN, email="bob@vg.test", db_path=test_db)

    # Seed an inspection record created by Alice
    rec = save_inspection({
        "image_name": "alice_crack.jpg",
        "inspection_type": "road",
        "road_name": "Marine Drive",
        "area": "South Mumbai",
        "city": "Mumbai",
        "latitude": 18.9438,
        "longitude": 72.8232,
        "defect_count": 1,
        "detections": [{"class_name": "D00", "confidence": 0.88}],
        "status": "Open",
        "created_by_user_id": citizen_alice["id"],
        "created_by_username": "citizen_alice",
        "notes": "Confidential private citizen note near my building entrance",
    }, db_path=test_db)
    alice_record_id = rec["id"]

    # Assign it and add instructions
    conn = get_db_connection(test_db)
    cur = conn.cursor()
    cur.execute("""
        UPDATE defect_inspections
        SET assigned_to_user_id = ?, assigned_to_username = ?, assignment_instructions = ?
        WHERE id = ?;
    """, (admin["id"], "admin_user", "Dispatch inspection crew #3", alice_record_id))
    conn.commit()
    conn.close()

    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db,
        "AUTH_ENABLED": True,
        "ENFORCE_CSRF": True,
        "SECRET_KEY": "a" * 32,
    })

    return {
        "app": app,
        "test_db": test_db,
        "admin": admin,
        "alice": citizen_alice,
        "bob": citizen_bob,
        "alice_record_id": alice_record_id,
    }


def login_client(client, username, password):
    """Logs in and retrieves session cookies + csrf_token."""
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.get_json()}"
    data = res.get_json()
    return data.get("csrf_token")


# =========================================================================
# 1. Citizen Access Control Tests
# =========================================================================

def test_citizen_cannot_access_admin_only_apis(auth_security_app):
    """Citizen must be forbidden from accessing admin/inspector-only endpoints."""
    app = auth_security_app["app"]
    with app.test_client() as client:
        csrf_tok = login_client(client, "citizen_bob", "BobPass1234!")
        headers = {"X-CSRF-Token": csrf_tok}

        # 1. Dashboard stats
        res = client.get("/api/dashboard/stats")
        assert res.status_code == 403
        assert res.get_json()["error_code"] == "FORBIDDEN"

        # 2. User management
        res = client.get("/api/users")
        assert res.status_code == 403

        # 3. Staff listing
        res = client.get("/api/maintenance/staff")
        assert res.status_code == 403

        # 4. Reports fleet CSV export
        res = client.get("/api/reports/export/csv")
        assert res.status_code == 403

        # 5. Reports fleet PDF export
        res = client.get("/api/reports/export/pdf")
        assert res.status_code == 403

        # 6. Operations dashboard page (/app) redirects away from internal telemetry
        res = client.get("/app")
        assert res.status_code in [302, 303, 307]
        assert "/report?restricted=1" in res.headers.get("Location", "")


def test_citizen_cannot_read_another_citizens_private_reports(auth_security_app):
    """Citizen Bob cannot read Citizen Alice's private inspection report by ID."""
    app = auth_security_app["app"]
    alice_id = auth_security_app["alice_record_id"]

    with app.test_client() as client:
        login_client(client, "citizen_bob", "BobPass1234!")

        # 1. Direct GET by ID
        res = client.get(f"/api/inspections/{alice_id}")
        assert res.status_code == 403
        data = res.get_json()
        assert data["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # 2. Direct Image GET
        res = client.get(f"/api/inspections/{alice_id}/image/original")
        assert res.status_code == 403
        assert res.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # 3. Activity log GET
        res = client.get(f"/api/inspections/{alice_id}/activity")
        assert res.status_code == 403
        assert res.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"


def test_citizen_inspection_list_cannot_leak_other_records_via_query_params(auth_security_app):
    """Citizen querying /api/inspections cannot see Alice's record by tampering with URL params."""
    app = auth_security_app["app"]
    alice_user_id = auth_security_app["alice"]["id"]

    with app.test_client() as client:
        login_client(client, "citizen_bob", "BobPass1234!")

        # Attempt to query all records or Alice's specific user ID
        res = client.get(f"/api/inspections?created_by_user_id={alice_user_id}")
        assert res.status_code == 200
        records = res.get_json()["inspections"]
        # Bob must see ZERO records (not Alice's)
        assert len(records) == 0

        # Attempt generic /api/inspections (should default to Bob's reports)
        res = client.get("/api/inspections")
        assert res.status_code == 200
        records = res.get_json()["inspections"]
        assert len(records) == 0


def test_public_map_data_sanitizes_citizen_pii_and_internal_dispatch(auth_security_app):
    """When a citizen views civic geotagged map pins, private citizen notes and staff IDs are stripped."""
    app = auth_security_app["app"]

    with app.test_client() as client:
        login_client(client, "citizen_bob", "BobPass1234!")

        # Bob explores civic map
        res = client.get("/api/inspections?has_coords=true&all_civic=true")
        assert res.status_code == 200
        records = res.get_json()["inspections"]
        assert len(records) >= 1

        alice_pin = records[0]
        # Coordinates and public road location are preserved
        assert alice_pin["latitude"] == 18.9438
        assert alice_pin["road_name"] == "Marine Drive"

        # PII and internal dispatch instructions are strictly stripped
        assert alice_pin["created_by_user_id"] is None
        assert alice_pin["created_by_username"] == "Citizen Report"
        assert alice_pin["assigned_to_user_id"] is None
        assert alice_pin["assignment_instructions"] == ""
        assert alice_pin["notes"] == ""  # Confidential private note hidden


def test_authorized_admin_access_continues_working(auth_security_app):
    """Admin user retains full management visibility into telemetry and all records."""
    app = auth_security_app["app"]
    alice_id = auth_security_app["alice_record_id"]

    with app.test_client() as client:
        csrf_tok = login_client(client, "admin_user", "AdminPass1234!")

        # 1. Dashboard stats accessible
        res = client.get("/api/dashboard/stats")
        assert res.status_code == 200
        assert "stats" in res.get_json()

        # 2. View any inspection detail including dispatch instructions
        res = client.get(f"/api/inspections/{alice_id}")
        assert res.status_code == 200
        rec = res.get_json()["inspection"]
        assert rec["created_by_username"] == "citizen_alice"
        assert "Dispatch inspection crew" in rec["assignment_instructions"]

        # 3. Access operations dashboard
        res = client.get("/app")
        assert res.status_code == 200


# =========================================================================
# 2. CSRF Enforcement Tests
# =========================================================================

def test_csrf_missing_or_invalid_token_is_rejected(auth_security_app):
    """Mutating state-changing requests without valid CSRF token must return HTTP 403."""
    app = auth_security_app["app"]

    with app.test_client() as client:
        login_client(client, "citizen_alice", "AlicePass1234!")

        dummy_img = (io.BytesIO(b"fake_jpeg_content"), "test.jpg")

        # 1. Missing CSRF token
        res = client.post("/api/inspect", data={"image": dummy_img, "domain": "road"})
        assert res.status_code == 403
        data = res.get_json()
        assert data["error_code"] == "CSRF_TOKEN_INVALID"
        assert "CSRF token" in data["message"]

        # 2. Invalid CSRF token
        dummy_img = (io.BytesIO(b"fake_jpeg_content"), "test.jpg")
        res = client.post(
            "/api/inspect",
            data={"image": dummy_img, "domain": "road", "csrf_token": "invalid_token_12345"},
            headers={"X-CSRF-Token": "invalid_token_12345"}
        )
        assert res.status_code == 403
        assert res.get_json()["error_code"] == "CSRF_TOKEN_INVALID"


def test_csrf_valid_token_succeeds(auth_security_app):
    """Mutating request with genuine CSRF token passes the security gate."""
    app = auth_security_app["app"]

    with app.test_client() as client:
        csrf_tok = login_client(client, "citizen_alice", "AlicePass1234!")
        assert csrf_tok and len(csrf_tok) == 64

        # Read genuine benchmark test image
        with open("data/evaluation_benchmark/images/benchmark_01_d00_longitudinal_center.jpg", "rb") as f:
            img_bytes = f.read()

        # Pass CSRF token in both header and form data
        data = {
            "image": (io.BytesIO(img_bytes), "test_road.jpg"),
            "domain": "road",
            "csrf_token": csrf_tok
        }
        res = client.post(
            "/api/inspect",
            data=data,
            headers={"X-CSRF-Token": csrf_tok},
            content_type="multipart/form-data"
        )
        assert res.status_code == 200
        res_data = res.get_json()
        assert res_data["status"] == "success"
        assert "detections" in res_data
        assert "annotated_image" in res_data


def test_building_inspection_with_csrf_succeeds(auth_security_app):
    """Building inspection mode operates correctly with valid CSRF token."""
    app = auth_security_app["app"]

    with app.test_client() as client:
        csrf_tok = login_client(client, "citizen_alice", "AlicePass1234!")

        with open("data/test_representative_home_defects/01_wall_crack_zenodo_022.jpg", "rb") as f:
            img_bytes = f.read()

        data = {
            "image": (io.BytesIO(img_bytes), "wall_crack.jpg"),
            "domain": "home",
            "csrf_token": csrf_tok
        }
        res = client.post(
            "/api/inspect",
            data=data,
            headers={"X-CSRF-Token": csrf_tok},
            content_type="multipart/form-data"
        )
        assert res.status_code == 200
        res_data = res.get_json()
        assert res_data["status"] == "success"
        assert res_data["domain"] == "home"


# =========================================================================
# 3. Frontend CSRF Meta & Routing Tests
# =========================================================================

def test_all_frontend_pages_contain_csrf_meta_tag(auth_security_app):
    """Every rendered frontend page must inject the meta[name='csrf-token'] element."""
    app = auth_security_app["app"]
    with app.test_client() as client:
        pages = ["/", "/landing", "/login", "/create_home", "/map", "/report"]
        for p in pages:
            res = client.get(p)
            assert res.status_code == 200, f"Page {p} returned {res.status_code}"
            html = res.data.decode("utf-8")
            assert '<meta name="csrf-token"' in html, f"Page {p} is missing meta[name='csrf-token'] tag"


def test_login_page_renders_clean_dom_without_raw_html_escape(auth_security_app):
    """login.html must not contain literal unescaped HTML strings in raw text handlers."""
    app = auth_security_app["app"]
    with app.test_client() as client:
        res = client.get("/login")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        # Ensure the old raw string concatenation was removed
        assert "Signed in as ' + data.user.username" not in html
        assert "replaceChildren" in html
        assert "getCsrfToken" in html
