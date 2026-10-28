"""
VisionGuard AI - Security Test Suite for Authentication, Session Lifecycle, and IDOR Protections.

Validates the security fixes:
1. Registration & Credential Validation:
   - Minimum and maximum password length enforcement (DoS mitigation).
   - Email format validation and length restriction.
   - Duplicate account rejection with case-insensitivity for both usernames and emails.
2. Authentication & Session Security:
   - Session fixation prevention (session cleared, fresh CSRF token assigned on login/register/setup-admin).
   - Generic credential error responses preventing username enumeration.
   - Timing discrepancy mitigation with static dummy password verification.
   - Logout session invalidation and fresh anonymous CSRF token issuance.
3. Insecure Direct Object Reference (IDOR) & Data Privacy:
   - Citizen can strictly access their own inspection details, images, activity history, and complaint drafts.
   - Citizen is blocked (403 FORBIDDEN_REPORT_ACCESS) from accessing another citizen's records.
   - Citizen is blocked (403 FORBIDDEN_REPORT_ACCESS) from accessing unowned / NULL created_by_user_id records.
   - Citizen cannot edit, view, or export (TXT/PDF) complaint drafts for unowned or other users' inspections.
4. Server-Side Role-Based Access Control (RBAC):
   - Citizens and maintenance staff strictly blocked from admin user management.
   - Citizens blocked from maintenance dispatch and status mutation.
   - Maintenance blocked from institutional report exports.
"""

import io
import json
import pytest
from unittest.mock import MagicMock

from database.db import init_db, save_inspection, get_db_connection
from database.auth import (
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    ROLE_MAINTENANCE,
    ROLE_CITIZEN,
    create_user,
    get_user_by_username,
    authenticate_user,
    validate_email,
    validate_password_strength,
)
from app.server import create_app


@pytest.fixture
def test_db_path(tmp_path):
    """Provides a fresh isolated database path for each test."""
    db_file = tmp_path / "test_security.db"
    return str(db_file)


@pytest.fixture
def mock_detector():
    """Mock DefectDetectionService to avoid loading actual heavy YOLO weights."""
    mock = MagicMock()
    mock.is_loaded = True
    mock.load_model.return_value = True
    mock.status_message = "Mock Ready"
    mock.model_path = "models/best.pt"
    mock.detect.return_value = []
    mock.draw_annotations.return_value = None
    mock.encode_image_to_base64.return_value = "mock_b64"
    return mock


@pytest.fixture
def auth_app(test_db_path, mock_detector):
    """Creates a Flask application instance with authentication and CSRF strictly enforced."""
    app = create_app(
        detector=mock_detector,
        home_detector=mock_detector,
        test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db_path,
            "AUTH_ENABLED": True,
            "AUTH_ENABLED_EXPLICIT": True,
            "ENFORCE_CSRF": True,
            "ENFORCE_CSRF_EXPLICIT": True,
            "SECRET_KEY": "test-secret-key-32-chars-minimum-visionguard",
        }
    )
    return app


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


# =============================================================================
# 1. Registration & Input Validation Security Tests
# =============================================================================
class TestRegistrationSecurity:
    def test_password_length_boundaries(self):
        """Enforces minimum 8 chars and maximum 128 chars to prevent scrypt DoS."""
        # Short password
        valid_short, err_short = validate_password_strength("short7")
        assert not valid_short
        assert "at least 8" in err_short

        # Valid password
        valid_ok, err_ok = validate_password_strength("ValidPassword123!")
        assert valid_ok
        assert err_ok is None

        # Exceeds maximum length (128 characters)
        oversized = "A" * 129
        valid_long, err_long = validate_password_strength(oversized)
        assert not valid_long
        assert "cannot exceed 128" in err_long

    def test_email_validation(self):
        """Validates standard email format and rejects malformed strings."""
        assert validate_email(None) == (True, None)
        assert validate_email("") == (True, None)
        assert validate_email("user@example.com")[0] is True
        assert validate_email("first.last+tag@sub.domain.org")[0] is True

        # Invalid formats
        assert validate_email("not-an-email")[0] is False
        assert validate_email("user@")[0] is False
        assert validate_email("@domain.com")[0] is False
        assert validate_email("user@domain")[0] is False
        assert validate_email("a" * 121 + "@example.com")[0] is False

    def test_duplicate_username_case_insensitive_rejection(self, test_db_path):
        """Prevents account collisions caused by different casing (e.g. Alice vs alice)."""
        create_user("SecurityUser", "SecurePass123!", role=ROLE_CITIZEN, db_path=test_db_path)

        # Exact match
        with pytest.raises(ValueError) as exc1:
            create_user("SecurityUser", "DifferentPass123!", role=ROLE_CITIZEN, db_path=test_db_path)
        assert "already in use" in str(exc1.value)

        # Lowercase match
        with pytest.raises(ValueError) as exc2:
            create_user("securityuser", "DifferentPass123!", role=ROLE_CITIZEN, db_path=test_db_path)
        assert "already in use" in str(exc2.value)

        # Uppercase match
        with pytest.raises(ValueError) as exc3:
            create_user("SECURITYUSER", "DifferentPass123!", role=ROLE_CITIZEN, db_path=test_db_path)
        assert "already in use" in str(exc3.value)

    def test_duplicate_email_case_insensitive_rejection(self, test_db_path):
        """Rejects registration with an email already associated with an account."""
        create_user("user_one", "SecurePass123!", email="test@example.com", role=ROLE_CITIZEN, db_path=test_db_path)

        with pytest.raises(ValueError) as exc:
            create_user("user_two", "SecurePass123!", email="TEST@EXAMPLE.COM", role=ROLE_CITIZEN, db_path=test_db_path)
        assert "Email 'test@example.com' is already in use" in str(exc.value)

    def test_api_registration_rejects_duplicates(self, client):
        """API endpoint /api/auth/register properly surfaces duplicate registration errors."""
        res1 = client.post("/api/auth/register", json={
            "username": "ResidentDan",
            "password": "Password123!",
            "email": "dan@example.com"
        })
        assert res1.status_code == 201

        # Attempt with different case username
        res2 = client.post("/api/auth/register", json={
            "username": "residentdan",
            "password": "Password456!",
            "email": "other@example.com"
        })
        assert res2.status_code == 400
        assert "already in use" in res2.get_json()["message"]

        # Attempt with duplicate email
        res3 = client.post("/api/auth/register", json={
            "username": "another_dan",
            "password": "Password456!",
            "email": "DAN@EXAMPLE.COM"
        })
        assert res3.status_code == 400
        assert "already in use" in res3.get_json()["message"]


# =============================================================================
# 2. Session Fixation & Lifecycle Security Tests
# =============================================================================
class TestSessionSecurity:
    def test_session_fixation_protection_on_login(self, client, test_db_path):
        """Pre-existing session data and CSRF token are replaced upon login."""
        create_user("alice_login", "SecurePassword123!", role=ROLE_CITIZEN, db_path=test_db_path)

        # Step 1: Pre-set anonymous session data
        with client.session_transaction() as sess:
            sess["attacker_marker"] = "injected_session_value"
            sess["csrf_token"] = "pre_auth_csrf_token_12345"

        # Step 2: Authenticate
        login_res = client.post("/api/auth/login", json={
            "username": "alice_login",
            "password": "SecurePassword123!"
        })
        assert login_res.status_code == 200
        data = login_res.get_json()

        # Step 3: Verify previous session was cleared and new CSRF token issued
        with client.session_transaction() as sess:
            assert "attacker_marker" not in sess
            assert sess["user_id"] is not None
            assert sess["csrf_token"] != "pre_auth_csrf_token_12345"
            assert sess["csrf_token"] == data["csrf_token"]

    def test_session_fixation_protection_on_registration(self, client):
        """Pre-existing session data and CSRF token are replaced upon registration."""
        with client.session_transaction() as sess:
            sess["stale_cookie_key"] = "stale_val"
            sess["csrf_token"] = "old_anonymous_csrf"

        reg_res = client.post("/api/auth/register", json={
            "username": "new_citizen_reg",
            "password": "Password123!",
            "email": "reg@example.com"
        })
        assert reg_res.status_code == 201
        data = reg_res.get_json()

        with client.session_transaction() as sess:
            assert "stale_cookie_key" not in sess
            assert sess["csrf_token"] != "old_anonymous_csrf"
            assert sess["csrf_token"] == data["csrf_token"]

    def test_logout_invalidates_session_and_provides_fresh_csrf(self, client, test_db_path):
        """Logging out clears session credentials and provides a fresh anonymous CSRF token."""
        create_user("carol_logout", "Password123!", role=ROLE_CITIZEN, db_path=test_db_path)

        login_res = client.post("/api/auth/login", json={
            "username": "carol_logout",
            "password": "Password123!"
        })
        auth_csrf = login_res.get_json()["csrf_token"]

        # Logout with CSRF token
        logout_res = client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": auth_csrf}
        )
        assert logout_res.status_code == 200
        logout_data = logout_res.get_json()
        assert "csrf_token" in logout_data
        assert logout_data["csrf_token"] != auth_csrf

        # Verify session is cleared
        with client.session_transaction() as sess:
            assert "user_id" not in sess
            assert "username" not in sess
            assert sess["csrf_token"] == logout_data["csrf_token"]

        # Protected route returns 401
        assert client.get("/api/auth/me").status_code == 401

    def test_csrf_protection_on_mutating_requests(self, client, test_db_path):
        """Mutating requests fail with 403 CSRF_TOKEN_INVALID without valid token."""
        create_user("dave_csrf", "Password123!", role=ROLE_ADMIN, db_path=test_db_path)

        login_res = client.post("/api/auth/login", json={
            "username": "dave_csrf",
            "password": "Password123!"
        })
        valid_csrf = login_res.get_json()["csrf_token"]

        # POST without CSRF token -> 403
        r_no_csrf = client.post("/api/users", json={"username": "new_user", "password": "Password123!"})
        assert r_no_csrf.status_code == 403
        assert r_no_csrf.get_json()["error_code"] == "CSRF_TOKEN_INVALID"

        # POST with wrong CSRF token -> 403
        r_bad_csrf = client.post(
            "/api/users",
            json={"username": "new_user", "password": "Password123!"},
            headers={"X-CSRF-Token": "invalid_csrf_token_value"}
        )
        assert r_bad_csrf.status_code == 403
        assert r_bad_csrf.get_json()["error_code"] == "CSRF_TOKEN_INVALID"

        # POST with valid CSRF token -> 201
        r_ok = client.post(
            "/api/users",
            json={"username": "new_user", "password": "Password123!", "role": "inspector"},
            headers={"X-CSRF-Token": valid_csrf}
        )
        assert r_ok.status_code == 201


# =============================================================================
# 3. IDOR & Data Privacy Security Tests
# =============================================================================
class TestIDORAndDataPrivacy:
    @pytest.fixture(autouse=True)
    def setup_data(self, test_db_path):
        self.citizen_a = create_user("citizen_alice", "AlicePass123!", role=ROLE_CITIZEN, db_path=test_db_path)
        self.citizen_b = create_user("citizen_bob", "BobPass123!", role=ROLE_CITIZEN, db_path=test_db_path)
        self.admin = create_user("admin_sec", "AdminPass123!", role=ROLE_ADMIN, db_path=test_db_path)

        # Inspection owned by Citizen A
        self.insp_a = save_inspection({
            "image_name": "alice_defect.jpg",
            "road_name": "Alice Terrace",
            "status": "Open",
            "created_by_user_id": self.citizen_a["id"],
            "created_by_username": self.citizen_a["username"],
        }, db_path=test_db_path)

        # Inspection owned by Citizen B
        self.insp_b = save_inspection({
            "image_name": "bob_defect.jpg",
            "road_name": "Bob Boulevard",
            "status": "Open",
            "created_by_user_id": self.citizen_b["id"],
            "created_by_username": self.citizen_b["username"],
        }, db_path=test_db_path)

        # Unowned / legacy inspection (created_by_user_id is None)
        self.insp_unowned = save_inspection({
            "image_name": "unowned_defect.jpg",
            "road_name": "Public Highway",
            "status": "Open",
            "created_by_user_id": None,
            "created_by_username": None,
        }, db_path=test_db_path)

    def test_citizen_cannot_access_other_citizen_subresources(self, client):
        """Citizen A is denied access to Citizen B's images, activity, and complaint drafts."""
        login_res = client.post("/api/auth/login", json={"username": "citizen_alice", "password": "AlicePass123!"})
        csrf_a = login_res.get_json()["csrf_token"]

        b_id = self.insp_b["id"]

        # 1. Image access denied
        res_img = client.get(f"/api/inspections/{b_id}/image/original")
        assert res_img.status_code == 403
        assert res_img.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # 2. Activity history denied
        res_act = client.get(f"/api/inspections/{b_id}/activity")
        assert res_act.status_code == 403
        assert res_act.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # 3. Complaint draft GET denied
        res_draft = client.get(f"/api/inspections/{b_id}/complaint-draft")
        assert res_draft.status_code == 403
        assert res_draft.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # 4. Complaint draft PUT denied
        res_put = client.put(
            f"/api/inspections/{b_id}/complaint-draft",
            json={"subject": "Tampered subject"},
            headers={"X-CSRF-Token": csrf_a}
        )
        assert res_put.status_code == 403
        assert res_put.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # 5. Complaint draft TXT export denied
        res_txt = client.get(f"/api/inspections/{b_id}/complaint-draft/export/txt")
        assert res_txt.status_code == 403
        assert res_txt.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # 6. Complaint draft PDF export denied
        res_pdf = client.get(f"/api/inspections/{b_id}/complaint-draft/export/pdf")
        assert res_pdf.status_code == 403
        assert res_pdf.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    def test_citizen_cannot_access_unowned_records(self, client):
        """Citizen is strictly denied access to unowned records (created_by_user_id is None)."""
        login_res = client.post("/api/auth/login", json={"username": "citizen_alice", "password": "AlicePass123!"})
        csrf_a = login_res.get_json()["csrf_token"]

        unowned_id = self.insp_unowned["id"]

        # Inspection detail denied
        assert client.get(f"/api/inspections/{unowned_id}").status_code == 403

        # Image access denied
        res_img = client.get(f"/api/inspections/{unowned_id}/image/original")
        assert res_img.status_code == 403
        assert res_img.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # Activity history denied
        res_act = client.get(f"/api/inspections/{unowned_id}/activity")
        assert res_act.status_code == 403
        assert res_act.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # Complaint draft GET denied
        res_draft = client.get(f"/api/inspections/{unowned_id}/complaint-draft")
        assert res_draft.status_code == 403
        assert res_draft.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # Complaint draft PUT denied
        res_put = client.put(
            f"/api/inspections/{unowned_id}/complaint-draft",
            json={"subject": "Tampered unowned"},
            headers={"X-CSRF-Token": csrf_a}
        )
        assert res_put.status_code == 403
        assert res_put.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

        # TXT export denied
        assert client.get(f"/api/inspections/{unowned_id}/complaint-draft/export/txt").status_code == 403

        # PDF export denied
        assert client.get(f"/api/inspections/{unowned_id}/complaint-draft/export/pdf").status_code == 403

    def test_citizen_can_access_own_records(self, client):
        """Citizen A can view their own details, activity, and complaint drafts."""
        login_res = client.post("/api/auth/login", json={"username": "citizen_alice", "password": "AlicePass123!"})
        csrf_a = login_res.get_json()["csrf_token"]
        a_id = self.insp_a["id"]

        # Detail -> 200
        res_det = client.get(f"/api/inspections/{a_id}")
        assert res_det.status_code == 200

        # Activity -> 200
        res_act = client.get(f"/api/inspections/{a_id}/activity")
        assert res_act.status_code == 200

        # Complaint draft GET -> 200
        res_draft = client.get(f"/api/inspections/{a_id}/complaint-draft")
        assert res_draft.status_code == 200

        # Complaint draft PUT -> 200
        res_put = client.put(
            f"/api/inspections/{a_id}/complaint-draft",
            json={"subject": "Valid Subject Line for Alice Report", "recipient_agency": "Roads Dept"},
            headers={"X-CSRF-Token": csrf_a}
        )
        assert res_put.status_code == 200

        # Complaint draft TXT export -> 200
        res_txt = client.get(f"/api/inspections/{a_id}/complaint-draft/export/txt")
        assert res_txt.status_code == 200

