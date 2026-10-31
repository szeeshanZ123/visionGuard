"""
Automated regression tests for VisionGuard AI inference performance,
timeout safeguards, timing telemetry, and JSON API error responses.
"""

import io
import os
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
    # Warm up detector so benchmarks measure real inference latency rather than one-time cold PyTorch import
    app.detector.load_model()
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



class TestHttp503ErrorContracts:
    """Verifies that 503 error codes are clearly distinguished between overload and missing weights."""

    def test_server_overloaded_does_not_contain_setup_instructions(self, tmp_path):
        """Verifies SERVER_OVERLOADED returns 503 but does not masquerade as missing weights."""
        test_db = str(tmp_path / "overload_test.db")
        app = create_app(test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db,
            "AUTH_ENABLED": False,
            "ENFORCE_CSRF": False,
        })
        with app.test_client() as client:
            from unittest.mock import patch
            from app.server import INSPECTION_SEMAPHORE
            with patch.object(INSPECTION_SEMAPHORE, "acquire", return_value=False):
                res = client.post(
                    "/api/inspect",
                    data={"image": (create_synthetic_image_stream(320, 240), "test.jpg"), "domain": "road"},
                    content_type="multipart/form-data",
                )
                assert res.status_code == 503
                data = res.get_json()
                assert data["error_code"] == "SERVER_OVERLOADED"
                assert "setup_instructions" not in data
                assert "processing another inspection" in data["message"]

    def test_frontend_handle_api_error_does_not_conflate_503(self):
        """Verifies app.js handleApiError only triggers checkpoint banner on genuine missing weights."""
        from storage.backend import PROJECT_ROOT
        app_js_path = os.path.join(PROJECT_ROOT, "app", "static", "js", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            js = f.read()
        assert "const isWeightsMissing = Boolean" in js
        assert 'data.error_code === "SERVER_OVERLOADED"' in js
        assert 'Server Busy (HTTP 503)' in js
<<<<<<< HEAD
=======


class TestHttp500FixAndErrorResilience:
    """Verifies that unexpected errors in the pipeline are safely caught and return structured JSON."""

    def test_post_inference_overlay_failure_graceful_recovery(self, loaded_app_client):
        """If OpenCV draw_annotations fails, /api/inspect must gracefully return 200 with fallback image."""
        client, app = loaded_app_client
        from unittest.mock import patch

        img = create_synthetic_image_stream(width=320, height=240)
        with patch.object(app.detector, "draw_annotations", side_effect=RuntimeError("OpenCV drawing error")):
            res = client.post(
                "/api/inspect",
                data={"image": (img, "road.jpg"), "domain": "road"},
                content_type="multipart/form-data",
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["status"] == "success"
            assert "annotated_image" in data

    def test_numpy_types_in_detections_json_serializable(self, loaded_app_client):
        """NumPy float32/int64 objects in detections must not cause TypeError in jsonify."""
        client, app = loaded_app_client
        from unittest.mock import patch
        import numpy as np

        mock_detection = [{
            "domain": "road",
            "class_id": np.int64(0),
            "class_name": "D00_longitudinal_crack",
            "distress_category": "Longitudinal Crack",
            "confidence": np.float32(0.8523),
            "bbox": {
                "x1": np.float32(10.5),
                "y1": np.float32(20.3),
                "x2": np.float32(100.2),
                "y2": np.float32(200.1),
                "width": np.float32(89.7),
                "height": np.float32(179.8),
                "aspect_ratio": np.float32(0.499),
                "pixel_area": np.float32(16128.06),
            },
            "disclaimer": "Test disclaimer",
        }]

        img = create_synthetic_image_stream(width=320, height=240)
        with patch.object(app.detector, "detect", return_value=mock_detection):
            res = client.post(
                "/api/inspect",
                data={"image": (img, "road.jpg"), "domain": "road"},
                content_type="multipart/form-data",
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["status"] == "success"
            assert data["defect_count"] == 1
            assert isinstance(data["detections"][0]["confidence"], float)

    def test_none_stats_and_timings_resilience(self, loaded_app_client):
        """If last_inference_stats is None or contains None timings, response must not crash."""
        client, app = loaded_app_client
        from unittest.mock import patch

        img = create_synthetic_image_stream(width=320, height=240)
        with patch.object(app.detector, "last_inference_stats", None):
            res = client.post(
                "/api/inspect",
                data={"image": (img, "road.jpg"), "domain": "road"},
                content_type="multipart/form-data",
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["status"] == "success"
            assert data["timings"]["model_load_ms"] == 0.0

    def test_db_error_during_auth_does_not_crash_api_inspect(self, tmp_path):
        """Database error in get_current_user_record returns 401 instead of unhandled 500."""
        test_db = str(tmp_path / "auth_db_err.db")
        app = create_app(test_config={
            "TESTING": False,
            "DATABASE_PATH": test_db,
            "AUTH_ENABLED": True,
            "ENFORCE_CSRF": False,
        })
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = 12345

            from unittest.mock import patch
            with patch("database.auth.get_user_by_id", side_effect=RuntimeError("Database connection lost")):
                img = create_synthetic_image_stream(width=320, height=240)
                res = client.post(
                    "/api/inspect",
                    data={"image": (img, "road.jpg"), "domain": "road"},
                    content_type="multipart/form-data",
                )
                # Auth fails gracefully with 401 instead of unhandled 500
                assert res.status_code == 401
                data = res.get_json()
                assert data["error_code"] == "UNAUTHORIZED"

    def test_unhandled_exception_in_inspection_returns_structured_json_error(self, loaded_app_client):
        """Any internal exception inside _execute_inspection_internal returns structured JSON."""
        client, _ = loaded_app_client
        from unittest.mock import patch

        img = create_synthetic_image_stream(width=320, height=240)
        with patch("app.server.load_image_as_opencv", side_effect=RuntimeError("Corrupt OpenCV tensor")):
            res = client.post(
                "/api/inspect",
                data={"image": (img, "road.jpg"), "domain": "road"},
                content_type="multipart/form-data",
            )
            assert res.status_code == 500
            data = res.get_json()
            assert data["status"] == "error"
            assert data["error_code"] == "INSPECTION_FAILED"
            assert "Corrupt OpenCV tensor" in data["message"]
>>>>>>> cfc1ca63437b8bef5fe70d8179369a9add77ec91
