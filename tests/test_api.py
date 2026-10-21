"""
Integration and API tests for VisionGuard AI Flask backend.

Covers requirement 10:
- Missing model weights (HTTP 503)
- Invalid images (HTTP 400): unsupported extensions, empty files, corrupt streams, missing payload
- File-size limits (HTTP 400/413)
- Empty detections on sound roadway (HTTP 200)
- Successful inference and response contract (HTTP 200)
- Health and class endpoints
"""

import io
import os
from pathlib import Path
import numpy as np
import pytest

from app.server import create_app
from ai.detection.detector import DefectDetectionService


@pytest.fixture
def client_with_missing_weights():
    """Flask test client configured with a nonexistent checkpoint."""
    detector = DefectDetectionService(model_path="nonexistent_checkpoint.pt")
    app = create_app(detector=detector, test_config={"TESTING": True})
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_road_bytes():
    """Reads the real sample road image asset from data/sample_road.jpg."""
    road_path = Path(__file__).parent.parent / "data" / "sample_road.jpg"
    with open(road_path, "rb") as f:
        return f.read()


class MockLoadedDetector(DefectDetectionService):
    """Subclass of DefectDetectionService simulating a loaded model for deterministic testing."""

    def __init__(self, mock_detections=None):
        super().__init__(model_path="ai/models/best.pt")
        self.is_loaded = True
        self.status_message = "Mock loaded for testing"
        self.mock_detections = mock_detections if mock_detections is not None else []

    def detect(self, image_bgr, conf_threshold=0.25, raise_if_unloaded=False):
        return self.mock_detections


@pytest.fixture
def client_with_empty_detections():
    """Client where model is loaded and detects 0 defects (sound road)."""
    detector = MockLoadedDetector(mock_detections=[])
    app = create_app(detector=detector, test_config={"TESTING": True})
    with app.test_client() as client:
        yield client


@pytest.fixture
def client_with_mock_detections():
    """Client where model is loaded and returns authentic-schema defect detections."""
    detections = [
        {
            "class_id": 3,
            "class_name": "D40_pothole",
            "distress_category": "Pothole",
            "confidence": 0.8654,
            "bbox": {
                "x1": 150.0,
                "y1": 200.0,
                "x2": 350.0,
                "y2": 420.0,
                "width": 200.0,
                "height": 220.0,
                "aspect_ratio": 0.909,
                "pixel_area": 44000.0,
            },
            "disclaimer": "Detection confidence is statistical likelihood, not pavement structural safety.",
        }
    ]
    detector = MockLoadedDetector(mock_detections=detections)
    app = create_app(detector=detector, test_config={"TESTING": True})
    with app.test_client() as client:
        yield client


# =============================================================================
# Tests
# =============================================================================

def test_api_health_endpoint(client_with_missing_weights):
    """Verifies GET /api/health reports system status."""
    res = client_with_missing_weights.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert "database" in data
    assert "model" in data
    assert data["model"]["loaded"] is False
    assert len(data["model"]["supported_classes"]) == 4


def test_api_classes_endpoint(client_with_missing_weights):
    """Verifies GET /api/classes lists the 4 target distress classes."""
    res = client_with_missing_weights.get("/api/classes")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    class_names = [c["class_name"] for c in data["classes"]]
    assert "D00_longitudinal_crack" in class_names
    assert "D10_transverse_crack" in class_names
    assert "D20_alligator_crack" in class_names
    assert "D40_pothole" in class_names


def test_api_index_serves_html(client_with_missing_weights):
    """Verifies GET / renders the HTML interface."""
    res = client_with_missing_weights.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "VisionGuard AI" in html
    assert "Infrastructure Defect Detection" in html
    assert "Original Road Image" in html
    assert "Authentic AI Detection Overlay" in html


def test_inspect_missing_payload(client_with_missing_weights):
    """Verifies POST /api/inspect returns 400 when no file is uploaded."""
    res = client_with_missing_weights.post("/api/inspect", data={})
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert data["error_code"] == "NO_FILE_UPLOADED"


def test_inspect_unsupported_extension(client_with_missing_weights):
    """Verifies POST /api/inspect returns 400 for unsupported file formats."""
    data = {
        "image": (io.BytesIO(b"Hello world"), "test.txt"),
    }
    res = client_with_missing_weights.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    res_data = res.get_json()
    assert res_data["status"] == "error"
    assert res_data["error_code"] == "INVALID_IMAGE"
    assert "unsupported" in res_data["message"].lower()


def test_inspect_empty_file(client_with_missing_weights):
    """Verifies POST /api/inspect returns 400 for empty 0-byte files."""
    data = {
        "image": (io.BytesIO(b""), "empty.jpg"),
    }
    res = client_with_missing_weights.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    res_data = res.get_json()
    assert res_data["status"] == "error"
    assert "empty" in res_data["message"].lower()


def test_inspect_corrupt_file(client_with_missing_weights):
    """Verifies POST /api/inspect returns 400 for corrupted image byte stream."""
    data = {
        "image": (io.BytesIO(b"\xFF\xD8\xFF\xE0corruptbyteshere"), "corrupt.jpg"),
    }
    res = client_with_missing_weights.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    res_data = res.get_json()
    assert res_data["status"] == "error"
    assert "corrupted" in res_data["message"].lower() or "invalid" in res_data["message"].lower()


def test_inspect_oversized_file(client_with_missing_weights):
    """Verifies oversized files (> 15 MB limit) are rejected."""
    # Create app with small 0.01 MB limit for fast testing
    app = create_app(
        detector=DefectDetectionService(model_path="nonexistent.pt"),
        test_config={"TESTING": True, "MAX_CONTENT_LENGTH_MB": 0.01},
    )
    with app.test_client() as client:
        oversized_bytes = b"X" * int(0.02 * 1024 * 1024)
        data = {"image": (io.BytesIO(oversized_bytes), "large.jpg")}
        res = client.post("/api/inspect", data=data, content_type="multipart/form-data")
        assert res.status_code in [400, 413]
        res_data = res.get_json()
        assert res_data["status"] == "error"


def test_inspect_missing_model_weights_returns_503(client_with_missing_weights, sample_road_bytes):
    """Verifies POST /api/inspect returns HTTP 503 with actionable setup steps when best.pt is absent."""
    data = {
        "image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"),
    }
    res = client_with_missing_weights.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 503
    res_data = res.get_json()
    assert res_data["status"] == "error"
    assert res_data["error_code"] == "MODEL_WEIGHTS_MISSING"
    assert "not present" in res_data["message"].lower()
    assert "setup_instructions" in res_data
    assert "best.pt" in res_data["setup_instructions"]


def test_inspect_empty_detections_on_sound_road(client_with_empty_detections, sample_road_bytes):
    """Verifies that an image without defects returns 200, 0 detections, and genuine unadulterated overlay."""
    data = {
        "image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"),
        "confidence_threshold": "0.30",
    }
    res = client_with_empty_detections.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["status"] == "success"
    assert res_data["filename"] == "sample_road.jpg"
    assert res_data["defect_count"] == 0
    assert res_data["detections"] == []
    assert res_data["annotated_image"].startswith("data:image/jpeg;base64,")
    assert "disclaimer" in res_data
    # Confidence separate from structural safety
    assert "statistical likelihood" in res_data["disclaimer"].lower()


def test_inspect_successful_inference_contract(client_with_mock_detections, sample_road_bytes):
    """Verifies response schema, bounding coordinates, dimensions, and confidence values."""
    data = {
        "image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"),
        "confidence_threshold": "0.25",
    }
    res = client_with_mock_detections.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["status"] == "success"
    assert res_data["defect_count"] == 1
    assert len(res_data["detections"]) == 1

    det = res_data["detections"][0]
    assert det["class_id"] == 3
    assert det["class_name"] == "D40_pothole"
    assert det["distress_category"] == "Pothole"
    assert 0.0 <= det["confidence"] <= 1.0

    bbox = det["bbox"]
    assert all(k in bbox for k in ["x1", "y1", "x2", "y2", "width", "height", "aspect_ratio", "pixel_area"])
    assert bbox["x2"] > bbox["x1"]
    assert bbox["y2"] > bbox["y1"]
    assert bbox["width"] == bbox["x2"] - bbox["x1"]
    assert bbox["height"] == bbox["y2"] - bbox["y1"]


def test_inspect_inference_failure_returns_500_json(sample_road_bytes):
    """Verifies that if an unexpected error occurs during inference, the server returns structured JSON with HTTP 500."""
    class FailingDetector(DefectDetectionService):
        def __init__(self):
            super().__init__(model_path="ai/models/best.pt")
            self.is_loaded = True
            self.status_message = "Loaded"

        def detect(self, image_bgr, conf_threshold=0.25, raise_if_unloaded=False):
            raise RuntimeError("Simulated internal neural network layer failure")

    failing_app = create_app(detector=FailingDetector(), test_config={"TESTING": True})
    with failing_app.test_client() as client:
        data = {
            "image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"),
        }
        res = client.post("/api/inspect", data=data, content_type="multipart/form-data")
        assert res.status_code == 500
        res_data = res.get_json()
        assert res_data["status"] == "error"
        assert res_data["error_code"] == "INFERENCE_FAILED"
        assert "Simulated internal neural network" in res_data["message"]


def test_inspect_with_real_best_pt_checkpoint(sample_road_bytes):
    """Verifies real inference when ai/models/best.pt is available on disk."""
    real_weights_path = Path(__file__).parent.parent / "ai" / "models" / "best.pt"
    if not real_weights_path.exists():
        pytest.skip("ai/models/best.pt not present; skipping real weights test")

    real_detector = DefectDetectionService(model_path=str(real_weights_path))
    assert real_detector.is_loaded is True

    app = create_app(detector=real_detector, test_config={"TESTING": True})
    with app.test_client() as client:
        data = {
            "image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"),
            "confidence_threshold": "0.25",
        }
        res = client.post("/api/inspect", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        res_data = res.get_json()
        assert res_data["status"] == "success"
        assert res_data["filename"] == "sample_road.jpg"
        assert res_data["confidence_threshold"] == 0.25
        assert res_data["model_info"]["checkpoint_path"] == str(real_weights_path)
        assert isinstance(res_data["detections"], list)
        assert res_data["defect_count"] == len(res_data["detections"])
        assert res_data["annotated_image"].startswith("data:image/jpeg;base64,")


def test_inspect_threshold_propagation_and_clamping(sample_road_bytes):
    """Verifies that confidence_threshold is correctly passed, parsed, clamped, and echoed back."""
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as client:
        # Case 1: Custom valid threshold = 0.10
        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"), "confidence_threshold": "0.10"},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        assert res.get_json()["confidence_threshold"] == 0.10

        # Case 2: Minimum clamp = 0.05 when 0.01 provided
        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"), "confidence_threshold": "0.01"},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        assert res.get_json()["confidence_threshold"] == 0.05

        # Case 3: Maximum clamp = 0.95 when 0.99 provided
        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"), "confidence_threshold": "0.99"},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        assert res.get_json()["confidence_threshold"] == 0.95

        # Case 4: Default fallback = 0.25 when invalid string provided
        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"), "confidence_threshold": "invalid"},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        assert res.get_json()["confidence_threshold"] == 0.25


def test_inspect_empty_predictions_consistency(sample_road_bytes):
    """Verifies that an image with zero detections returns a consistent, complete payload."""
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as client:
        # Request at high threshold 0.90
        res = client.post(
            "/api/inspect",
            data={"image": (io.BytesIO(sample_road_bytes), "sample_road.jpg"), "confidence_threshold": "0.90"},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["confidence_threshold"] == 0.90
        assert data["defect_count"] == 0
        assert data["detections"] == []
        assert data["annotated_image"].startswith("data:image/jpeg;base64,")
        assert "Notice:" in data["disclaimer"]

