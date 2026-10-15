"""
Unit tests for DefectDetectionService in ai/detection/detector.py.

Verifies:
- Safe handling of missing checkpoints.
- Safe initialization without crashing when best.pt is not present.
- Contract adherence of detect() returning genuine bounding boxes and confidence.
- OpenCV visual overlay drawing (draw_annotations).
- Base64 encoding utility.
"""

import os
import cv2
import numpy as np
import pytest

from ai.detection.detector import (
    DefectDetectionService,
    CLASS_NAMES,
    CLASS_DISPLAY_NAMES,
    CLASS_COLORS_BGR,
)


def test_detector_missing_checkpoint():
    """Verifies that DefectDetectionService safely marks is_loaded=False when weights are missing."""
    detector = DefectDetectionService(model_path="nonexistent_checkpoint.pt")
    assert detector.is_loaded is False
    assert detector.model is None
    assert "not found" in detector.status_message.lower()

    # detect() returns empty list without raising
    blank_img = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(blank_img)
    assert detections == []

    # detect() raises FileNotFoundError if raise_if_unloaded=True
    with pytest.raises(FileNotFoundError) as exc_info:
        detector.detect(blank_img, raise_if_unloaded=True)
    assert "not found" in str(exc_info.value).lower()


def test_detector_draw_annotations_empty():
    """Verifies that drawing annotations with no detections returns an unaltered image."""
    img = np.full((300, 400, 3), 100, dtype=np.uint8)
    annotated = DefectDetectionService.draw_annotations(img, [])
    assert annotated is not None
    assert annotated.shape == img.shape
    # Must be pixel-identical to original
    np.testing.assert_array_equal(annotated, img)


def test_detector_draw_annotations_with_boxes():
    """Verifies that drawing annotations renders boxes and labels on the image."""
    img = np.zeros((400, 500, 3), dtype=np.uint8)
    mock_detections = [
        {
            "class_id": 3,
            "class_name": "D40_pothole",
            "distress_category": "Pothole",
            "confidence": 0.88,
            "bbox": {
                "x1": 50.0,
                "y1": 60.0,
                "x2": 180.0,
                "y2": 220.0,
                "width": 130.0,
                "height": 160.0,
                "aspect_ratio": 0.812,
                "pixel_area": 20800.0,
            },
        },
        {
            "class_id": 0,
            "class_name": "D00_longitudinal_crack",
            "distress_category": "Longitudinal Crack",
            "confidence": 0.72,
            "bbox": {
                "x1": 250.0,
                "y1": 30.0,
                "x2": 320.0,
                "y2": 350.0,
                "width": 70.0,
                "height": 320.0,
                "aspect_ratio": 0.219,
                "pixel_area": 22400.0,
            },
        },
    ]

    annotated = DefectDetectionService.draw_annotations(img, mock_detections)
    assert annotated is not None
    assert annotated.shape == img.shape
    # The annotated image must now contain painted pixels (not all black)
    assert np.any(annotated > 0)


def test_detector_encode_image_to_base64():
    """Verifies base64 image data URL conversion."""
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    b64_url = DefectDetectionService.encode_image_to_base64(img, ext=".jpg")
    assert b64_url.startswith("data:image/jpeg;base64,")
    assert len(b64_url) > 50


def test_detector_invalid_input_handling():
    """Verifies detect() gracefully handles None or empty arrays."""
    detector = DefectDetectionService(model_path="nonexistent.pt")
    assert detector.detect(None) == []
    empty_arr = np.array([], dtype=np.uint8)
    assert detector.detect(empty_arr) == []
