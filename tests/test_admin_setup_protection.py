"""
Unit tests for VisionGuard AI first-administrator initialization and existing-administrator protection.
"""

import pytest
from unittest.mock import MagicMock
from app.server import create_app
from database.db import init_db
from database.auth import (
    create_user,
    count_admin_users,
    count_users,
    ROLE_ADMIN,
    ROLE_CITIZEN,
)


@pytest.fixture
def test_db_path(tmp_path):
    p = str(tmp_path / "test_admin_protection.db")
    init_db(p)
    return p


@pytest.fixture
def mock_detector():
    mock = MagicMock()
    mock.is_loaded = True
    mock.load_model.return_value = True
    mock.status_message = "Mock Ready"
    mock.model_path = "models/best.pt"
    return mock


@pytest.fixture
def auth_app(test_db_path, mock_detector):
    app = create_app(
        detector=mock_detector,
        home_detector=mock_detector,
        test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db_path,
            "AUTH_ENABLED": True,
            "ENFORCE_CSRF": False,
            "SECRET_KEY": "test-secret-key-32-chars-minimum-visionguard",
        }
    )
    return app


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


class TestAdminSetupProtection:
    def test_setup_allowed_only_when_no_admin_exists(self, client, test_db_path):
        """Administrator setup is available if and only if no active admin account exists."""
        # 1. Initially 0 admins exist -> requires_setup is True
        status_res = client.get("/api/auth/status")
        assert status_res.status_code == 200
        assert status_res.get_json()["requires_setup"] is True

        # 2. Setup initial admin
        setup_res = client.post("/api/auth/setup-admin", json={
            "username": "primary_admin",
            "password": "SecurePassword123!",
            "email": "admin@visionguard.local"
        })
        assert setup_res.status_code == 201
        assert setup_res.get_json()["user"]["role"] == ROLE_ADMIN
        assert count_admin_users(test_db_path) == 1

        # 3. Status now indicates setup is no longer required
        status_res2 = client.get("/api/auth/status")
        assert status_res2.status_code == 200
        assert status_res2.get_json()["requires_setup"] is False

        # 4. Repeated setup attempt is strictly forbidden (cannot overwrite or create second admin via setup)
        repeat_res = client.post("/api/auth/setup-admin", json={
            "username": "attacker_admin",
            "password": "MaliciousPassword123!",
            "email": "attacker@evil.com"
        })
        assert repeat_res.status_code == 403
        assert repeat_res.get_json()["error_code"] == "SETUP_FORBIDDEN"

        # 5. Overwrite attempt on existing admin username via setup endpoint is also forbidden
        overwrite_res = client.post("/api/auth/setup-admin", json={
            "username": "primary_admin",
            "password": "NewOverwritingPassword123!",
            "email": "overwrite@evil.com"
        })
        assert overwrite_res.status_code == 403
        assert overwrite_res.get_json()["error_code"] == "SETUP_FORBIDDEN"

        # 6. Verify existing admin credentials and state remain intact
        assert count_admin_users(test_db_path) == 1

    def test_citizens_do_not_prevent_admin_setup_if_no_admin_exists(self, client, test_db_path):
        """If citizens register before an admin is configured, admin setup remains available."""
        # Create a citizen first
        create_user("citizen_sam", "CitizenPass123!", role=ROLE_CITIZEN, db_path=test_db_path)
        assert count_users(test_db_path) == 1
        assert count_admin_users(test_db_path) == 0

        # Setup must still be required because no admin exists
        status_res = client.get("/api/auth/status")
        assert status_res.get_json()["requires_setup"] is True

        # Admin setup succeeds
        setup_res = client.post("/api/auth/setup-admin", json={
            "username": "initial_admin",
            "password": "AdminPassword123!",
            "email": "admin@city.gov"
        })
        assert setup_res.status_code == 201
        assert count_admin_users(test_db_path) == 1

    def test_setup_token_enforcement(self, monkeypatch, client, test_db_path):
        """When VISIONGUARD_SETUP_TOKEN is configured, requests without valid token are rejected."""
        monkeypatch.setenv("VISIONGUARD_SETUP_TOKEN", "super-secret-setup-key-42")

        # 1. Missing token -> rejected with 403
        r1 = client.post("/api/auth/setup-admin", json={
            "username": "admin_no_token",
            "password": "Password123!",
        })
        assert r1.status_code == 403
        assert r1.get_json()["error_code"] == "SETUP_TOKEN_INVALID"

        # 2. Invalid token -> rejected with 403
        r2 = client.post("/api/auth/setup-admin", json={
            "username": "admin_bad_token",
            "password": "Password123!",
            "setup_token": "wrong-token"
        })
        assert r2.status_code == 403
        assert r2.get_json()["error_code"] == "SETUP_TOKEN_INVALID"

        # 3. Valid token -> succeeds with 201
        r3 = client.post("/api/auth/setup-admin", json={
            "username": "authorized_admin",
            "password": "AuthorizedPassword123!",
            "setup_token": "super-secret-setup-key-42"
        })
        assert r3.status_code == 201
        assert r3.get_json()["user"]["username"] == "authorized_admin"
        assert count_admin_users(test_db_path) == 1

    def test_production_guard_blocks_unauthorized_public_setup(self, monkeypatch, auth_app, test_db_path):
        """In production mode without setup token, public web setup is rejected with 403."""
        monkeypatch.setenv("VISIONGUARD_ENV", "production")
        monkeypatch.delenv("VISIONGUARD_SETUP_TOKEN", raising=False)
        auth_app.config["TESTING"] = False
        prod_client = auth_app.test_client()

        res = prod_client.post("/api/auth/setup-admin", json={
            "username": "public_visitor",
            "password": "VisitorPassword123!",
        })
        assert res.status_code == 403
        assert res.get_json()["error_code"] == "SETUP_TOKEN_REQUIRED"
        assert count_admin_users(test_db_path) == 0

    def test_server_side_env_admin_bootstrap(self, monkeypatch, test_db_path):
        """Server-side environment variables bootstrap the administrator cleanly."""
        from database.auth import init_admin_from_env
        monkeypatch.setenv("VISIONGUARD_ADMIN_USERNAME", "zeeshanshaikh1")
        monkeypatch.setenv("VISIONGUARD_ADMIN_PASSWORD", "RootPass123!Secure")
        monkeypatch.setenv("VISIONGUARD_ADMIN_EMAIL", "zeeshan@visionguard.gov")

        admin = init_admin_from_env(db_path=test_db_path)
        assert admin is not None
        assert admin["username"] == "zeeshanshaikh1"
        assert admin["role"] == ROLE_ADMIN
        assert count_admin_users(test_db_path) == 1

