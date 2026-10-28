"""
Automated regression tests for VisionGuard AI inference performance,
timeout safeguards, timing telemetry, and JSON API error responses.
"""

import io
import time
import cv2
import numpy as np
import pytest

from app.server import create_app
from ai.detection.detector import DefectDetectionService


@pytest.fixture
def loaded_app_client(tmp_path):
    """Test client configured with loaded real detectors and test database."""
    test_db = str(tmp_path / "perf_test.db")
    app = create_app(test_config={
        "TESTING": True,
        "DATABASE_PATH": test_db,
        "AUTH_ENABLED": False,
        "ENFORCE_CSRF": False,
    })
    with app.test_client() as client:
        yield client, app


def create_synthetic_image_stream(width=640, height=480, noise=True):
    """Generates an in-memory JPEG byte stream for benchmarking."""
    if noise:
        img = np.random.randint(50, 200, (height, width, 3), dtype=np.uint8)
    else:
        img = np.full((height, width, 3), 128, dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return io.BytesIO(buf.tobytes())


class TestInferencePerformanceAndTiming:
    """Verifies that CPU inference is optimized and completes well within the timeout threshold."""

    def test_standard_inference_performance_under_3_seconds(self, loaded_app_client):
        """Standard mode on 1080p image must complete in < 3.0s on CPU (preventing 60s timeout)."""
        client, _ = loaded_app_client
        img_stream = create_synthetic_image_stream(width=1920, height=1080)

        t0 = time.perf_counter()
        res = client.post(
            "/api/inspect",
            data={
                "image": (img_stream, "test_1080p.jpg"),
                "confidence_threshold": "0.25",
                "inspection_mode": "standard",
                "domain": "road",
            },
            content_type="multipart/form-data",
        )
        elapsed = time.perf_counter() - t0

        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "timings" in data
        assert "inference_ms" in data["timings"]
        assert "total_ms" in data["timings"]

        # Inference must complete in under 3.0 seconds (well below 60s / 90s SLA)
        assert elapsed < 3.0, f"Standard inference took {elapsed:.2f}s, expected < 3.0s"

    def test_tiled_inference_performance_under_5_seconds(self, loaded_app_client):
        """Tiled mode on high-res image must complete in < 5.0s on CPU."""
        client, _ = loaded_app_client
        img_stream = create_synthetic_image_stream(width=1600, height=1200)

        t0 = time.perf_counter()
        res = client.post(
            "/api/inspect",
            data={
                "image": (img_stream, "test_tiled.jpg"),
                "confidence_threshold": "0.25",
                "inspection_mode": "tiled",
                "domain": "home",
            },
            content_type="multipart/form-data",
        )
        elapsed = time.perf_counter() - t0

        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["inspection_mode"] == "tiled"
        assert "timings" in data
        assert elapsed < 5.0, f"Tiled inference took {elapsed:.2f}s, expected < 5.0s"

    def test_models_loaded_once_per_worker(self, loaded_app_client):
        """Verifies that model detectors are loaded once on startup and reused across requests."""
        client, app = loaded_app_client
        assert app.detector.is_loaded is True
        assert app.home_detector.is_loaded is True

        # Run two consecutive inspect requests
        img1 = create_synthetic_image_stream(width=320, height=240)
        res1 = client.post("/api/inspect", data={"image": (img1, "i1.jpg")}, content_type="multipart/form-data")
        assert res1.status_code == 200

        img2 = create_synthetic_image_stream(width=320, height=240)
        res2 = client.post("/api/inspect", data={"image": (img2, "i2.jpg")}, content_type="multipart/form-data")
        assert res2.status_code == 200

        # Model instance identity is preserved (no reloads)
        assert app.detector.is_loaded is True


class TestJsonApiErrorResponses:
    """Verifies that all API error conditions return structured JSON instead of HTML."""

    def test_missing_image_payload_returns_json_400(self, loaded_app_client):
        """Missing image file in multipart body returns JSON 400."""
        client, _ = loaded_app_client
        res = client.post("/api/inspect", data={}, content_type="multipart/form-data")
        assert res.status_code == 400
        data = res.get_json()
        assert data["status"] == "error"
        assert data["error_code"] == "NO_FILE_UPLOADED"
        assert "message" in data

    def test_invalid_extension_returns_json_400(self, loaded_app_client):
        """Unsupported file extension returns JSON 400."""
        client, _ = loaded_app_client
        bad_stream = io.BytesIO(b"fake executable content")
        res = client.post(
            "/api/inspect",
            data={"image": (bad_stream, "malware.exe")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 400
        data = res.get_json()
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_IMAGE"

    def test_invalid_domain_returns_json_400(self, loaded_app_client):
        """Unsupported inspection domain returns JSON 400."""
        client, _ = loaded_app_client
        img = create_synthetic_image_stream(width=320, height=240)
        res = client.post(
            "/api/inspect",
            data={"image": (img, "road.jpg"), "domain": "underwater"},
            content_type="multipart/form-data",
        )
        assert res.status_code == 400
        data = res.get_json()
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_DOMAIN"

    def test_missing_weights_returns_json_503(self, tmp_path):
        """Unloaded model weights returns JSON 503 with setup instructions."""
        test_db = str(tmp_path / "weights_test.db")
        unloaded_detector = DefectDetectionService(model_path="nonexistent.pt")
        app = create_app(
            detector=unloaded_detector,
            home_detector=unloaded_detector,
            test_config={"TESTING": True, "DATABASE_PATH": test_db, "AUTH_ENABLED": False, "ENFORCE_CSRF": False}
        )
        client = app.test_client()
        img = create_synthetic_image_stream(width=320, height=240)
        res = client.post(
            "/api/inspect",
            data={"image": (img, "road.jpg")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 503
        data = res.get_json()
        assert data["status"] == "error"
        assert data["error_code"] == "MODEL_WEIGHTS_MISSING"
        assert "setup_instructions" in data

    def test_api_not_found_returns_json_404(self, loaded_app_client):
        """Non-existent /api/ endpoint returns structured JSON 404."""
        client, _ = loaded_app_client
        res = client.get("/api/nonexistent-endpoint")
        assert res.status_code == 404
        data = res.get_json()
        assert data["status"] == "error"
        assert data["error_code"] == "NOT_FOUND"

    def test_api_method_not_allowed_returns_json_405(self, loaded_app_client):
        """Calling GET on POST-only /api/inspect returns JSON 405."""
        client, _ = loaded_app_client
        res = client.get("/api/inspect")
        assert res.status_code == 405
        data = res.get_json()
        assert data["status"] == "error"
        assert data["error_code"] == "METHOD_NOT_ALLOWED"

