"""
Unit and integration tests for Sliced / Tiled Inference in ai/detection/slicer.py
and its integration into DefectDetectionService and Flask API.
"""

import io
import cv2
import numpy as np
import pytest

from ai.detection.slicer import (
    compute_iou,
    apply_nms,
    SlicedInferenceEngine,
)
from ai.detection.detector import DefectDetectionService
from app.server import create_app


# ---------------------------------------------------------
# Unit Tests for Geometry and Math Helpers
# ---------------------------------------------------------

def test_compute_iou_identical():
    """Identical bounding boxes must have IoU == 1.0."""
    box = {"x1": 10.0, "y1": 20.0, "x2": 60.0, "y2": 70.0}
    iou = compute_iou(box, box)
    assert pytest.approx(iou, rel=1e-4) == 1.0


def test_compute_iou_disjoint():
    """Completely disjoint bounding boxes must have IoU == 0.0."""
    box1 = {"x1": 0.0, "y1": 0.0, "x2": 50.0, "y2": 50.0}
    box2 = {"x1": 60.0, "y1": 60.0, "x2": 100.0, "y2": 100.0}
    assert compute_iou(box1, box2) == 0.0


def test_compute_iou_partial_overlap():
    """Boxes with known overlap must calculate exact mathematical ratio."""
    # box1: 100x100 = 10000
    box1 = {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 100.0}
    # box2: shifted by 50px in x -> intersection: 50x100 = 5000
    # union: 10000 + 10000 - 5000 = 15000 -> IoU = 5000/15000 = 1/3
    box2 = {"x1": 50.0, "y1": 0.0, "x2": 150.0, "y2": 100.0}
    expected_iou = 5000.0 / 15000.0
    assert pytest.approx(compute_iou(box1, box2), rel=1e-4) == expected_iou


def test_compute_iou_zero_area():
    """Degenerate zero-area bounding boxes must return 0.0 without division by zero."""
    box1 = {"x1": 10.0, "y1": 10.0, "x2": 10.0, "y2": 10.0}
    box2 = {"x1": 10.0, "y1": 10.0, "x2": 50.0, "y2": 50.0}
    assert compute_iou(box1, box2) == 0.0


# ---------------------------------------------------------
# Unit Tests for Non-Maximum Suppression (NMS)
# ---------------------------------------------------------

def test_apply_nms_empty():
    """Empty list returns empty list."""
    assert apply_nms([]) == []


def test_apply_nms_single():
    """Single detection is retained unchanged."""
    det = {
        "class_id": 0,
        "confidence": 0.85,
        "bbox": {"x1": 10.0, "y1": 10.0, "x2": 50.0, "y2": 50.0},
    }
    result = apply_nms([det])
    assert len(result) == 1
    assert result[0] == det


def test_apply_nms_suppresses_same_class_overlap():
    """Lower-confidence box of the same class overlapping above threshold is suppressed."""
    high_conf = {
        "class_id": 0,
        "confidence": 0.90,
        "bbox": {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 100.0},
    }
    low_conf = {
        "class_id": 0,
        "confidence": 0.60,
        "bbox": {"x1": 10.0, "y1": 10.0, "x2": 105.0, "y2": 105.0},
    }
    kept = apply_nms([low_conf, high_conf], iou_threshold=0.40)
    assert len(kept) == 1
    assert kept[0]["confidence"] == 0.90


def test_apply_nms_preserves_different_classes():
    """Boxes of different classes overlapping in the same area are both preserved."""
    pothole = {
        "class_id": 3,
        "confidence": 0.75,
        "bbox": {"x1": 50.0, "y1": 50.0, "x2": 150.0, "y2": 150.0},
    }
    crack = {
        "class_id": 0,
        "confidence": 0.70,
        "bbox": {"x1": 50.0, "y1": 50.0, "x2": 150.0, "y2": 150.0},
    }
    kept = apply_nms([pothole, crack], iou_threshold=0.40)
    assert len(kept) == 2
    class_ids = {d["class_id"] for d in kept}
    assert class_ids == {0, 3}


# ---------------------------------------------------------
# Unit Tests for Tile Coordinate Generation
# ---------------------------------------------------------

def test_calculate_slices_smaller_than_slice_size():
    """When the image is smaller than the tile size, returns a single slice matching image bounds."""
    slicer = SlicedInferenceEngine(slice_size=480, overlap_ratio=0.20)
    slices = slicer.calculate_slices(img_w=300, img_h=200)
    assert len(slices) == 1
    assert slices[0] == (0, 0, 300, 200)


def test_calculate_slices_covers_entire_image():
    """All generated slices must stay within bounds and collectively cover every pixel."""
    slicer = SlicedInferenceEngine(slice_size=384, overlap_ratio=0.20)
    w, h = 800, 600
    slices = slicer.calculate_slices(img_w=w, img_h=h)

    assert len(slices) > 1

    mask = np.zeros((h, w), dtype=np.uint8)
    for (x1, y1, x2, y2) in slices:
        assert 0 <= x1 < x2 <= w
        assert 0 <= y1 < y2 <= h
        mask[y1:y2, x1:x2] = 1

    # Every pixel must be covered (mask has no zeros)
    assert np.all(mask == 1)


# ---------------------------------------------------------
# Integration Tests: DefectDetectionService + Slicer
# ---------------------------------------------------------

def test_detector_detect_sliced_unloaded():
    """detect_sliced handles missing model gracefully without crashing."""
    detector = DefectDetectionService(model_path="nonexistent.pt")
    assert detector.is_loaded is False

    blank_img = np.zeros((600, 800, 3), dtype=np.uint8)
    res = detector.detect_sliced(blank_img)
    assert res == []

    with pytest.raises(FileNotFoundError):
        detector.detect_sliced(blank_img, raise_if_unloaded=True)


def test_detector_detect_tiled_mode_routing():
    """Calling detector.detect with inspection_mode='tiled' routes to detect_sliced."""
    detector = DefectDetectionService(model_path="nonexistent.pt")
    blank_img = np.zeros((400, 400, 3), dtype=np.uint8)

    # With model unloaded, returns [] safely
    res_std = detector.detect(blank_img, inspection_mode="standard")
    res_tiled = detector.detect(blank_img, inspection_mode="tiled")

    assert res_std == []
    assert res_tiled == []


def test_sliced_coordinate_shifting_with_mock_detector():
    """Verify that tile bounding boxes are properly shifted by tile offsets (x_min, y_min)."""
    class MockDetector:
        def __init__(self):
            self.last_inference_stats = {"raw_candidate_count": 1, "top_raw_confidence": 0.88, "top_raw_class": "Crack"}

        def _detect_standard(self, tile, conf_threshold=0.25, raise_if_unloaded=False):
            # Return a relative bbox [10, 15, 60, 85] on every tile
            return [{
                "class_id": 0,
                "class_name": "D00_longitudinal_crack",
                "distress_category": "Longitudinal Crack",
                "confidence": 0.88,
                "bbox": {"x1": 10.0, "y1": 15.0, "x2": 60.0, "y2": 85.0, "width": 50.0, "height": 70.0},
            }]

    mock_det = MockDetector()
    slicer = SlicedInferenceEngine(slice_size=300, overlap_ratio=0.20)
    fake_img = np.zeros((600, 600, 3), dtype=np.uint8)

    fused = slicer.execute_sliced_inference(
        detector=mock_det,
        image_bgr=fake_img,
        conf_threshold=0.50,
        fuse_with_global=False,
    )

    assert len(fused) > 0
    # Every shifted detection must have source="tiled" and global coordinates >= 10, 15
    for det in fused:
        assert det["source"] == "tiled"
        assert det["bbox"]["x1"] >= 10.0
        assert det["bbox"]["y1"] >= 15.0
        assert det["bbox"]["x2"] <= 600.0
        assert det["bbox"]["y2"] <= 600.0


# ---------------------------------------------------------
# Flask API Integration Tests with inspection_mode
# ---------------------------------------------------------

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_inspect_tiled_mode(client):
    """Verifies that /api/inspect accepts inspection_mode='tiled' and returns valid response."""
    # Create synthetic test image
    img = np.full((350, 450, 3), 128, dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    img_bytes = io.BytesIO(buf.tobytes())

    data = {
        "image": (img_bytes, "test_road.jpg"),
        "confidence_threshold": "0.20",
        "inspection_mode": "tiled",
    }

    res = client.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    json_data = res.get_json()

    assert json_data["status"] == "success"
    assert json_data["inspection_mode"] == "tiled"
    assert "candidate_summary" in json_data
    assert "detections" in json_data
    assert "annotated_image" in json_data
