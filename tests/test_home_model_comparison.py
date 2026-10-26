"""
Unit tests for isolated Home model evaluation and comparison in ai/evaluation/compare_home_models.py.

Verifies:
1. Isolated model loading without mutating production checkpoints.
2. Graceful handling of missing candidate checkpoints.
3. Correct execution on representative images.
4. Output format of comparison CSV and JSON summary.
5. Preservation of Road model isolation and separation of workflows.
"""

import os
import json
import pytest
import numpy as np

from ai.evaluation.compare_home_models import (
    render_side_by_side_comparison,
    run_home_model_comparison,
)
from ai.detection.detector import (
    DefectDetectionService,
    DEFAULT_HOME_MODEL_PATH,
    DEFAULT_ROAD_MODEL_PATH,
)


def test_render_side_by_side_with_mock_detections():
    """Verifies side-by-side canvas rendering with both baseline and candidate detections."""
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    baseline_dets = [{
        "class_id": 0,
        "class_name": "wall_crack",
        "distress_category": "Wall Crack",
        "confidence": 0.45,
        "bbox": {"x1": 50, "y1": 50, "x2": 150, "y2": 250, "width": 100, "height": 200},
    }]
    candidate_dets = [{
        "class_id": 0,
        "class_name": "wall_crack",
        "distress_category": "Wall Crack",
        "confidence": 0.65,
        "bbox": {"x1": 55, "y1": 52, "x2": 148, "y2": 248, "width": 93, "height": 196},
    }]

    canvas = render_side_by_side_comparison(
        image_bgr=dummy_img,
        baseline_dets=baseline_dets,
        candidate_dets=candidate_dets,
        title="dummy_test.jpg",
    )
    assert canvas is not None
    assert isinstance(canvas, np.ndarray)
    assert canvas.ndim == 3
    # Combined canvas must contain headers and both panels
    assert canvas.shape[1] > 640


def test_render_side_by_side_missing_candidate_placeholder():
    """Verifies side-by-side canvas rendering when candidate checkpoint is missing."""
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    baseline_dets = [{
        "class_id": 2,
        "class_name": "peeling_paint_or_plaster",
        "distress_category": "Peeling Paint / Plaster",
        "confidence": 0.72,
        "bbox": {"x1": 10, "y1": 10, "x2": 300, "y2": 400, "width": 290, "height": 390},
    }]

    canvas = render_side_by_side_comparison(
        image_bgr=dummy_img,
        baseline_dets=baseline_dets,
        candidate_dets=None,
        title="missing_candidate_test.jpg",
        missing_candidate_msg="Candidate Pending Download",
    )
    assert canvas is not None
    assert canvas.shape[1] > 640


def test_run_home_model_comparison_missing_candidate_raises(tmp_path):
    """Verifies that missing candidate checkpoint raises FileNotFoundError by default."""
    test_out = str(tmp_path / "comparison_test_out")
    test_images_dir = "data/test_representative_home_defects"

    if not os.path.exists(test_images_dir) or not os.path.exists(DEFAULT_HOME_MODEL_PATH):
        pytest.skip("Representative images or home_best.pt not available on local disk.")

    with pytest.raises(FileNotFoundError, match="Candidate Home checkpoint not found"):
        run_home_model_comparison(
            baseline_path=DEFAULT_HOME_MODEL_PATH,
            candidate_path="ai/models/nonexistent_exp_a_candidate.pt",
            images_dir=test_images_dir,
            output_dir=test_out,
            conf_threshold=0.20,
            allow_missing_candidate=False,
        )


def test_run_home_model_comparison_missing_candidate_allowed(tmp_path):
    """Verifies that missing candidate with allow_missing_candidate=True reports incomplete status."""
    test_out = str(tmp_path / "comparison_test_out")
    test_images_dir = "data/test_representative_home_defects"

    if not os.path.exists(test_images_dir) or not os.path.exists(DEFAULT_HOME_MODEL_PATH):
        pytest.skip("Representative images or home_best.pt not available on local disk.")

    summary = run_home_model_comparison(
        baseline_path=DEFAULT_HOME_MODEL_PATH,
        candidate_path="ai/models/nonexistent_exp_a_candidate.pt",
        images_dir=test_images_dir,
        output_dir=test_out,
        conf_threshold=0.20,
        allow_missing_candidate=True,
    )

    assert summary["candidate_present_on_disk"] is False
    assert summary["comparison_completed"] is False
    assert summary["status"] == "incomplete"
    assert os.path.exists(summary["csv_path"])


def test_run_home_model_comparison_with_genuine_candidate(tmp_path):
    """Verifies that run_home_model_comparison evaluates both models when candidate is available."""
    test_out = str(tmp_path / "comparison_candidate_out")
    test_images_dir = "data/test_representative_home_defects"
    candidate_path = "ai/models/home_exp_a_test.pt"

    if not (os.path.exists(test_images_dir) and os.path.exists(DEFAULT_HOME_MODEL_PATH) and os.path.exists(candidate_path)):
        pytest.skip("Representative images or checkpoints not available.")

    summary = run_home_model_comparison(
        baseline_path=DEFAULT_HOME_MODEL_PATH,
        candidate_path=candidate_path,
        images_dir=test_images_dir,
        output_dir=test_out,
        conf_threshold=0.20,
    )

    assert summary["candidate_present_on_disk"] is True
    assert summary["comparison_completed"] is True
    assert summary["status"] == "success"
    assert summary["summary_stats"]["candidate_detections_total"] is not None
    assert summary["summary_stats"]["images_tested"] == 10
    assert os.path.exists(summary["csv_path"])



def test_road_model_integrity_and_workflow_separation():
    """
    Verifies that the Road model remains strictly separated and untouched.
    Confirms road detector loads only best.pt with Road classes.
    """
    assert os.path.exists(DEFAULT_ROAD_MODEL_PATH)
    road_detector = DefectDetectionService(model_path=DEFAULT_ROAD_MODEL_PATH, domain="road")
    assert road_detector.domain == "road"
    assert road_detector.model_path == DEFAULT_ROAD_MODEL_PATH
    assert road_detector.is_loaded is True
    # Road classes must be D00, D10, D20, D40
    assert "D00_longitudinal_crack" in road_detector.classes_map.values()
    assert "wall_crack" not in road_detector.classes_map.values()
