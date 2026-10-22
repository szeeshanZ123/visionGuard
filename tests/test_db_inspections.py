"""
Unit tests for VisionGuard AI inspection records persistence layer.
"""

import os
import pytest
from database.db import (
    init_db,
    save_inspection,
    get_inspections,
    get_inspection_by_id,
    update_inspection_status,
    delete_inspection,
    ALLOWED_STATUSES,
)


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_inspections.db")
    init_db(db_file)
    return db_file


def test_save_inspection_with_zero_detections(test_db):
    """Verifies that an inspection with 0 defects saves accurately without fabricating data."""
    data = {
        "image_name": "clean_road.jpg",
        "original_image_path": "data/uploads/clean_road.jpg",
        "annotated_image_path": "data/processed/clean_road_annotated.jpg",
        "road_name": "Ring Road Sector 4",
        "location_notes": "Sound asphalt pavement, no distress",
        "inspection_mode": "standard",
        "confidence_threshold": 0.25,
        "detections": [],
        "status": "Open",
    }

    record = save_inspection(data, db_path=test_db)
    assert record["id"] is not None
    assert record["image_name"] == "clean_road.jpg"
    assert record["road_name"] == "Ring Road Sector 4"
    assert record["defect_count"] == 0
    assert record["defect_type"] == "None detected"
    assert record["confidence"] == 0.0
    assert record["status"] == "Open"
    assert record["detections"] == []


def test_save_inspection_with_genuine_detections(test_db):
    """Verifies saving an inspection with authentic bounding boxes and categories."""
    detections = [
        {
            "class_id": 0,
            "class_name": "D00_longitudinal_crack",
            "distress_category": "Longitudinal Crack",
            "confidence": 0.4215,
            "bbox": {"x1": 120.0, "y1": 200.0, "x2": 250.0, "y2": 580.0, "width": 130.0, "height": 380.0},
            "source": "global"
        },
        {
            "class_id": 2,
            "class_name": "D20_alligator_crack",
            "distress_category": "Alligator Crack",
            "confidence": 0.6540,
            "bbox": {"x1": 300.0, "y1": 400.0, "x2": 600.0, "y2": 720.0, "width": 300.0, "height": 320.0},
            "source": "global"
        }
    ]

    data = {
        "image_name": "damaged_mumbai.jpg",
        "original_image_path": "data/uploads/orig_123_damaged_mumbai.jpg",
        "annotated_image_path": "data/processed/annotated_123_damaged_mumbai.jpg",
        "road_name": "Western Express Highway",
        "location_notes": "Near flyover expansion joint",
        "inspection_mode": "standard",
        "confidence_threshold": 0.25,
        "detections": detections,
        "status": "Open",
    }

    record = save_inspection(data, db_path=test_db)
    assert record["id"] is not None
    assert record["defect_count"] == 2
    assert "Alligator Crack" in record["defect_type"]
    assert "Longitudinal Crack" in record["defect_type"]
    assert record["confidence"] == 0.654
    assert len(record["detections"]) == 2
    assert record["detections"][0]["class_id"] == 0


def test_duplicate_save_prevention(test_db):
    """Verifies that duplicate saves with identical original_image_path return the existing record."""
    data = {
        "image_name": "test_dup.jpg",
        "original_image_path": "data/uploads/unique_orig_path.jpg",
        "road_name": "Main Street",
        "detections": [],
        "status": "Open",
    }

    rec1 = save_inspection(data, db_path=test_db)
    rec2 = save_inspection(data, db_path=test_db)
    assert rec1["id"] == rec2["id"]

    all_recs = get_inspections(db_path=test_db)
    assert len(all_recs) == 1


def test_status_tracking_transitions(test_db):
    """Verifies status transitions through all 4 initial states."""
    data = {
        "image_name": "pothole_road.jpg",
        "road_name": "Koramangala 80ft Road",
        "detections": [{"class_id": 3, "class_name": "D40_pothole", "confidence": 0.72}],
        "status": "Open",
    }
    rec = save_inspection(data, db_path=test_db)
    rec_id = rec["id"]
    assert rec["status"] == "Open"

    for state in ["Under Review", "Repair in Progress", "Resolved"]:
        updated = update_inspection_status(rec_id, state, notes=f"Moved to {state}", db_path=test_db)
        assert updated is not None
        assert updated["status"] == state
        assert updated["notes"] == f"Moved to {state}"

    # Verify invalid status is rejected
    with pytest.raises(ValueError):
        update_inspection_status(rec_id, "NonExistentStatus", db_path=test_db)


def test_get_inspections_filtering(test_db):
    """Verifies listing inspections with status filters."""
    for i, st in enumerate(["Open", "Under Review", "Resolved"]):
        save_inspection({
            "image_name": f"img_{i}.jpg",
            "original_image_path": f"path_{i}.jpg",
            "status": st,
            "detections": []
        }, db_path=test_db)

    all_list = get_inspections(db_path=test_db)
    assert len(all_list) == 3

    open_list = get_inspections(status="Open", db_path=test_db)
    assert len(open_list) == 1
    assert open_list[0]["status"] == "Open"

    resolved_list = get_inspections(status="Resolved", db_path=test_db)
    assert len(resolved_list) == 1
    assert resolved_list[0]["status"] == "Resolved"
