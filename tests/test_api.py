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
