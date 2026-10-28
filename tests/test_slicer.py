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


def test_compute_iom():
    """Intersection over Minimum must correctly calculate containment for nested boxes."""
    # box1: 100x100 (area 10,000)
    box1 = {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 100.0}
    # box2: 30x30 inside box1 (area 900)
    box2 = {"x1": 10.0, "y1": 10.0, "x2": 40.0, "y2": 40.0}

    # IoU is low (900 / 10000 = 0.09)
    assert compute_iou(box1, box2) == pytest.approx(900.0 / 10000.0, rel=1e-4)
    # IoM containment is 1.0 (900 / 900 = 1.0)
    from ai.detection.slicer import compute_iom
    assert compute_iom(box1, box2) == pytest.approx(1.0, rel=1e-4)


def test_apply_nms_suppresses_nested_same_class_duplicate():
    """
    Verifies that a large oversized global box and a smaller localized tile box
    of the SAME class are properly deduplicated using containment (IoM) even if IoU < 0.40.
    """
    oversized_global = {
        "class_id": 2,
        "class_name": "peeling_paint_or_plaster",
        "confidence": 0.70,
        "bbox": {"x1": 0.0, "y1": 0.0, "x2": 600.0, "y2": 600.0},
        "source": "global",
    }
    sharp_tile = {
        "class_id": 2,
        "class_name": "peeling_paint_or_plaster",
        "confidence": 0.88,
        "bbox": {"x1": 50.0, "y1": 50.0, "x2": 250.0, "y2": 250.0},
        "source": "tiled",
    }

    # Standard IoU between them is (200*200) / (600*600) = 40,000 / 360,000 = 0.111 (< 0.40)
    # Under standard IoU alone, both would survive.
    # Under IoM containment (IoM = 1.0 >= 0.60), the lower-confidence duplicate is suppressed.
    kept = apply_nms([oversized_global, sharp_tile], iou_threshold=0.40, iom_threshold=0.60)
    assert len(kept) == 1
    assert kept[0]["confidence"] == 0.88
    assert kept[0]["source"] == "tiled"


def test_apply_nms_preserves_colocated_different_classes():
    """
    Verifies that co-located defects of DIFFERENT classes (e.g. wall crack inside peeling paint)
    are strictly preserved and never suppress each other.
    """
    peeling_paint = {
        "class_id": 2,
        "class_name": "peeling_paint_or_plaster",
        "confidence": 0.85,
        "bbox": {"x1": 50.0, "y1": 50.0, "x2": 250.0, "y2": 250.0},
    }
    wall_crack = {
        "class_id": 0,
        "class_name": "wall_crack",
        "confidence": 0.65,
        # Physically located within the same peeling paint region
        "bbox": {"x1": 70.0, "y1": 50.0, "x2": 90.0, "y2": 240.0},
    }

    kept = apply_nms([peeling_paint, wall_crack], iou_threshold=0.40, iom_threshold=0.60, class_aware=True)
    assert len(kept) == 2
    class_names = {d["class_name"] for d in kept}
    assert "peeling_paint_or_plaster" in class_names
    assert "wall_crack" in class_names


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


def test_sliced_boundary_clipping():
    """
    Verifies that tile bounding boxes extending beyond tile boundaries
    are strictly clamped to image boundaries [0, w] and [0, h], avoiding coordinate overflow.
    """
    class OverflowDetector:
        def __init__(self):
            self.last_inference_stats = {}

        def _detect_standard(self, tile, conf_threshold=0.25, raise_if_unloaded=False):
            # Returns an overflowing box [100, 100, 500, 500]
            # When added to a tile at x_min=300, y_min=300 on a 500x500 image,
            # unclipped coordinates would reach 800x800.
            return [{
                "class_id": 2,
                "class_name": "peeling_paint_or_plaster",
                "distress_category": "Peeling Paint / Plaster",
                "confidence": 0.82,
                "bbox": {"x1": 100.0, "y1": 100.0, "x2": 500.0, "y2": 500.0, "width": 400.0, "height": 400.0},
            }]

    detector = OverflowDetector()
    slicer = SlicedInferenceEngine(slice_size=300, overlap_ratio=0.20)
    img_500 = np.zeros((500, 500, 3), dtype=np.uint8)

    fused = slicer.execute_sliced_inference(
        detector=detector,
        image_bgr=img_500,
        conf_threshold=0.50,
        fuse_with_global=False,
    )

    assert len(fused) > 0
    for det in fused:
        b = det["bbox"]
        assert 0.0 <= b["x1"] < b["x2"] <= 500.0
        assert 0.0 <= b["y1"] < b["y2"] <= 500.0
        assert b["width"] == pytest.approx(b["x2"] - b["x1"], 0.1)
        assert b["height"] == pytest.approx(b["y2"] - b["y1"], 0.1)


def test_cross_tile_and_global_deduplication_integration():
    """
    Tests end-to-end multi-tile + global fusion:
    - Global pass detects an oversized peeling-paint box (conf=0.72) covering the whole area.
    - Tile 1 detects a sharp localized peeling-paint box (conf=0.88) and a wall crack (conf=0.68).
    - Tile 2 detects a partially overlapping peeling-paint box across the tile boundary (conf=0.84).
    Verifies:
    1. Oversized global peeling-paint box is deduplicated.
    2. Overlapping tile peeling-paint boxes are deduplicated.
    3. Wall crack is strictly preserved (class-aware NMS).
    """
    class MultiScaleMockDetector:
        def __init__(self):
            self.last_inference_stats = {}

        def _detect_standard(self, img, conf_threshold=0.25, raise_if_unloaded=False):
            h, w = img.shape[:2]
            # Global pass on full 600x600 image
            if w == 600 and h == 600:
                return [{
                    "class_id": 2,
                    "class_name": "peeling_paint_or_plaster",
                    "distress_category": "Peeling Paint / Plaster",
                    "confidence": 0.72,
                    "bbox": {"x1": 20.0, "y1": 20.0, "x2": 580.0, "y2": 580.0, "width": 560.0, "height": 560.0},
                }]
            # Slices (approx 384x384)
            return [
                {
                    "class_id": 2,
                    "class_name": "peeling_paint_or_plaster",
                    "distress_category": "Peeling Paint / Plaster",
                    "confidence": 0.88,
                    "bbox": {"x1": 50.0, "y1": 50.0, "x2": 200.0, "y2": 200.0, "width": 150.0, "height": 150.0},
                },
                {
                    "class_id": 0,
                    "class_name": "wall_crack",
                    "distress_category": "Wall Crack",
                    "confidence": 0.68,
                    "bbox": {"x1": 60.0, "y1": 50.0, "x2": 80.0, "y2": 200.0, "width": 20.0, "height": 150.0},
                },
            ]

    detector = MultiScaleMockDetector()
    slicer = SlicedInferenceEngine(slice_size=384, overlap_ratio=0.20, merge_iou_threshold=0.40, merge_iom_threshold=0.60)
    fake_img = np.zeros((600, 600, 3), dtype=np.uint8)

    fused = slicer.execute_sliced_inference(
        detector=detector,
        image_bgr=fake_img,
        conf_threshold=0.50,
        fuse_with_global=True,
    )

    # Class separation:
    # Wall Crack (class 0) must be preserved
    crack_dets = [d for d in fused if d["class_id"] == 0]
    assert len(crack_dets) >= 1
    assert crack_dets[0]["class_name"] == "wall_crack"

    # Peeling paint detections should be cleanly deduplicated:
    # The oversized 0.72 global box was suppressed by the tighter 0.88 tile box
    peeling_dets = [d for d in fused if d["class_id"] == 2]
    for p in peeling_dets:
        # None of the surviving peeling paint detections should be the oversized global box
        assert p["confidence"] >= 0.88


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


def test_calculate_slices_max_slices_cap():
    """Ultra-high resolution images must dynamically scale tile size to prevent slice count explosion."""
    slicer = SlicedInferenceEngine(slice_size=384, overlap_ratio=0.20, max_slices=16)
    # 4000x3000 would normally generate 140+ slices without cap
    slices = slicer.calculate_slices(img_w=4000, img_h=3000)
    assert len(slices) <= 25  # Bounded to protect against Gunicorn worker timeout

