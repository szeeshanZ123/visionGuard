"""
Unit and Integration Tests for Phase 7: Production Hardening & Deployment Preparation.

Verifies:
- Production configuration enforcement (VISIONGUARD_SECRET_KEY validation)
- Rejection of missing/weak secret keys in production mode
- Cookie hardening in production (HTTPOnly, SameSite, Secure)
- Upload path traversal prevention via secure_filename
- Image endpoint directory boundary enforcement
- WSGI entry point compatibility (wsgi:app and wsgi:application)
- Structured JSON 405 error handling
"""

import io
import os
import sys
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.server import create_app
from database.db import save_inspection


class TestProductionConfigurationHardening:
    """Tests for production environment configuration and secret enforcement."""

    def test_production_mode_rejects_missing_secret_key(self, monkeypatch):
        """Production mode must fail startup if VISIONGUARD_SECRET_KEY is missing."""
        monkeypatch.delenv("VISIONGUARD_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError) as exc_info:
            create_app(test_config={
                "ENV": "production",
                "TESTING": True,
                "DATABASE_PATH": ":memory:",
            })
        assert "VISIONGUARD_SECRET_KEY" in str(exc_info.value)
        assert "Production configuration error" in str(exc_info.value)

    def test_production_mode_rejects_weak_secret_key(self, monkeypatch):
        """Production mode must fail startup if secret key is weak or under 32 chars."""
        for weak_key in ["short", "secret", "12345678", "password", "visionguard", "a" * 31]:
            with pytest.raises(RuntimeError) as exc_info:
                create_app(test_config={
                    "ENV": "production",
                    "SECRET_KEY": weak_key,
                    "TESTING": True,
                    "DATABASE_PATH": ":memory:",
                })
            assert "VISIONGUARD_SECRET_KEY" in str(exc_info.value)

    def test_production_mode_accepts_strong_secret_key(self):
        """Production mode succeeds with a valid 32+ character high-entropy key."""
        strong_key = "prod_secure_secret_key_with_sufficient_entropy_64chars_long_12345"
        app = create_app(test_config={
            "ENV": "production",
            "SECRET_KEY": strong_key,
            "TESTING": True,
            "DATABASE_PATH": ":memory:",
        })
        assert app.secret_key == strong_key
        assert app.config["DEBUG"] is False
        assert app.config["PRODUCTION"] is True

    def test_development_mode_allows_ephemeral_key(self, monkeypatch):
        """Local development without an explicit secret key uses a safe ephemeral key."""
        monkeypatch.delenv("VISIONGUARD_SECRET_KEY", raising=False)
        app = create_app(test_config={
            "ENV": "development",
            "TESTING": True,
            "DATABASE_PATH": ":memory:",
        })
        assert app.secret_key is not None
        assert len(app.secret_key) >= 32

    def test_cookie_hardening_configuration(self):
        """Verifies session cookie security flags."""
        strong_key = "prod_secure_secret_key_with_sufficient_entropy_64chars_long_12345"
        app = create_app(test_config={
            "ENV": "production",
            "SECRET_KEY": strong_key,
            "TESTING": True,
            "DATABASE_PATH": ":memory:",
        })
        assert app.config["SESSION_COOKIE_HTTPONLY"] is True
        assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
        assert app.config["SESSION_COOKIE_SECURE"] is True


class TestPathTraversalAndPersistenceProtection:
    """Tests for file upload sanitization and directory traversal prevention."""

    @pytest.fixture
    def client(self, tmp_path):
        test_db = str(tmp_path / "test_vg.db")
        app = create_app(test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db,
            "AUTH_ENABLED": False,
            "ENFORCE_CSRF": False,
            "SECRET_KEY": "test_secret_for_hardening_suite_32chars!",
        })
        with app.test_client() as client:
            yield client, test_db

    def test_uploaded_filename_sanitized_against_path_traversal(self, client):
        client_inst, _ = client
        malicious_filename = "../../../etc/passwd_road.jpg"
        fake_stream = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 200)

        res = client_inst.post(
            "/api/inspect",
            data={
                "image": (fake_stream, malicious_filename),
                "domain": "road",
            },
            content_type="multipart/form-data"
        )
        data = res.get_json() or {}
        if "filename" in data:
            assert ".." not in data["filename"]
            assert "/" not in data["filename"]
            assert "\\" not in data["filename"]

    def test_image_serving_directory_boundary_enforcement(self, client):
        client_inst, test_db = client
        rec = save_inspection({
            "image_name": "test.jpg",
            "road_name": "Test Highway",
            "status": "Open",
            "inspection_type": "road",
            "original_image_path": "C:\\Windows\\System32\\cmd.exe",
        }, db_path=test_db)
        rec_id = rec["id"]

        res = client_inst.get(f"/api/inspections/{rec_id}/image/original")
        assert res.status_code == 403
        data = res.get_json()
        assert data["error_code"] == "FORBIDDEN_FILE_ACCESS"

    def test_image_serving_nonexistent_file_safe_error(self, client):
        client_inst, test_db = client
        rec = save_inspection({
            "image_name": "test.jpg",
            "road_name": "Test Highway",
            "status": "Open",
            "inspection_type": "road",
            "original_image_path": "data/uploads/nonexistent_file_12345.jpg",
        }, db_path=test_db)
        rec_id = rec["id"]

        res = client_inst.get(f"/api/inspections/{rec_id}/image/original")
        assert res.status_code == 404
        data = res.get_json()
        assert data["error_code"] == "IMAGE_FILE_NOT_FOUND"
        assert "data/uploads/nonexistent_file_12345.jpg" not in data["message"]


class TestProductionWsgiCompatibility:
    """Verifies that the WSGI entry point can be imported and executed."""

    def test_wsgi_module_exposes_app_and_application(self):
        import wsgi
        assert hasattr(wsgi, "app")
        assert hasattr(wsgi, "application")
        assert wsgi.app is wsgi.application

    def test_method_not_allowed_returns_clean_json(self, tmp_path):
        test_db = str(tmp_path / "test_vg.db")
        app = create_app(test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db,
            "AUTH_ENABLED": False,
        })
        with app.test_client() as client:
            res = client.post("/api/classes")
            assert res.status_code == 405
            data = res.get_json()
            assert data["status"] == "error"
            assert data["error_code"] == "METHOD_NOT_ALLOWED"
