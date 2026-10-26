"""
VisionGuard AI - Phase 1 Citizen-Facing Mode & Authentication Test Suite.

Validates:
1. Citizen self-registration (POST /api/auth/register) with role=ROLE_CITIZEN.
2. Citizen authentication (login, session persistence, invalid credentials, logout).
3. Citizen defect reporting (running inspection, saving inspection, civic complaint drafts).
4. Strict access boundary enforcement (citizens strictly denied admin & maintenance operations).
5. Unauthenticated guest protection on protected APIs.
"""

import io
import os
import pytest
from PIL import Image

from app.server import create_app
from database.db import init_db
from database.auth import (
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    ROLE_MAINTENANCE,
    ROLE_CITIZEN,
    create_user,
    get_user_by_username,
)
from ai.detection.detector import DefectDetectionService


class MockDetector(DefectDetectionService):
    def __init__(self, domain="road"):
        super().__init__(domain=domain)
        self.domain = domain
        self._model = object()
        self.model = object()
        self.is_loaded = True
        self.status_message = "Ready (Mock Detector for Citizen Tests)"
        self.model_path = f"ai/models/{'home_' if domain == 'home' else ''}mock.pt"
        self.model_info = {
            "model_name": "YOLOv8-Mock",
            "checkpoint_path": self.model_path,
            "classes": ["wall_crack"] if domain == "home" else ["D00"],
            "domain": domain,
        }

    def detect(self, image_bgr, conf_threshold=0.25, inspection_mode="standard", raise_if_unloaded=True, **kwargs):
        cls_name = "wall_crack" if self.domain == "home" else "D00"
        return [
            {
                "class_id": 0,
                "class_name": cls_name,
                "confidence": 0.88,
                "bbox": {"x1": 50, "y1": 50, "x2": 200, "y2": 200, "width": 150, "height": 150},
                "coordinates": [50, 50, 200, 200],
                "distress_category": "wall_crack" if self.domain == "home" else "longitudinal_crack",
                "domain": self.domain,
            }
        ]

    def draw_annotations(self, image_bgr, detections):
        return image_bgr.copy()

    def encode_image_to_base64(self, image_bgr):
        return "data:image/jpeg;base64,mockb64"


def create_dummy_png_bytes(width=200, height=200, color="gray"):
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def citizen_test_env(tmp_path):
    test_db = str(tmp_path / "citizen_test.db")
    init_db(test_db)

    detector = MockDetector(domain="road")
    home_detector = MockDetector(domain="home")

    app = create_app(
        detector=detector,
        home_detector=home_detector,
        test_config={
            "DATABASE_PATH": test_db,
            "TESTING": True,
            "AUTH_ENABLED": True,
            "AUTH_ENABLED_EXPLICIT": True,
            "ENFORCE_CSRF": False,  # tested separately
            "SECRET_KEY": "citizen-test-secret-key-32-bytes!!",
        }
    )
    client = app.test_client()
    return client, test_db, app


class TestCitizenRegistration:
    def test_successful_citizen_registration(self, citizen_test_env):
        client, test_db, _ = citizen_test_env

        res = client.post("/api/auth/register", json={
            "username": "jane_citizen",
            "password": "SecurePassword123!",
            "email": "jane@example.com"
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["status"] == "success"
        assert data["user"]["username"] == "jane_citizen"
        assert data["user"]["role"] == ROLE_CITIZEN
        assert data["user"]["role_display"] == "Citizen"
        assert "csrf_token" in data

        # Verify persisted user in DB has role 'citizen'
        db_user = get_user_by_username("jane_citizen", db_path=test_db)
        assert db_user is not None
        assert db_user["role"] == ROLE_CITIZEN
        assert db_user["email"] == "jane@example.com"

        # Verify session is established automatically
        status_res = client.get("/api/auth/status")
        assert status_res.status_code == 200
        status_data = status_res.get_json()
        assert status_data["authenticated"] is True
        assert status_data["user"]["username"] == "jane_citizen"
        assert status_data["user"]["role"] == ROLE_CITIZEN

    def test_registration_validation_rules(self, citizen_test_env):
        client, _, _ = citizen_test_env

        # Missing password
        r1 = client.post("/api/auth/register", json={"username": "valid_user", "password": ""})
        assert r1.status_code == 400
        assert r1.get_json()["error_code"] == "MISSING_CREDENTIALS"

        # Short password (< 8 chars)
        r2 = client.post("/api/auth/register", json={"username": "valid_user", "password": "short"})
        assert r2.status_code == 400
        assert r2.get_json()["error_code"] == "REGISTRATION_FAILED"

        # Invalid username characters
        r3 = client.post("/api/auth/register", json={"username": "bad user!", "password": "Password123!"})
        assert r3.status_code == 400
        assert r3.get_json()["error_code"] == "REGISTRATION_FAILED"

    def test_duplicate_registration_rejected(self, citizen_test_env):
        client, _, _ = citizen_test_env

        r1 = client.post("/api/auth/register", json={"username": "resident_mark", "password": "Password123!"})
        assert r1.status_code == 201

        # Second attempt with same username
        r2 = client.post("/api/auth/register", json={"username": "resident_mark", "password": "AnotherPassword123!"})
        assert r2.status_code == 400
        assert "already in use" in r2.get_json()["message"]


class TestCitizenAuthenticationFlow:
    def test_citizen_login_and_logout(self, citizen_test_env):
        client, test_db, _ = citizen_test_env
        create_user("citizen_alex", "AlexSecret123!", role=ROLE_CITIZEN, db_path=test_db)

        # Login with valid credentials
        login_res = client.post("/api/auth/login", json={
            "username": "citizen_alex",
            "password": "AlexSecret123!"
        })
        assert login_res.status_code == 200
        login_data = login_res.get_json()
        assert login_data["user"]["username"] == "citizen_alex"
        assert login_data["user"]["role"] == ROLE_CITIZEN

        # Verify session persistence via /api/auth/me
        me_res = client.get("/api/auth/me")
        assert me_res.status_code == 200
        assert me_res.get_json()["user"]["username"] == "citizen_alex"

        # Logout
        logout_res = client.post("/api/auth/logout")
        assert logout_res.status_code == 200

        # After logout, /api/auth/me should return 401
        me_after = client.get("/api/auth/me")
        assert me_after.status_code == 401

    def test_citizen_invalid_login_credentials(self, citizen_test_env):
        client, test_db, _ = citizen_test_env
        create_user("citizen_bob", "BobSecret123!", role=ROLE_CITIZEN, db_path=test_db)

        # Wrong password
        r1 = client.post("/api/auth/login", json={"username": "citizen_bob", "password": "WrongPassword!"})
        assert r1.status_code == 401
        assert r1.get_json()["error_code"] == "INVALID_CREDENTIALS"

        # Non-existent user
        r2 = client.post("/api/auth/login", json={"username": "ghost_user", "password": "AnyPassword!"})
        assert r2.status_code == 401
        assert r2.get_json()["error_code"] == "INVALID_CREDENTIALS"


class TestCitizenInspectionAndReportingWorkflow:
    def test_citizen_can_inspect_and_save_home_and_road_problems(self, citizen_test_env):
        client, test_db, _ = citizen_test_env
        create_user("active_citizen", "CitizenPass123!", role=ROLE_CITIZEN, db_path=test_db)

        client.post("/api/auth/login", json={"username": "active_citizen", "password": "CitizenPass123!"})

        # 1. Citizen runs Defect Inspection for Home Problem
        png_data = create_dummy_png_bytes()
        inspect_home_res = client.post(
            "/api/inspect",
            data={
                "image": (io.BytesIO(png_data), "wall_crack_test.png"),
                "domain": "home",
                "confidence_threshold": "0.25",
            },
            content_type="multipart/form-data"
        )
        assert inspect_home_res.status_code == 200
        home_result = inspect_home_res.get_json()
        assert home_result["domain"] == "home"
        assert home_result["defect_count"] == 1

        # 2. Citizen saves the inspection record
        save_res = client.post("/api/inspections", json={
            "image_name": "wall_crack_test.png",
            "domain": "home",
            "road_name": "Flat 302, Building 4",
            "city": "Metropolis",
            "area": "Downtown",
            "detections": home_result["detections"],
            "defect_count": home_result["defect_count"],
            "confidence_threshold": 0.25,
            "status": "Open",
            "notes": "Severe diagonal crack on living room wall.",
        })
        assert save_res.status_code == 201
        saved_record = save_res.get_json()["inspection"]
        insp_id = saved_record["id"]
        assert saved_record["created_by_username"] == "active_citizen"
        assert saved_record["inspection_type"] == "home"

        # 3. Citizen retrieves their saved inspection detail
        detail_res = client.get(f"/api/inspections/{insp_id}")
        assert detail_res.status_code == 200
        assert detail_res.get_json()["inspection"]["id"] == insp_id

        # 4. Citizen retrieves and updates civic complaint draft
        draft_res = client.get(f"/api/inspections/{insp_id}/complaint-draft")
        assert draft_res.status_code == 200
        draft_data = draft_res.get_json()
        assert "draft" in draft_data
        assert "disclaimer" in draft_data

        update_draft_res = client.put(f"/api/inspections/{insp_id}/complaint-draft", json={
            "recipient_agency": "Building Safety & Housing Inspectorate",
            "subject": "Urgent Inspection Request: Wall Cracks at Flat 302",
            "complaint_body": "Formal notification regarding structural wall cracks observed on Oct 26.",
        })
        assert update_draft_res.status_code == 200
        assert update_draft_res.get_json()["draft"]["recipient_agency"] == "Building Safety & Housing Inspectorate"

        # 5. Citizen exports draft TXT & PDF
        txt_res = client.get(f"/api/inspections/{insp_id}/complaint-draft/export/txt")
        assert txt_res.status_code == 200
        assert txt_res.mimetype == "text/plain"

        # 6. Citizen lists their own records via /api/inspections?my_reports=1
        list_res = client.get("/api/inspections?my_reports=1")
        assert list_res.status_code == 200
        inspections = list_res.get_json()["inspections"]
        assert len(inspections) >= 1
        assert any(i["id"] == insp_id for i in inspections)


class TestCitizenSeparationAndAccessBoundaries:
    def test_citizen_strictly_denied_admin_and_maintenance_interfaces(self, citizen_test_env):
        client, test_db, _ = citizen_test_env
        admin = create_user("sys_admin", "AdminPass123!", role=ROLE_ADMIN, db_path=test_db)
        maint = create_user("maint_tech", "MaintPass123!", role=ROLE_MAINTENANCE, db_path=test_db)
        citizen = create_user("citizen_eve", "CitizenPass123!", role=ROLE_CITIZEN, db_path=test_db)

        # Log in as citizen
        client.post("/api/auth/login", json={"username": "citizen_eve", "password": "CitizenPass123!"})

        # A. Citizen CANNOT view user directory (/api/users GET)
        res_users = client.get("/api/users")
        assert res_users.status_code == 403
        assert res_users.get_json()["error_code"] == "FORBIDDEN"

        # B. Citizen CANNOT create user accounts (/api/users POST)
        res_create_user = client.post("/api/users", json={
            "username": "rogue_user",
            "password": "Password123!",
            "role": ROLE_ADMIN,
        })
        assert res_create_user.status_code == 403

        # C. Citizen CANNOT modify users (/api/users/<id> PATCH)
        res_patch_user = client.patch(f"/api/users/{admin['id']}", json={"role": ROLE_CITIZEN})
        assert res_patch_user.status_code == 403

        # D. Citizen CANNOT access Maintenance Work Queue (/api/maintenance/queue)
        res_queue = client.get("/api/maintenance/queue")
        assert res_queue.status_code == 403
        assert res_queue.get_json()["error_code"] == "FORBIDDEN"

        # E. Citizen CANNOT view maintenance staff list (/api/maintenance/staff)
        res_staff = client.get("/api/maintenance/staff")
        assert res_staff.status_code == 403

        # F. Citizen CANNOT assign maintenance tasks (/api/inspections/<id>/assign)
        res_assign = client.post("/api/inspections/1/assign", json={"assigned_to_user_id": maint["id"]})
        assert res_assign.status_code == 403

        # G. Citizen CANNOT update inspection status (/api/inspections/<id>/status PATCH)
        res_status = client.patch("/api/inspections/1/status", json={"status": "Resolved"})
        assert res_status.status_code == 403

        # H. Citizen CANNOT delete inspection records (/api/inspections/<id> DELETE)
        res_delete = client.delete("/api/inspections/1")
        assert res_delete.status_code == 403

        # I. Citizen CANNOT export institutional reports (/api/reports/preview, /api/reports/csv, /api/reports/pdf)
        assert client.get("/api/reports/preview").status_code == 403
        assert client.get("/api/reports/csv").status_code == 403
        assert client.get("/api/reports/pdf").status_code == 403

        # J. Citizen CANNOT reload models (/api/reload-model)
        assert client.post("/api/reload-model?domain=road").status_code == 403


class TestUnauthenticatedAccessProtection:
    def test_unauthenticated_requests_blocked_from_protected_apis(self, citizen_test_env):
        client, _, _ = citizen_test_env

        # Guest attempting inspection
        png_data = create_dummy_png_bytes()
        res_inspect = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(png_data), "test.png"), "domain": "road"},
            content_type="multipart/form-data"
        )
        assert res_inspect.status_code == 401
        assert res_inspect.get_json()["error_code"] == "UNAUTHORIZED"

        # Guest attempting to save inspection
        res_save = client.post("/api/inspections", json={"image_name": "test.png"})
        assert res_save.status_code == 401

        # Guest attempting to access inspection list
        res_list = client.get("/api/inspections")
        assert res_list.status_code == 401

        # Guest attempting to access /api/auth/me
        res_me = client.get("/api/auth/me")
        assert res_me.status_code == 401
