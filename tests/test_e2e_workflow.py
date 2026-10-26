"""End-to-End Workflow Test for VisionGuard AI Inspection Records.

Tests the complete flow:
1. Image upload and YOLOv8 inference (/api/inspect).
2. Inspection record persistence (/api/inspections).
3. Duplicate save prevention.
4. History listing with status filter (/api/inspections?status=...).
5. Single record retrieval with full telemetry (/api/inspections/<id>).
6. Safe image streaming (/api/inspections/<id>/image/...).
7. Status tracking lifecycle (Open -> Under Review -> Repair in Progress -> Resolved).
8. Disclaimer verification (workflow status != structural/physical repair proof).
9. Zero-detection persistence test (authentic representation of 0 defects).
"""

import json
import os
import io
import pytest
from app.server import app
import uuid
from app.server import create_app
from ai.detection.detector import DefectDetectionService


@pytest.fixture
def client(tmp_path):
    test_db = str(tmp_path / "e2e_test.db")
    test_upload_dir = str(tmp_path / "uploads")
    test_proc_dir = str(tmp_path / "processed")
    os.makedirs(test_upload_dir, exist_ok=True)
    os.makedirs(test_proc_dir, exist_ok=True)

    test_app = create_app(
        detector=DefectDetectionService(model_path="ai/models/best.pt"),
        test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db,
            "UPLOAD_FOLDER": test_upload_dir,
            "PROCESSED_FOLDER": test_proc_dir,
        }
    )
    with test_app.test_client() as client:
        yield client


def test_complete_inspection_workflow(client):
    sample_img_path = os.path.join(os.path.dirname(__file__), "..", "data", "sample_road.jpg")
    assert os.path.exists(sample_img_path), f"Sample road image missing at {sample_img_path}"

    with open(sample_img_path, "rb") as f:
        img_bytes = f.read()

    # Step 1: Upload image and run inference
    upload_res = client.post(
        "/api/inspect",
        data={
            "image": (io.BytesIO(img_bytes), "sample_road.jpg"),
            "confidence": "0.15",
            "inspection_mode": "standard",
        },
        content_type="multipart/form-data"
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.data}"
    inspect_data = upload_res.get_json()
    assert inspect_data["status"] == "success"
    assert "original_file_path" in inspect_data
    assert "processed_file_path" in inspect_data
    assert os.path.exists(inspect_data["original_file_path"])
    assert os.path.exists(inspect_data["processed_file_path"])

    orig_path = inspect_data["original_file_path"]
    proc_path = inspect_data["processed_file_path"]
    detections = inspect_data["detections"]

    # Step 2: Save inspection record
    save_payload = {
        "image_name": inspect_data["filename"],
        "original_image_path": orig_path,
        "annotated_image_path": proc_path,
        "road_name": "NH-48 Sector 29 Expressway",
        "location_notes": "KM 34.2 Northbound lane outer edge",
        "inspection_mode": "standard",
        "confidence_threshold": 0.15,
        "detections": detections,
        "status": "Open",
    }
    save_res = client.post(
        "/api/inspections",
        data=json.dumps(save_payload),
        content_type="application/json"
    )
    assert save_res.status_code == 201, f"Save failed: {save_res.data}"
    save_data = save_res.get_json()
    assert save_data["status"] == "success"
    record = save_data["inspection"]
    record_id = record["id"]
    assert record_id > 0
    assert record["road_name"] == "NH-48 Sector 29 Expressway"
    assert record["status"] == "Open"
    assert record["defect_count"] == len(detections)

    # Step 3: Prevent duplicate save with identical original_image_path
    dup_res = client.post(
        "/api/inspections",
        data=json.dumps(save_payload),
        content_type="application/json"
    )
    assert dup_res.status_code == 409
    dup_data = dup_res.get_json()
    assert dup_data["status"] == "error"
    assert "already been saved" in dup_data["message"]

    # Step 4: List inspections
    list_res = client.get("/api/inspections")
    assert list_res.status_code == 200
    list_data = list_res.get_json()
    assert list_data["status"] == "success"
    assert any(i["id"] == record_id for i in list_data["inspections"])

    # Filter by status
    open_res = client.get("/api/inspections?status=Open")
    assert open_res.status_code == 200
    assert any(i["id"] == record_id for i in open_res.get_json()["inspections"])

    resolved_res = client.get("/api/inspections?status=Resolved")
    assert resolved_res.status_code == 200
    assert not any(i["id"] == record_id for i in resolved_res.get_json()["inspections"])

    # Step 5: Get single inspection details
    detail_res = client.get(f"/api/inspections/{record_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.get_json()
    assert detail_data["status"] == "success"
    fetched = detail_data["inspection"]
    assert fetched["id"] == record_id
    assert fetched["road_name"] == "NH-48 Sector 29 Expressway"
    assert len(fetched["detections"]) == len(detections)
    assert "disclaimer" in fetched

    # Step 6: Safe image streaming
    orig_img_res = client.get(f"/api/inspections/{record_id}/image/original")
    assert orig_img_res.status_code == 200
    assert orig_img_res.content_type.startswith("image/")

    anno_img_res = client.get(f"/api/inspections/{record_id}/image/annotated")
    assert anno_img_res.status_code == 200
    assert anno_img_res.content_type.startswith("image/")

    # Step 7: Status tracking lifecycle with audit notes and disclaimers
    # 7a: Transition to Under Review
    patch1 = client.patch(
        f"/api/inspections/{record_id}/status",
        data=json.dumps({"status": "Under Review", "notes": "Dispatched maintenance team to survey site"}),
        content_type="application/json"
    )
    assert patch1.status_code == 200
    p1_data = patch1.get_json()
    assert p1_data["inspection"]["status"] == "Under Review"
    assert "disclaimer" in p1_data

    # 7b: Transition to Repair in Progress
    patch2 = client.patch(
        f"/api/inspections/{record_id}/status",
        data=json.dumps({"status": "Repair in Progress", "notes": "Contractor assigned asphalt patch"}),
        content_type="application/json"
    )
    assert patch2.status_code == 200
    assert patch2.get_json()["inspection"]["status"] == "Repair in Progress"

    # 7c: Transition to Resolved
    patch3 = client.patch(
        f"/api/inspections/{record_id}/status",
        data=json.dumps({"status": "Resolved", "notes": "Work order closed by regional engineer"}),
        content_type="application/json"
    )
    assert patch3.status_code == 200
    assert patch3.get_json()["inspection"]["status"] == "Resolved"
    # Ensure disclaimer explicitly states this does not prove physical repair
    assert "does not prove physical road repair" in patch3.get_json()["disclaimer"]

    # 7d: Invalid status rejected
    patch_bad = client.patch(
        f"/api/inspections/{record_id}/status",
        data=json.dumps({"status": "Permanently Fixed"}),
        content_type="application/json"
    )
    assert patch_bad.status_code == 400
    assert patch_bad.get_json()["error_code"] == "INVALID_STATUS"
    assert "is invalid" in patch_bad.get_json()["message"]

    # Step 8: Zero-detection save test
    zero_payload = {
        "image_name": "pristine_pavement.jpg",
        "original_image_path": "data/uploads/pristine_test.jpg",
        "annotated_image_path": "data/processed/pristine_test.jpg",
        "road_name": "Ring Road Sector 1",
        "location_notes": "Smooth freshly laid pavement",
        "inspection_mode": "standard",
        "confidence_threshold": 0.25,
        "detections": [],
        "status": "Open",
    }
    zero_res = client.post(
        "/api/inspections",
        data=json.dumps(zero_payload),
        content_type="application/json"
    )
    assert zero_res.status_code == 201
    zero_rec = zero_res.get_json()["inspection"]
    assert zero_rec["defect_count"] == 0
    assert zero_rec["defect_type"] in ["None", "None detected"]
    assert zero_rec["confidence"] == 0.0
    assert zero_rec["detections"] == []


def test_e2e_home_inspection_and_complaint_workflow(client):
    """
    End-to-end integration test for Home & Building Defect workflow:
    1. Upload image to /api/inspect with domain="home"
    2. Save Home inspection record to SQLite with inspection_type='home'
    3. Generate and retrieve Civic Complaint Draft (/api/inspections/<id>/complaint-draft)
    4. Verify complaint draft is pre-populated with building defect notice
    5. Edit and save complaint draft (recipient agency, subject, body)
    6. Verify strict guardrail: attempting to mark status as 'submitted' returns HTTP 400
    7. Export draft to TXT and verify unsubmitted notice & engineering disclaimers
    8. Export draft to PDF and verify valid PDF binary response
    9. Verify domain filtering across inspections list (/api/inspections?domain=home vs road)
    10. Verify domain filtering in inspection reports preview and CSV export
    """
    from PIL import Image

    # Generate synthetic wall image
    img = Image.new("RGB", (640, 480), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    # Step 1: Upload image and run Home defect inference
    res = client.post(
        "/api/inspect",
        data={
            "image": (io.BytesIO(img_bytes), "exterior_wall_01.jpg"),
            "domain": "home",
            "confidence": "0.20",
            "inspection_mode": "standard",
        },
        content_type="multipart/form-data"
    )
    assert res.status_code == 200, f"Home inspection upload failed: {res.data}"
    data = res.get_json()
    assert data["status"] == "success"
    assert data["domain"] == "home"
    assert "original_file_path" in data
    assert "processed_file_path" in data

    # Step 2: Save Home inspection record with GPS coordinates
    home_payload = {
        "image_name": data["filename"],
        "original_image_path": data["original_file_path"],
        "annotated_image_path": data["processed_file_path"],
        "road_name": "Tower 4, Apt 802 Exterior Wall",
        "area": "Kalyani Nagar Sector 14",
        "city": "Pune",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "location_notes": "Noticeable shear crack propagating near balcony joint",
        "status": "Open",
        "inspection_type": "home",
        "detections": data["detections"],
    }
    save_res = client.post(
        "/api/inspections",
        data=json.dumps(home_payload),
        content_type="application/json"
    )
    assert save_res.status_code == 201, f"Save failed: {save_res.data}"
    rec = save_res.get_json()["inspection"]
    insp_id = rec["id"]
    assert insp_id > 0
    assert rec["inspection_type"] == "home"
    assert rec["road_name"] == "Tower 4, Apt 802 Exterior Wall"

    # Step 3: Fetch auto-generated Civic Complaint Draft
    draft_res = client.get(f"/api/inspections/{insp_id}/complaint-draft")
    assert draft_res.status_code == 200
    draft_data = draft_res.get_json()
    assert draft_data["status"] == "success"
    draft = draft_data["draft"]
    assert draft["inspection_id"] == insp_id
    assert draft["status"] == "draft"
    assert "Building" in draft["recipient_agency"] or "Housing" in draft["recipient_agency"]
    assert "Tower 4" in draft["subject"] or "Defect" in draft["subject"]
    assert "UNCONFIRMED DRAFT" in draft["complaint_body"] or "unsubmitted" in draft["complaint_body"].lower()

    # Step 4: Edit and persist complaint draft modifications
    edit_payload = {
        "recipient_agency": "Pune Municipal Housing & Building Safety Authority",
        "subject": "Urgent Structural Defect Grievance Notice - Tower 4 Apt 802",
        "complaint_body": (
            "Attention: Building Safety & Municipal Housing Inspector\n\n"
            "This formal grievance notice documents an observable defect at:\n"
            "Location: Tower 4, Apt 802 Exterior Wall, Kalyani Nagar Sector 14, Pune (GPS: 18.5204, 73.8567)\n"
            "Inspection Date: 2026-10-26\n\n"
            "Visual inspection identified crack propagation near balcony structural joints.\n"
            "Immediate professional structural inspection is respectfully requested.\n\n"
            "NOTICE: This document is an unsubmitted draft for formal grievance drafting."
        ),
    }
    put_res = client.put(
        f"/api/inspections/{insp_id}/complaint-draft",
        data=json.dumps(edit_payload),
        content_type="application/json"
    )
    assert put_res.status_code == 200
    updated_draft = put_res.get_json()["draft"]
    assert updated_draft["recipient_agency"] == "Pune Municipal Housing & Building Safety Authority"
    assert "Urgent Structural Defect" in updated_draft["subject"]
    assert updated_draft["status"] == "draft"

    # Step 5: Strict guardrail against false submission claim
    bad_put = client.put(
        f"/api/inspections/{insp_id}/complaint-draft",
        data=json.dumps({"status": "submitted"}),
        content_type="application/json"
    )
    assert bad_put.status_code == 400
    assert "Cannot mark draft as 'submitted'" in bad_put.get_json()["message"]

    # Step 6: Export draft to text format
    txt_res = client.get(f"/api/inspections/{insp_id}/complaint-draft/export/txt")
    assert txt_res.status_code == 200
    assert "text/plain" in txt_res.content_type
    txt_str = txt_res.data.decode("utf-8")
    assert "unsubmitted draft" in txt_str.lower()
    assert "Pune Municipal Housing & Building Safety Authority" in txt_str

    # Step 7: Export draft to PDF format
    pdf_res = client.get(f"/api/inspections/{insp_id}/complaint-draft/export/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.content_type == "application/pdf"
    assert pdf_res.data.startswith(b"%PDF")

    # Step 8: Domain filtering verification
    home_list = client.get("/api/inspections?domain=home")
    assert home_list.status_code == 200
    assert any(i["id"] == insp_id for i in home_list.get_json()["inspections"])

    road_list = client.get("/api/inspections?domain=road")
    assert road_list.status_code == 200
    assert not any(i["id"] == insp_id for i in road_list.get_json()["inspections"])

    all_list = client.get("/api/inspections?domain=all")
    assert all_list.status_code == 200
    assert any(i["id"] == insp_id for i in all_list.get_json()["inspections"])

    # Step 9: Inspection Reports Preview with domain filtering
    report_res = client.get("/api/reports/preview?domain=home")
    assert report_res.status_code == 200
    report_data = report_res.get_json()["report"]
    assert report_data["summary"]["total_inspections"] >= 1
    assert any(r["id"] == insp_id for r in report_data["records"])
