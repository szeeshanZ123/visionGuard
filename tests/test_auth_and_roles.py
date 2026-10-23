"""
VisionGuard AI - Phase 4.6: Authentication, User Roles, and Access Control Test Suite.

Validates:
1. Strong password hashing (scrypt via werkzeug.security), password validation, and username formatting.
2. User account lifecycle (creation, listing, role modification, activation/deactivation, self-deactivation protection).
3. Generic credential failure responses preventing username enumeration.
4. Safe first-admin bootstrap (environment variables, setup-admin endpoint once-only restriction).
5. Role-based backend authorization matrix:
   - Administrator: full system access, user management, record deletion, model reloading.
   - Inspector: defect detection, inspection record creation, report generation, CSV/PDF exports.
   - Maintenance Staff: inspection review, maintenance status/notes/deadline updates. Denied inspect, create, exports, admin.
6. CSRF protection on mutating requests (POST, PATCH, DELETE) and exemption of public/safe requests.
7. User attribution in maintenance activity audit logs, with preservation of NULL legacy identities.
8. Database migration backward compatibility on pre-existing schema.
"""

import os
import io
import json
import sqlite3
import pytest
import datetime
from pathlib import Path
from unittest.mock import MagicMock

from database.db import (
    init_db,
    get_db_connection,
    save_inspection,
    update_inspection_status,
    get_inspection_by_id,
    get_inspection_activity,
)
from database.auth import (
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    ROLE_MAINTENANCE,
    ALLOWED_ROLES,
    hash_password,
    verify_password,
    validate_username,
    validate_password_strength,
    validate_role,
    create_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    count_users,
    update_user,
    authenticate_user,
    init_admin_from_env,
)
from app.server import create_app


@pytest.fixture
def test_db_path(tmp_path):
    """Provides a fresh isolated database path for each test."""
    db_file = tmp_path / "test_auth.db"
    return str(db_file)


@pytest.fixture
def mock_detector():
    """Mock DefectDetectionService to avoid loading full YOLO model weights in unit tests."""
    mock = MagicMock()
    mock.is_loaded = True
    mock.load_model.return_value = True
    mock.status_message = "Mock Detector Ready"
    mock.model_path = "models/best.pt"
    mock.detect.return_value = [
        {
            "class_id": 0,
            "class_name": "D00",
            "distress_category": "Longitudinal Crack",
            "confidence": 0.88,
            "bbox": [10, 20, 100, 150],
        }
    ]
    return mock


@pytest.fixture
def auth_app(test_db_path, mock_detector):
    """Creates a Flask application instance with authentication and CSRF strictly enforced."""
    app = create_app(
        detector=mock_detector,
        test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db_path,
            "AUTH_ENABLED": True,
            "ENFORCE_CSRF": True,
            "SECRET_KEY": "test-secret-key-32-chars-minimum-visionguard",
        }
    )
    return app


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


# =============================================================================
# 1. Password Hashing and Input Validation Tests
# =============================================================================
class TestAuthSecurityBasics:
    def test_password_hashing_and_verification(self):
        """Verifies strong password hashing and positive/negative verification."""
        raw_pw = "SecureP@ssw0rd123"
        pw_hash = hash_password(raw_pw)

        assert pw_hash != raw_pw
        assert pw_hash.startswith("scrypt:") or len(pw_hash) > 20
        assert verify_password(pw_hash, raw_pw) is True
        assert verify_password(pw_hash, "WrongPassword") is False
        assert verify_password(pw_hash, "") is False

    def test_password_strength_validation(self):
        """Rejects passwords shorter than 8 characters or empty."""
        valid, err = validate_password_strength("short")
        assert valid is False
        assert "8 characters" in err

        valid, err = validate_password_strength("")
        assert valid is False

        valid, err = validate_password_strength("ValidPassword123!")
        assert valid is True
        assert err is None

    def test_username_validation(self):
        """Enforces clean alphanumeric username standards with length bounds."""
        valid, err = validate_username("ab")  # Too short
        assert valid is False

        valid, err = validate_username("invalid space")
        assert valid is False

        valid, err = validate_username("valid_user-1")
        assert valid is True
        assert err is None

    def test_role_validation(self):
        """Ensures only approved application roles are allowed."""
        for r in ALLOWED_ROLES:
            valid, err = validate_role(r)
            assert valid is True

        valid, err = validate_role("superuser")
        assert valid is False


# =============================================================================
# 2. User CRUD and Account Lifecycle Tests
# =============================================================================
class TestUserLifecycle:
    def test_create_and_retrieve_user(self, test_db_path):
        """Verifies creating users, case-insensitive lookup, and password hash exclusion."""
        user = create_user(
            username="road_inspector_1",
            password="StrongPassword123",
            role=ROLE_INSPECTOR,
            email="inspector1@visionguard.org",
            db_path=test_db_path
        )
        assert user["id"] is not None
        assert user["username"] == "road_inspector_1"
        assert user["role"] == ROLE_INSPECTOR
        assert "password_hash" not in user

        by_id = get_user_by_id(user["id"], db_path=test_db_path)
        assert by_id["username"] == "road_inspector_1"

        by_name = get_user_by_username("ROAD_INSPECTOR_1", db_path=test_db_path)
        assert by_name["id"] == user["id"]

    def test_duplicate_username_rejected(self, test_db_path):
        """Prevents duplicate usernames."""
        create_user("unique_user", "Password123", role=ROLE_INSPECTOR, db_path=test_db_path)
        with pytest.raises(ValueError, match="already in use"):
            create_user("unique_user", "DifferentPassword123", role=ROLE_INSPECTOR, db_path=test_db_path)

    def test_user_updates_and_password_change(self, test_db_path):
        """Tests updating role, status, and resetting password."""
        user = create_user("staff_member", "Password123", role=ROLE_MAINTENANCE, db_path=test_db_path)

        # Update role to inspector
        updated = update_user(user["id"], {"role": ROLE_INSPECTOR}, db_path=test_db_path)
        assert updated["role"] == ROLE_INSPECTOR

        # Update password
        update_user(user["id"], {"password": "NewSecretPassword123"}, db_path=test_db_path)
        is_auth, auth_user, _ = authenticate_user("staff_member", "NewSecretPassword123", db_path=test_db_path)
        assert is_auth is True

        # Old password fails
        is_auth, _, _ = authenticate_user("staff_member", "Password123", db_path=test_db_path)
        assert is_auth is False


# =============================================================================
# 3. Authentication & First-Admin Bootstrap Tests
# =============================================================================
class TestAuthenticationEndpoints:
    def test_first_admin_setup_endpoint(self, client, test_db_path):
        """When 0 users exist, setup-admin creates initial admin. Subsequent attempts are forbidden."""
        assert count_users(db_path=test_db_path) == 0

        # Status indicates setup required
        res = client.get("/api/auth/status")
        assert res.status_code == 200
        assert res.get_json()["requires_setup"] is True
        assert res.get_json()["authenticated"] is False

        # Create first admin
        res = client.post("/api/auth/setup-admin", json={
            "username": "sysadmin",
            "password": "AdminPassword123",
            "email": "admin@visionguard.org"
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["status"] == "success"
        assert data["user"]["role"] == ROLE_ADMIN

        # Subsequent attempt to setup-admin must be blocked
        res2 = client.post("/api/auth/setup-admin", json={
            "username": "hacker",
            "password": "Password123"
        })
        assert res2.status_code == 403
        assert res2.get_json()["error_code"] == "SETUP_FORBIDDEN"

    def test_environment_variable_bootstrap(self, test_db_path, monkeypatch):
        """Verifies safe bootstrapping of admin from environment variables."""
        monkeypatch.setenv("VISIONGUARD_ADMIN_USERNAME", "env_admin")
        monkeypatch.setenv("VISIONGUARD_ADMIN_PASSWORD", "EnvAdminP@ss123")
        monkeypatch.setenv("VISIONGUARD_ADMIN_EMAIL", "envadmin@visionguard.org")

        admin = init_admin_from_env(db_path=test_db_path)
        assert admin is not None
        assert admin["username"] == "env_admin"
        assert admin["role"] == ROLE_ADMIN

    def test_invalid_credentials_generic_response(self, client, test_db_path):
        """Prevents username enumeration by returning generic error messages."""
        create_user("known_user", "ValidPassword123", role=ROLE_INSPECTOR, db_path=test_db_path)

        # Non-existent user
        res1 = client.post("/api/auth/login", json={"username": "unknown_user", "password": "WrongPassword"})
        assert res1.status_code == 401

        # Real user, wrong password
        res2 = client.post("/api/auth/login", json={"username": "known_user", "password": "WrongPassword"})
        assert res2.status_code == 401

        # Error messages should match
        assert res1.get_json()["message"] == res2.get_json()["message"]

    def test_deactivated_account_blocked(self, client, test_db_path):
        """Deactivated accounts cannot log in or access protected endpoints."""
        u = create_user("fired_staff", "Password123", role=ROLE_MAINTENANCE, is_active=0, db_path=test_db_path)

        res = client.post("/api/auth/login", json={"username": "fired_staff", "password": "Password123"})
        assert res.status_code == 401
        assert "deactivated" in res.get_json()["message"].lower()

    def test_login_logout_flow(self, client, test_db_path):
        """Complete login, session verification, and logout cycle."""
        create_user("inspector_bob", "BobPassword123", role=ROLE_INSPECTOR, db_path=test_db_path)

        login_res = client.post("/api/auth/login", json={"username": "inspector_bob", "password": "BobPassword123"})
        assert login_res.status_code == 200
        csrf_token = login_res.get_json()["csrf_token"]
        assert csrf_token is not None

        # Verify /api/auth/me works
        me_res = client.get("/api/auth/me")
        assert me_res.status_code == 200
        assert me_res.get_json()["user"]["username"] == "inspector_bob"

        # Logout
        logout_res = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
        assert logout_res.status_code == 200

        # /api/auth/me now requires login
        me_res2 = client.get("/api/auth/me")
        assert me_res2.status_code == 401


# =============================================================================
# 4. Role-based Access Control (RBAC) Matrix Tests
# =============================================================================
class TestRoleAccessControl:
    @pytest.fixture(autouse=True)
    def setup_roles_and_records(self, test_db_path):
        """Sets up Admin, Inspector, Maintenance Staff, and a test inspection record."""
        self.admin = create_user("admin_user", "AdminSecret123", role=ROLE_ADMIN, db_path=test_db_path)
        self.inspector = create_user("inspector_user", "InspectorSecret123", role=ROLE_INSPECTOR, db_path=test_db_path)
        self.maintenance = create_user("maint_user", "MaintSecret123", role=ROLE_MAINTENANCE, db_path=test_db_path)

        # Create one baseline record in SQLite
        self.record = save_inspection({
            "image_name": "road_baseline.jpg",
            "road_name": "Highway 101",
            "status": "Open",
            "defect_count": 1,
            "detections": [{"distress_category": "Pothole", "confidence": 0.9}],
            "target_repair_date": "2026-11-01"
        }, db_path=test_db_path)

    def _login(self, client, username, password):
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200
        return res.get_json()["csrf_token"]

    def test_unauthenticated_requests_denied(self, client):
        """Unauthenticated requests to protected endpoints return 401."""
        endpoints = [
            ("GET", "/api/inspections"),
            ("GET", f"/api/inspections/{self.record['id']}"),
            ("GET", "/api/dashboard/stats"),
            ("GET", "/api/reports/preview"),
            ("GET", "/api/users"),
        ]
        for method, url in endpoints:
            if method == "GET":
                res = client.get(url)
            assert res.status_code == 401, f"{method} {url} should return 401"
            assert res.get_json()["error_code"] == "UNAUTHORIZED"

    def test_admin_has_full_access(self, client):
        """Admin role can access user management, model reload, reports, and delete."""
        csrf = self._login(client, "admin_user", "AdminSecret123")
        headers = {"X-CSRF-Token": csrf}

        # User management
        assert client.get("/api/users").status_code == 200

        # Reload model
        assert client.post("/api/reload-model", headers=headers).status_code in [200, 503]

        # Reports
        assert client.get("/api/reports/preview").status_code == 200

        # Delete inspection
        del_res = client.delete(f"/api/inspections/{self.record['id']}", headers=headers)
        assert del_res.status_code == 200

    def test_inspector_permissions(self, client):
        """
        Inspector CAN: inspect, save, view, export reports.
        Inspector CANNOT: user management, model reload, maintenance status update, delete.
        """
        csrf = self._login(client, "inspector_user", "InspectorSecret123")
        headers = {"X-CSRF-Token": csrf}

        # Can view inspections and preview reports
        assert client.get("/api/inspections").status_code == 200
        assert client.get("/api/reports/preview").status_code == 200
        assert client.get("/api/reports/export/csv").status_code == 200

        # Can save new inspection
        save_res = client.post("/api/inspections", json={
            "image_name": "inspector_new.jpg",
            "road_name": "Main Street",
            "status": "Open",
            "defect_count": 0,
        }, headers=headers)
        assert save_res.status_code == 201

        # Denied user management (403)
        assert client.get("/api/users").status_code == 403
        assert client.post("/api/users", json={}, headers=headers).status_code == 403

        # Denied model reload (403)
        assert client.post("/api/reload-model", headers=headers).status_code == 403

        # Denied maintenance status updates (403)
        status_res = client.patch(f"/api/inspections/{self.record['id']}/status", json={"status": "Resolved"}, headers=headers)
        assert status_res.status_code == 403

        # Denied delete (403)
        del_res = client.delete(f"/api/inspections/{self.record['id']}", headers=headers)
        assert del_res.status_code == 403

    def test_maintenance_staff_permissions(self, client):
        """
        Maintenance CAN: view records, view dashboard, update status/target dates/notes.
        Maintenance CANNOT: perform defect inspection, save inspection, export reports, manage users.
        """
        csrf = self._login(client, "maint_user", "MaintSecret123")
        headers = {"X-CSRF-Token": csrf}

        # Can view records and dashboard
        assert client.get("/api/inspections").status_code == 200
        assert client.get("/api/dashboard/stats").status_code == 200
        assert client.get(f"/api/inspections/{self.record['id']}").status_code == 200

        # Can update maintenance status & target deadline
        update_res = client.patch(
            f"/api/inspections/{self.record['id']}/status",
            json={"status": "Repair in Progress", "notes": "Crews dispatched to site.", "target_repair_date": "2026-11-10"},
            headers=headers
        )
        assert update_res.status_code == 200
        assert update_res.get_json()["inspection"]["status"] == "Repair in Progress"

        # Denied defect inference (403)
        inspect_res = client.post("/api/inspect", data={"file": (io.BytesIO(b"dummy"), "test.jpg")}, headers=headers)
        assert inspect_res.status_code == 403

        # Denied saving new inspection (403)
        save_res = client.post("/api/inspections", json={"image_name": "test.jpg"}, headers=headers)
        assert save_res.status_code == 403

        # Denied report preview & exports (403)
        assert client.get("/api/reports/preview").status_code == 403
        assert client.get("/api/reports/export/csv").status_code == 403
        assert client.get("/api/reports/export/pdf").status_code == 403

        # Denied user management (403)
        assert client.get("/api/users").status_code == 403


# =============================================================================
# 5. User Management & Administrator Controls Tests
# =============================================================================
class TestUserManagementControls:
    def test_admin_creates_and_manages_accounts(self, client, test_db_path):
        """Administrator creates accounts, alters roles, and deactivates accounts."""
        create_user("the_admin", "AdminSecret123", role=ROLE_ADMIN, db_path=test_db_path)
        login_res = client.post("/api/auth/login", json={"username": "the_admin", "password": "AdminSecret123"})
        csrf = login_res.get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        # 1. Create a maintenance user
        res = client.post("/api/users", json={
            "username": "road_crew_lead",
            "password": "CrewLeaderPassword123",
            "role": ROLE_MAINTENANCE,
            "email": "crew@visionguard.org"
        }, headers=headers)
        assert res.status_code == 201
        created_id = res.get_json()["user"]["id"]

        # 2. Deactivate the user
        deact_res = client.patch(f"/api/users/{created_id}", json={"is_active": False}, headers=headers)
        assert deact_res.status_code == 200
        assert deact_res.get_json()["user"]["is_active"] is False

        # Verify user is deactivated in database
        check_u = get_user_by_id(created_id, db_path=test_db_path)
        assert check_u["is_active"] is False

    def test_admin_cannot_deactivate_or_demote_self(self, client, test_db_path):
        """Safety control: administrator cannot lock themselves out."""
        admin = create_user("super_admin", "SuperAdminPw123", role=ROLE_ADMIN, db_path=test_db_path)
        login_res = client.post("/api/auth/login", json={"username": "super_admin", "password": "SuperAdminPw123"})
        csrf = login_res.get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        # Attempt self-deactivation
        deact_self = client.patch(f"/api/users/{admin['id']}", json={"is_active": False}, headers=headers)
        assert deact_self.status_code == 400
        assert deact_self.get_json()["error_code"] == "SELF_DEACTIVATION_DENIED"

        # Attempt self-demotion
        demote_self = client.patch(f"/api/users/{admin['id']}", json={"role": ROLE_MAINTENANCE}, headers=headers)
        assert demote_self.status_code == 400
        assert demote_self.get_json()["error_code"] == "SELF_DEMOTION_DENIED"


# =============================================================================
# 6. CSRF Protection Enforcement Tests
# =============================================================================
class TestCSRFProtection:
    def test_csrf_token_required_for_mutations(self, client, test_db_path):
        """Mutating browser requests (POST, PATCH, DELETE) require a valid CSRF token."""
        create_user("admin_csrf", "AdminPassword123", role=ROLE_ADMIN, db_path=test_db_path)
        login_res = client.post("/api/auth/login", json={"username": "admin_csrf", "password": "AdminPassword123"})
        assert login_res.status_code == 200
        valid_csrf = login_res.get_json()["csrf_token"]

        # 1. Missing CSRF token -> 403
        res_missing = client.post("/api/users", json={
            "username": "new_guy", "password": "Password123", "role": ROLE_INSPECTOR
        })
        assert res_missing.status_code == 403
        assert res_missing.get_json()["error_code"] == "CSRF_TOKEN_INVALID"

        # 2. Invalid CSRF token -> 403
        res_invalid = client.post("/api/users", json={
            "username": "new_guy", "password": "Password123", "role": ROLE_INSPECTOR
        }, headers={"X-CSRF-Token": "bogus-csrf-token-12345"})
        assert res_invalid.status_code == 403

        # 3. Valid CSRF token -> 201
        res_valid = client.post("/api/users", json={
            "username": "new_guy", "password": "Password123", "role": ROLE_INSPECTOR
        }, headers={"X-CSRF-Token": valid_csrf})
        assert res_valid.status_code == 201


# =============================================================================
# 7. User Attribution in Audit History & Migration Compatibility
# =============================================================================
class TestUserAttributionAndMigrations:
    def test_authenticated_user_attributed_in_audit_history(self, client, test_db_path):
        """Activity logs capture authenticated user_id and username upon state changes."""
        crew_user = create_user("repair_specialist_sam", "SamPassword123", role=ROLE_MAINTENANCE, db_path=test_db_path)
        rec = save_inspection({"image_name": "audit_test.jpg", "status": "Open"}, db_path=test_db_path)

        # Login as Sam
        login_res = client.post("/api/auth/login", json={"username": "repair_specialist_sam", "password": "SamPassword123"})
        csrf = login_res.get_json()["csrf_token"]

        # Update status
        client.patch(
            f"/api/inspections/{rec['id']}/status",
            json={"status": "Under Review", "notes": "Inspected road shoulder visually."},
            headers={"X-CSRF-Token": csrf}
        )

        activities = get_inspection_activity(rec["id"], db_path=test_db_path)
        assert len(activities) >= 2
        latest_act = activities[-1]

        assert latest_act["new_status"] == "Under Review"
        assert latest_act["user_id"] == crew_user["id"]
        assert latest_act["username"] == "repair_specialist_sam"

    def test_database_migration_preserves_legacy_data(self, tmp_path):
        """Simulates an older SQLite DB created before Phase 4.6 and verifies safe schema migration."""
        legacy_db = str(tmp_path / "legacy_v4_5.db")
        conn = sqlite3.connect(legacy_db)
        cur = conn.cursor()

        # Create older schema without users table or user_id columns
        cur.execute("""
        CREATE TABLE defect_inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_name TEXT NOT NULL,
            file_path TEXT,
            status TEXT DEFAULT 'Open',
            road_name TEXT,
            target_repair_date TEXT
        );
        """)
        cur.execute("""
        CREATE TABLE maintenance_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            previous_status TEXT,
            new_status TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cur.execute("INSERT INTO defect_inspections (image_name, road_name) VALUES ('legacy_road.jpg', 'Route 66');")
        cur.execute("INSERT INTO maintenance_activity_log (inspection_id, action_type, new_status, notes) VALUES (1, 'created', 'Open', 'Legacy note');")
        conn.commit()
        conn.close()

        # Run init_db to trigger migrations
        init_db(legacy_db)

        # Verify old data is intact
        conn2 = sqlite3.connect(legacy_db)
        conn2.row_factory = sqlite3.Row
        cur2 = conn2.cursor()

        cur2.execute("SELECT * FROM defect_inspections WHERE id = 1;")
        ins_row = dict(cur2.fetchone())
        assert ins_row["road_name"] == "Route 66"
        assert "created_by_user_id" in ins_row
        assert ins_row["created_by_user_id"] is None  # Preserved as NULL, no fake identity

        cur2.execute("SELECT * FROM maintenance_activity_log WHERE id = 1;")
        act_row = dict(cur2.fetchone())
        assert act_row["notes"] == "Legacy note"
        assert "user_id" in act_row
        assert act_row["user_id"] is None  # Preserved as NULL

        # Verify users table now exists
        cur2.execute("SELECT COUNT(*) as count FROM users;")
        assert cur2.fetchone()["count"] == 0
        conn2.close()


# =============================================================================
# 9. Regression Tests: 401 Authentication Lifecycle & Session Diagnostics
# =============================================================================
class TestAuthenticationLifecycleAndErrors:
    """
    Explicit regression tests for HTTP 401 handling across the four reported endpoints:
    - GET /api/inspections?limit=1
    - GET /api/dashboard/stats
    - GET /api/reports/preview
    - GET /api/inspections?has_coords=true&limit=500
    Validates:
    - Logged-out state returns HTTP 401 UNAUTHORIZED on protected APIs.
    - Public endpoints (/api/health, /api/auth/status) remain 200 without login.
    - Login establishes session and permits calls to protected endpoints.
    - Logout terminates session and restores HTTP 401.
    - Expired/invalid session cookies return HTTP 401.
    - Session for deactivated user is rejected with HTTP 401.
    - Role restrictions are strictly enforced across roles.
    """

    REPORTED_ENDPOINTS = [
        "/api/inspections?limit=1",
        "/api/dashboard/stats",
        "/api/reports/preview",
        "/api/inspections?has_coords=true&limit=500",
    ]

    def test_logged_out_requests_return_401_on_reported_endpoints(self, client):
        """Unauthenticated requests to all reported endpoints return HTTP 401."""
        for endpoint in self.REPORTED_ENDPOINTS:
            res = client.get(endpoint)
            assert res.status_code == 401, f"Expected 401 for unauthenticated {endpoint}, got {res.status_code}"
            data = res.get_json()
            assert data["status"] == "error"
            assert data["error_code"] == "UNAUTHORIZED"
            assert "authentication required" in data["message"].lower()

    def test_public_endpoints_accessible_without_authentication(self, client):
        """Public status/health endpoints return HTTP 200 without authentication."""
        health_res = client.get("/api/health")
        assert health_res.status_code == 200
        health_data = health_res.get_json()
        assert health_data["status"] in ("healthy", "online")

        status_res = client.get("/api/auth/status")
        assert status_res.status_code == 200
        status_data = status_res.get_json()
        assert status_data["authenticated"] is False
        assert status_data["user"] is None
        assert "csrf_token" in status_data

    def test_successful_login_authorizes_all_reported_endpoints(self, client, test_db_path):
        """Successful login establishes session and permits calls to all 4 reported endpoints."""
        create_user("lead_inspector", "InspectSecure123", role=ROLE_ADMIN, db_path=test_db_path)

        login_res = client.post("/api/auth/login", json={
            "username": "lead_inspector",
            "password": "InspectSecure123",
        })
        assert login_res.status_code == 200
        login_data = login_res.get_json()
        assert login_data["status"] == "success"
        assert login_data["user"]["username"] == "lead_inspector"

        # Check all reported endpoints return 200 for the authenticated session
        for endpoint in self.REPORTED_ENDPOINTS:
            res = client.get(endpoint)
            assert res.status_code == 200, f"Expected 200 for authenticated {endpoint}, got {res.status_code}"
            data = res.get_json()
            assert data["status"] == "success"

        # Check /api/auth/status confirms authentication
        status_res = client.get("/api/auth/status")
        assert status_res.status_code == 200
        status_data = status_res.get_json()
        assert status_data["authenticated"] is True
        assert status_data["user"]["username"] == "lead_inspector"

    def test_logout_terminates_session_and_restores_401(self, client, test_db_path):
        """Logging out destroys the session cookie and causes subsequent requests to return HTTP 401."""
        create_user("session_tester", "SessionPass123", role=ROLE_ADMIN, db_path=test_db_path)

        login_res = client.post("/api/auth/login", json={
            "username": "session_tester",
            "password": "SessionPass123",
        })
        csrf_token = login_res.get_json()["csrf_token"]

        # Confirm authorized
        assert client.get("/api/dashboard/stats").status_code == 200

        # Perform logout
        logout_res = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
        assert logout_res.status_code == 200
        assert logout_res.get_json()["status"] == "success"
        assert client.get("/api/auth/status").get_json()["authenticated"] is False

        # Endpoints must now return 401
        for endpoint in self.REPORTED_ENDPOINTS:
            res = client.get(endpoint)
            assert res.status_code == 401, f"Expected 401 after logout for {endpoint}, got {res.status_code}"

    def test_expired_or_invalid_session_cookie_returns_401(self, client):
        """Requests with corrupted or invalid session cookies are rejected with HTTP 401."""
        client.set_cookie("session", "tampered.or.expired.cookie.token")

        for endpoint in self.REPORTED_ENDPOINTS:
            res = client.get(endpoint)
            assert res.status_code == 401
            assert res.get_json()["error_code"] == "UNAUTHORIZED"

    def test_deactivated_user_session_returns_401(self, client, test_db_path):
        """Active session for a user who gets deactivated in the database returns 401 on next request."""
        u = create_user("active_staff", "StaffSecret123", role=ROLE_ADMIN, db_path=test_db_path)

        login_res = client.post("/api/auth/login", json={
            "username": "active_staff",
            "password": "StaffSecret123",
        })
        assert login_res.status_code == 200
        assert client.get("/api/dashboard/stats").status_code == 200

        # Deactivate user directly in the database
        update_user(u["id"], {"is_active": 0}, db_path=test_db_path)

        # Protected request should now fail with 401
        res = client.get("/api/dashboard/stats")
        assert res.status_code == 401
        data = res.get_json()
        assert data["error_code"] == "UNAUTHORIZED"
        assert "authentication required" in data["message"].lower()
        # Verify session was revoked
        status_res = client.get("/api/auth/status")
        assert status_res.get_json()["authenticated"] is False

    def test_role_restrictions_enforced_between_inspector_and_maintenance(self, client, test_db_path):
        """RBAC permissions correctly prevent unauthorized role operations."""
        create_user("test_inspector", "InspectPass123", role=ROLE_INSPECTOR, db_path=test_db_path)
        create_user("test_maint", "MaintPass123", role=ROLE_MAINTENANCE, db_path=test_db_path)

        # 1. Inspector: Can access reports, but denied maintenance queue and user management
        client.post("/api/auth/login", json={"username": "test_inspector", "password": "InspectPass123"})
        assert client.get("/api/reports/preview").status_code == 200
        assert client.get("/api/maintenance/queue").status_code == 403
        assert client.get("/api/users").status_code == 403
        client.post("/api/auth/logout")

        # 2. Maintenance: Can access queue, but denied report preview and inspect
        client.post("/api/auth/login", json={"username": "test_maint", "password": "MaintPass123"})
        assert client.get("/api/maintenance/queue").status_code == 200
        assert client.get("/api/reports/preview").status_code == 403
        assert client.post("/api/inspect").status_code == 403
        client.post("/api/auth/logout")


# =============================================================================
# 9. Frontend Auth Modal UI Regression Tests
# =============================================================================
class TestAuthModalFrontendContracts:
    """Verifies that the HTML template, CSS styling, and client-side JavaScript
    form an airtight contract for the Sign In / Setup Admin modal interactions.
    """

    def test_auth_modal_html_elements_present(self, client):
        """Verifies all modal and trigger elements exist in the server-rendered HTML."""
        res = client.get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        # Modal container and dialog
        assert 'id="authModal"' in html
        assert 'class="modal-overlay"' in html
        assert 'id="authModalTitle"' in html
        assert 'id="closeAuthModalBtn"' in html
        assert 'id="authErrorAlert"' in html

        # Forms
        assert 'id="loginForm"' in html
        assert 'id="loginUsername"' in html
        assert 'id="loginPassword"' in html
        assert 'id="cancelAuthBtn"' in html
        assert 'id="loginSubmitBtn"' in html

        assert 'id="setupAdminForm"' in html
        assert 'id="setupRequiredNotice"' in html
        assert 'id="setupAdminUsername"' in html
        assert 'id="setupAdminPassword"' in html
        assert 'id="setupAdminSubmitBtn"' in html

        # Sign-in triggers
        assert 'id="openAuthModalBtn"' in html
        assert 'id="authGuestBanner"' in html
        assert 'id="guestBannerSignInBtn"' in html
        assert 'id="mapErrorBanner"' in html

    def test_auth_modal_css_rules_present(self):
        """Verifies modal overlay and dialog styles are properly declared in styles.css."""
        css_path = Path(__file__).parent.parent / "app" / "static" / "css" / "styles.css"
        assert css_path.exists()
        css = css_path.read_text(encoding="utf-8")

        assert ".modal-overlay" in css
        assert "position: fixed" in css
        assert "z-index: 99999" in css
        assert ".modal-dialog" in css
        assert ".modal-header" in css
        assert ".modal-close-btn" in css

    def test_auth_modal_javascript_wiring_present(self):
        """Verifies app.js defines centralized modal controls and delegated event listeners."""
        js_path = Path(__file__).parent.parent / "app" / "static" / "js" / "app.js"
        assert js_path.exists()
        js = js_path.read_text(encoding="utf-8")

        # Centralized modal open/close functions
        assert "async function openAuthModal" in js
        assert "function closeAuthModal" in js

        # Delegated event listener targeting all triggers
        assert "#guestBannerSignInBtn" in js
        assert ".guest-login-btn" in js
        assert "#openAuthModalBtn" in js
        assert "openAuthModal(preferredMode)" in js

        # Escape keydown listener
        assert 'e.key === "Escape"' in js

        # No brittle openAuthModalBtn.click() chains
        assert "openAuthModalBtn.click()" not in js


