"""
Test suite for Phase 4.5: Inspection Reports, PDF Export, and Data Export.

Tests server-side filter validation, report data generation, CSV export (UTF-8 BOM),
professional PDF generation (ReportLab), empty datasets, missing fields,
exclusion of local server paths, and REST API endpoints.
"""

import io
import os
import json
import tempfile
import datetime
import pytest

from database.db import (
    init_db,
    save_inspection,
    update_inspection_status,
    log_maintenance_activity,
    DEFAULT_STATUS,
    ALLOWED_STATUSES,
)
from database.reports import (
    validate_report_filters,
    generate_report_data,
    generate_report_csv,
    generate_report_pdf,
    sanitize_inspection_for_report,
    REPORT_DISCLAIMER_TEXT,
    ALLOWED_DEADLINE_FILTERS,
)
from app.server import create_app


@pytest.fixture
def temp_db():
    """Provides a temporary, isolated SQLite database initialized with schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


@pytest.fixture
def populated_db(temp_db):
    """
    Populates the temporary DB with diverse records:
    - Multiple dates
    - Multiple distress classes (Longitudinal, Transverse, Alligator, Pothole, Sound)
    - Different statuses (Open, Under Review, Repair in Progress, Resolved)
    - Various maintenance deadlines (overdue, due today, upcoming, resolved, none)
    - Geotagged and non-geotagged records
    """
    ref_date = datetime.date(2026, 10, 22)
    today_str = ref_date.isoformat()
    yesterday_str = (ref_date - datetime.timedelta(days=2)).isoformat()
    tomorrow_str = (ref_date + datetime.timedelta(days=5)).isoformat()

    # Record 1: Open Pothole, Overdue, Geotagged in Bengaluru
    r1 = save_inspection({
        "image_name": "bengaluru_pothole_01.jpg",
        "original_image_path": "C:\\SecretServerPath\\uploads\\orig1.jpg",
        "annotated_image_path": "C:\\SecretServerPath\\processed\\annot1.jpg",
        "road_name": "MG Road",
        "area": "Indiranagar",
        "city": "Bengaluru",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "location_notes": "Deep pothole near junction",
        "target_repair_date": yesterday_str,
        "status": "Open",
        "detections": [
            {"distress_category": "Pothole", "class_name": "D40", "confidence": 0.88, "bbox": {"x1": 10, "y1": 20, "x2": 100, "y2": 120, "width": 90, "height": 100}}
        ]
    }, db_path=temp_db)

    # Record 2: Repair in Progress Alligator Crack, Due Today, Geotagged in Mumbai
    r2 = save_inspection({
        "image_name": "mumbai_alligator_02.jpg",
        "original_image_path": "C:\\SecretServerPath\\uploads\\orig2.jpg",
        "annotated_image_path": "C:\\SecretServerPath\\processed\\annot2.jpg",
        "road_name": "Marine Drive",
        "area": "South Mumbai",
        "city": "Mumbai",
        "latitude": 18.9438,
        "longitude": 72.8234,
        "location_notes": "Structural fatigue cracking",
        "target_repair_date": today_str,
        "status": "Repair in Progress",
        "detections": [
            {"distress_category": "Alligator Crack", "class_name": "D20", "confidence": 0.91, "bbox": {"x1": 50, "y1": 60, "x2": 200, "y2": 210, "width": 150, "height": 150}}
        ]
    }, db_path=temp_db)

    # Record 3: Resolved Longitudinal Crack, Upcoming original date, Geotagged in Delhi
    r3 = save_inspection({
        "image_name": "delhi_longitudinal_03.jpg",
        "original_image_path": "C:\\SecretServerPath\\uploads\\orig3.jpg",
        "annotated_image_path": "C:\\SecretServerPath\\processed\\annot3.jpg",
        "road_name": "Ring Road",
        "area": "Lajpat Nagar",
        "city": "New Delhi",
        "latitude": 28.5672,
        "longitude": 77.2435,
        "location_notes": "Longitudinal crack sealed",
        "target_repair_date": tomorrow_str,
        "status": "Resolved",
        "detections": [
            {"distress_category": "Longitudinal Crack", "class_name": "D00", "confidence": 0.79, "bbox": {"x1": 100, "y1": 100, "x2": 150, "y2": 400, "width": 50, "height": 300}}
        ]
    }, db_path=temp_db)

    # Record 4: Clean / Sound Surface (0 Defects), No Coordinates, No Deadline
    r4 = save_inspection({
        "image_name": "sound_road_04.jpg",
        "original_image_path": "C:\\SecretServerPath\\uploads\\orig4.jpg",
        "annotated_image_path": "C:\\SecretServerPath\\processed\\annot4.jpg",
        "road_name": "Outer Bypass",
        "area": "Electronic City",
        "city": "Bengaluru",
        "latitude": None,
        "longitude": None,
        "location_notes": "Newly paved asphalt layer",
        "target_repair_date": None,
        "status": "Open",
        "detections": []
    }, db_path=temp_db)

    # Add activity audit log to record 1
    log_maintenance_activity(
        inspection_id=r1["id"],
        action_type="status_change",
        previous_status="Open",
        new_status="Under Review",
        notes="Inspected by road engineer",
        db_path=temp_db
    )

    return temp_db, ref_date


@pytest.fixture
def test_client(populated_db):
    """Provides a Flask test client using the populated temporary database."""
    db_path, _ = populated_db
    app = create_app(test_config={"DATABASE_PATH": db_path, "TESTING": True})
    with app.test_client() as client:
        yield client


# =============================================================================
# 1. Filter Validation Tests
# =============================================================================

def test_validate_report_filters_empty_defaults():
    """Empty filter dictionary should return valid defaults."""
    is_valid, norm, err = validate_report_filters({})
    assert is_valid is True
    assert err is None
    assert norm["start_date"] is None
    assert norm["end_date"] is None
    assert norm["category"] is None
    assert norm["status"] is None
    assert norm["deadline"] is None
    assert norm["limit"] == 500
    assert norm["offset"] == 0


def test_validate_report_filters_valid_dates():
    """Valid YYYY-MM-DD date range should be accepted."""
    is_valid, norm, err = validate_report_filters({
        "start_date": "2026-01-01",
        "end_date": "2026-10-31",
    })
    assert is_valid is True
    assert norm["start_date"] == "2026-01-01"
    assert norm["end_date"] == "2026-10-31"


def test_validate_report_filters_invalid_start_date():
    """Malformed start date should fail validation with clear error."""
    is_valid, norm, err = validate_report_filters({"start_date": "31-10-2026"})
    assert is_valid is False
    assert "start_date" in err


def test_validate_report_filters_invalid_end_date():
    """Malformed end date should fail validation with clear error."""
    is_valid, norm, err = validate_report_filters({"end_date": "invalid-date"})
    assert is_valid is False
    assert "end_date" in err


def test_validate_report_filters_start_after_end():
    """start_date after end_date must be rejected."""
    is_valid, norm, err = validate_report_filters({
        "start_date": "2026-10-25",
        "end_date": "2026-10-10",
    })
    assert is_valid is False
    assert "start_date" in err and "end_date" in err


def test_validate_report_filters_status():
    """Status validation should allow valid statuses and 'all'."""
    is_valid, norm, _ = validate_report_filters({"status": "Open"})
    assert is_valid is True
    assert norm["status"] == "Open"

    is_valid, norm, _ = validate_report_filters({"status": "all"})
    assert is_valid is True
    assert norm["status"] is None

    is_valid, _, err = validate_report_filters({"status": "InvalidStatusXYZ"})
    assert is_valid is False
    assert "Invalid status" in err


def test_validate_report_filters_deadline():
    """Deadline validation should accept valid deadline values."""
    for dl in ["overdue", "due_today", "upcoming", "resolved", "no_deadline", "none"]:
        is_valid, norm, _ = validate_report_filters({"deadline": dl})
        assert is_valid is True
        assert norm["deadline"] == dl

    is_valid, _, err = validate_report_filters({"deadline": "not_a_valid_deadline"})
    assert is_valid is False
    assert "Invalid deadline" in err


# =============================================================================
# 2. Report Data Generation & Security Tests
# =============================================================================

def test_generate_report_data_all_records(populated_db):
    """Generates report data without filters and verifies summary aggregations."""
    db_path, ref_date = populated_db
    data = generate_report_data({}, ref_date=ref_date, db_path=db_path)

    assert "generated_at" in data
    assert data["reference_date"] == ref_date.isoformat()
    assert "summary" in data

    summary = data["summary"]
    assert summary["total_inspections"] == 4
    # Total defects: 1 Pothole + 1 Alligator + 1 Longitudinal + 0 Sound = 3
    assert summary["total_defects"] == 3
    assert len(data["records"]) == 4

    # Verify category counts
    cats = summary["category_distribution"]
    assert cats["Pothole"] == 1
    assert cats["Alligator Crack"] == 1
    assert cats["Longitudinal Crack"] == 1
    assert cats["Sound Surface"] == 1


def test_generate_report_data_strips_internal_paths(populated_db):
    """
    CRITICAL SECURITY CHECK:
    Ensures local disk file paths (e.g. C:\\SecretServerPath\\uploads\\orig1.jpg)
    are NEVER exposed in report output records.
    """
    db_path, ref_date = populated_db
    data = generate_report_data({}, ref_date=ref_date, db_path=db_path)

    for r in data["records"]:
        assert "original_image_path" not in r
        assert "annotated_image_path" not in r
        assert "file_path" not in r
        assert "processed_file_path" not in r
        # Safe URL routes should be provided instead
        assert r["annotated_image_url"].startswith("/api/inspections/")
        assert r["original_image_url"].startswith("/api/inspections/")


def test_generate_report_data_filter_by_status(populated_db):
    """Filters report records by workflow status."""
    db_path, ref_date = populated_db
    data = generate_report_data({"status": "Open"}, ref_date=ref_date, db_path=db_path)

    summary = data["summary"]
    assert summary["total_inspections"] == 2
    for r in data["records"]:
        assert r["status"] == "Open"


def test_generate_report_data_filter_by_category(populated_db):
    """Filters report records by defect category."""
    db_path, ref_date = populated_db
    data = generate_report_data({"category": "Pothole"}, ref_date=ref_date, db_path=db_path)

    assert data["summary"]["total_inspections"] == 1
    assert data["records"][0]["defect_type"] == "Pothole"


def test_generate_report_data_filter_by_city(populated_db):
    """Filters report records by city."""
    db_path, ref_date = populated_db
    data = generate_report_data({"city": "Mumbai"}, ref_date=ref_date, db_path=db_path)

    assert data["summary"]["total_inspections"] == 1
    assert data["records"][0]["city"] == "Mumbai"


def test_generate_report_data_filter_by_overdue_deadline(populated_db):
    """Filters active records that are overdue."""
    db_path, ref_date = populated_db
    data = generate_report_data({"deadline": "overdue"}, ref_date=ref_date, db_path=db_path)

    assert data["summary"]["total_inspections"] == 1
    rec = data["records"][0]
    assert rec["is_overdue"] is True
    assert rec["status"] != "Resolved"


def test_generate_report_data_empty_dataset(populated_db):
    """Non-matching filter criteria must return 0 records gracefully without crashing."""
    db_path, ref_date = populated_db
    data = generate_report_data({"city": "NonExistentCity12345"}, ref_date=ref_date, db_path=db_path)

    assert data["summary"]["total_inspections"] == 0
    assert data["summary"]["total_defects"] == 0
    assert len(data["records"]) == 0


def test_generate_report_data_missing_fields_and_legacy_records(temp_db):
    """Gracefully handles records with missing GPS coordinates, empty notes, and absent deadlines."""
    rec = save_inspection({
        "image_name": "legacy_image.jpg",
        "road_name": "",
        "area": "",
        "city": "",
        "latitude": None,
        "longitude": None,
        "location_notes": "",
        "target_repair_date": None,
        "status": "Open",
        "detections": []
    }, db_path=temp_db)

    data = generate_report_data({}, db_path=temp_db)
    assert len(data["records"]) == 1
    r = data["records"][0]
    assert r["coords_display"] == "Not recorded"
    assert r["maintenance_label"] == "No Target Date"
    assert r["is_overdue"] is False
    assert r["defect_count"] == 0


# =============================================================================
# 3. CSV Export Tests
# =============================================================================

def test_generate_report_csv_format(populated_db):
    """Verifies that generated CSV has UTF-8 BOM, executive headers, and itemized rows."""
    db_path, ref_date = populated_db
    data = generate_report_data({}, ref_date=ref_date, db_path=db_path)
    csv_str = generate_report_csv(data)

    # 1. Excel compatibility: UTF-8 BOM
    assert csv_str.startswith("\ufeff")

    # 2. Executive metadata lines
    assert "# VisionGuard AI" in csv_str
    assert "# Generated At:" in csv_str
    assert "Inspection ID,Inspection Date" in csv_str

    # 3. Data rows
    assert "MG Road" in csv_str
    assert "Marine Drive" in csv_str
    assert "Ring Road" in csv_str


def test_generate_report_csv_empty_dataset(populated_db):
    """Empty dataset CSV export succeeds and displays informative message."""
    db_path, ref_date = populated_db
    data = generate_report_data({"city": "NoSuchPlace"}, ref_date=ref_date, db_path=db_path)
    csv_str = generate_report_csv(data)

    assert csv_str.startswith("\ufeff")
    assert "No inspection records match the specified filters." in csv_str


# =============================================================================
# 4. PDF Generation Tests (ReportLab)
# =============================================================================

def test_generate_report_pdf_valid_bytes(populated_db):
    """Verifies that PDF export generates valid PDF bytes with header and structure."""
    db_path, ref_date = populated_db
    data = generate_report_data({}, ref_date=ref_date, db_path=db_path)
    pdf_bytes = generate_report_pdf(data)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF-")


def test_generate_report_pdf_empty_dataset(populated_db):
    """PDF generation on empty dataset must not crash and generate a valid PDF."""
    db_path, ref_date = populated_db
    data = generate_report_data({"city": "NonExistentPlace"}, ref_date=ref_date, db_path=db_path)
    pdf_bytes = generate_report_pdf(data)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


# =============================================================================
# 5. REST API Route Integration Tests
# =============================================================================

def test_api_report_preview_success(test_client):
    """GET /api/reports/preview returns 200 with structured report data."""
    res = test_client.get("/api/reports/preview")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["status"] == "success"
    assert "report" in json_data
    assert json_data["report"]["summary"]["total_inspections"] == 4


def test_api_report_preview_with_filters(test_client):
    """GET /api/reports/preview with category filter."""
    res = test_client.get("/api/reports/preview?category=Pothole")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["report"]["summary"]["total_inspections"] == 1


def test_api_report_preview_invalid_start_date(test_client):
    """GET /api/reports/preview with invalid date format returns 400 Bad Request."""
    res = test_client.get("/api/reports/preview?start_date=2026/10/22")
    assert res.status_code == 400
    json_data = res.get_json()
    assert json_data["status"] == "error"
    assert json_data["error_code"] == "INVALID_REPORT_FILTERS"


def test_api_report_preview_invalid_date_range(test_client):
    """GET /api/reports/preview with start_date > end_date returns 400 Bad Request."""
    res = test_client.get("/api/reports/preview?start_date=2026-10-25&end_date=2026-10-10")
    assert res.status_code == 400
    json_data = res.get_json()
    assert json_data["status"] == "error"
    assert json_data["error_code"] == "INVALID_REPORT_FILTERS"


def test_api_report_csv_export(test_client):
    """GET /api/reports/export/csv returns downloadable CSV with UTF-8 BOM."""
    res = test_client.get("/api/reports/export/csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("Content-Type", "")
    assert "attachment" in res.headers.get("Content-Disposition", "")
    assert res.data.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM bytes


def test_api_report_pdf_export(test_client):
    """GET /api/reports/export/pdf returns downloadable PDF bytes."""
    res = test_client.get("/api/reports/export/pdf")
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("Content-Type", "")
    assert "attachment" in res.headers.get("Content-Disposition", "")
    assert res.data.startswith(b"%PDF-")


def test_api_report_export_aliases(test_client):
    """Verifies that route aliases /api/reports/csv and /api/reports/pdf work as expected."""
    res_csv = test_client.get("/api/reports/csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers.get("Content-Type", "")

    res_pdf = test_client.get("/api/reports/pdf")
    assert res_pdf.status_code == 200
    assert "application/pdf" in res_pdf.headers.get("Content-Type", "")
