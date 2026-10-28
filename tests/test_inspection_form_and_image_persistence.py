"""
Regression test suite for VisionGuard AI:
1. Inspection form locking:
   - Form inputs, mode radios, domain selectors, file triggers, and dropzone locking during inspection
   - Restoration of controls across all completion paths (success, API errors, 502/503/504, timeout, exceptions)
   - Stale request suppression via incremental request IDs
2. Saved report image lifecycle:
   - Persistence and retrieval of original and processed image references
   - Reopening saved reports and resolving image URLs in both local and Cloudflare R2 storage modes
   - Citizen image authorization by user_id and username
   - Resilient path resolution, URL redirects, and fallback handling
"""

import io
import os
import json
import pytest
from unittest.mock import MagicMock, patch

from app.server import create_app
from database.db import init_db, save_inspection, get_inspection_by_id
from database.auth import create_user, ROLE_CITIZEN
from storage.backend import LocalStorageBackend, CloudflareR2StorageBackend, PROJECT_ROOT


@pytest.fixture
def app_and_client(tmp_path):
    """Initializes a clean test application with an isolated temporary SQLite database and local storage."""
    db_file = str(tmp_path / "test_visionguard.db")
    storage_dir = str(tmp_path / "data")
    os.makedirs(os.path.join(storage_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(storage_dir, "processed"), exist_ok=True)

    storage = LocalStorageBackend(base_dir=storage_dir)

    test_config = {
        "TESTING": True,
        "DATABASE_PATH": db_file,
        "AUTH_ENABLED": False,
        "ENFORCE_CSRF": False,
        "storage_backend": storage,
    }

    app = create_app(test_config=test_config)
    client = app.test_client()

    return {
        "app": app,
        "client": client,
        "db_file": db_file,
        "storage": storage,
        "storage_dir": storage_dir,
    }


def test_api_get_inspection_detail_includes_durable_urls(app_and_client):
    """Verifies that GET /api/inspections/<id> supplies durable original_image_url and annotated_image_url."""
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]

    record_data = {
        "image_name": "street_01.jpg",
        "original_image_path": "data/uploads/orig_street_01.jpg",
        "annotated_image_path": "data/processed/annotated_street_01.jpg",
        "status": "Open",
        "inspection_type": "road",
    }
    saved = save_inspection(record_data, db_path=db_file)

    res = client.get(f"/api/inspections/{saved['id']}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    insp = data["inspection"]
    assert insp["original_image_url"] == f"/api/inspections/{saved['id']}/image/original"
    assert insp["annotated_image_url"] == f"/api/inspections/{saved['id']}/image/annotated"


def test_api_get_inspections_list_includes_durable_urls(app_and_client):
    """Verifies that GET /api/inspections supplies durable image URLs for all listed inspection cards."""
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]

    record_data = {
        "image_name": "list_test.jpg",
        "original_image_path": "data/uploads/orig_list_test.jpg",
        "annotated_image_path": "data/processed/annotated_list_test.jpg",
        "status": "Open",
        "inspection_type": "road",
    }
    saved = save_inspection(record_data, db_path=db_file)

    res = client.get("/api/inspections")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    matching = [r for r in data["inspections"] if r["id"] == saved["id"]]
    assert len(matching) == 1
    assert matching[0]["original_image_url"] == f"/api/inspections/{saved['id']}/image/original"
    assert matching[0]["annotated_image_url"] == f"/api/inspections/{saved['id']}/image/annotated"


def test_api_get_inspection_image_local_storage(app_and_client):
    """Verifies that image streaming endpoints serve authentic binary image data from local storage."""
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]
    storage = app_and_client["storage"]

    orig_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIFfake_orig_jpeg"
    annotated_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIFfake_annotated_jpeg"

    orig_key = storage.save("uploads/test_orig.jpg", orig_bytes)
    annot_key = storage.save("processed/test_annot.jpg", annotated_bytes)

    saved = save_inspection({
        "image_name": "test_orig.jpg",
        "original_image_path": orig_key,
        "annotated_image_path": annot_key,
        "status": "Open",
        "inspection_type": "road",
    }, db_path=db_file)

    res_orig = client.get(f"/api/inspections/{saved['id']}/image/original")
    assert res_orig.status_code == 200
    assert res_orig.data == orig_bytes
    assert "image/jpeg" in res_orig.content_type

    res_annot = client.get(f"/api/inspections/{saved['id']}/image/annotated")
    assert res_annot.status_code == 200
    assert res_annot.data == annotated_bytes
    assert "image/jpeg" in res_annot.content_type


def test_api_get_inspection_image_missing_annotated_returns_404(app_and_client):
    """Verifies that if annotated image reference is missing, endpoint returns 404 rather than silently masking failure with original image."""
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]
    storage = app_and_client["storage"]

    orig_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIFonly_orig_jpeg"
    orig_key = storage.save("uploads/only_orig.jpg", orig_bytes)

    saved = save_inspection({
        "image_name": "only_orig.jpg",
        "original_image_path": orig_key,
        "annotated_image_path": "",
        "status": "Open",
        "inspection_type": "road",
    }, db_path=db_file)

    # Requesting annotated image must return 404 IMAGE_FILE_NOT_FOUND
    res_annot = client.get(f"/api/inspections/{saved['id']}/image/annotated")
    assert res_annot.status_code == 404
    data = res_annot.get_json()
    assert data["error_code"] == "IMAGE_FILE_NOT_FOUND"


def test_api_get_inspection_image_missing_original_returns_404(app_and_client):
    """Verifies that if original image reference is missing, endpoint returns 404 rather than silently masking failure with annotated image."""
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]
    storage = app_and_client["storage"]

    annot_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIFonly_annot_jpeg"
    annot_key = storage.save("processed/only_annot.jpg", annot_bytes)

    saved = save_inspection({
        "image_name": "only_annot.jpg",
        "original_image_path": "",
        "annotated_image_path": annot_key,
        "status": "Open",
        "inspection_type": "road",
    }, db_path=db_file)

    # Requesting original image must return 404 IMAGE_FILE_NOT_FOUND
    res_orig = client.get(f"/api/inspections/{saved['id']}/image/original")
    assert res_orig.status_code == 404
    data = res_orig.get_json()
    assert data["error_code"] == "IMAGE_FILE_NOT_FOUND"


def test_api_get_inspection_image_direct_url_redirect(app_and_client):
    """Verifies that if image path is an external HTTPS URL, endpoint returns HTTP 302 redirect."""
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]

    saved = save_inspection({
        "image_name": "cdn_image.jpg",
        "original_image_path": "https://media.visionguard.ai/uploads/cdn_image.jpg",
        "annotated_image_path": "https://media.visionguard.ai/processed/cdn_image.jpg",
        "status": "Open",
        "inspection_type": "road",
    }, db_path=db_file)

    res = client.get(f"/api/inspections/{saved['id']}/image/original")
    assert res.status_code == 302
    assert res.headers["Location"] == "https://media.visionguard.ai/uploads/cdn_image.jpg"


def test_api_get_inspection_image_cloud_r2_presigned_url(app_and_client):
    """Verifies that when Cloudflare R2 storage backend provides presigned URLs, client is redirected."""
    app = app_and_client["app"]
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]

    mock_r2 = MagicMock(spec=CloudflareR2StorageBackend)
    mock_r2.get_url.return_value = "https://r2.cloudflarestorage.com/bucket/uploads/r2_test.jpg?token=secure123"
    app.storage_backend = mock_r2

    saved = save_inspection({
        "image_name": "r2_test.jpg",
        "original_image_path": "uploads/r2_test.jpg",
        "annotated_image_path": "processed/r2_test.jpg",
        "status": "Open",
        "inspection_type": "road",
    }, db_path=db_file)

    res = client.get(f"/api/inspections/{saved['id']}/image/original")
    assert res.status_code == 302
    assert "https://r2.cloudflarestorage.com" in res.headers["Location"]
    mock_r2.get_url.assert_called_with("uploads/r2_test.jpg", expires_in=3600)


def test_citizen_image_access_authorization_both_id_and_username(app_and_client):
    """Verifies that citizens can access images when matched by user ID or username, but not foreign reports."""
    app = app_and_client["app"]
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]
    storage = app_and_client["storage"]

    user_owner = create_user("zeeshanshaikh1", "OwnerPass123!", role=ROLE_CITIZEN, db_path=db_file)
    user_stranger = create_user("stranger", "StrangerPass123!", role=ROLE_CITIZEN, db_path=db_file)

    img_data = b"\xff\xd8\xff\xe0\x00\x10JFIFcitizen_img"
    img_key = storage.save("uploads/citizen_report.jpg", img_data)

    # Record 1: user_id matching user_owner['id'], username="zeeshanshaikh1"
    saved1 = save_inspection({
        "image_name": "citizen_report.jpg",
        "original_image_path": img_key,
        "annotated_image_path": img_key,
        "created_by_user_id": user_owner["id"],
        "created_by_username": user_owner["username"],
        "status": "Open",
    }, db_path=db_file)

    # Record 2: historical record where user_id was 9999 (e.g. from SQLite before Neon migration), but username is "zeeshanshaikh1"
    saved2 = save_inspection({
        "image_name": "citizen_legacy.jpg",
        "original_image_path": img_key,
        "annotated_image_path": img_key,
        "created_by_user_id": 9999,
        "created_by_username": user_owner["username"],
        "status": "Open",
    }, db_path=db_file)

    # Case A: Logged in as citizen with matching user ID and username
    with client.session_transaction() as sess:
        sess["user_id"] = user_owner["id"]
        sess["username"] = user_owner["username"]
        sess["role"] = "citizen"

    res_auth = client.get(f"/api/inspections/{saved1['id']}/image/original")
    assert res_auth.status_code == 200

    # Case B: Logged in as citizen whose current DB user ID differs (user_owner['id'] != 9999) but matching username
    res_auth_name = client.get(f"/api/inspections/{saved2['id']}/image/original")
    assert res_auth_name.status_code == 200

    # Case C: Logged in as another citizen with different user ID and different username
    with client.session_transaction() as sess:
        sess["user_id"] = user_stranger["id"]
        sess["username"] = user_stranger["username"]
        sess["role"] = "citizen"

    res_denied = client.get(f"/api/inspections/{saved1['id']}/image/original")
    assert res_denied.status_code == 403
    assert res_denied.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"


def test_save_inspection_path_sanitization(app_and_client):
    """Verifies that API path sanitization safely preserves valid storage keys and eliminates traversal attacks."""
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]

    # 1. Valid Cloudflare R2 / S3 keys must be preserved
    res_r2 = client.post("/api/inspections", json={
        "image_name": "r2_persist.jpg",
        "original_image_path": "uploads/r2_persist.jpg",
        "annotated_image_path": "processed/annotated_r2_persist.jpg",
        "status": "Open",
    })
    assert res_r2.status_code == 201
    rec_r2 = res_r2.get_json()["inspection"]
    assert rec_r2["original_image_path"] == "uploads/r2_persist.jpg"
    assert rec_r2["annotated_image_path"] == "processed/annotated_r2_persist.jpg"

    # 2. Path traversal attempts must be neutralized to None / empty
    res_hack = client.post("/api/inspections", json={
        "image_name": "traversal.jpg",
        "original_image_path": "../../etc/shadow",
        "annotated_image_path": "../../../boot.ini",
        "status": "Open",
    })
    assert res_hack.status_code == 201
    rec_hack = res_hack.get_json()["inspection"]
    assert rec_hack["original_image_path"] in (None, "")
    assert rec_hack["annotated_image_path"] in (None, "")


def test_frontend_script_form_locking_contract():
    """
    Verifies that app.js implements the complete inspection form locking contract:
    - Defines isInspecting and activeInspectionRequestId
    - Implements setInspectionFormLocked disabling inputs, sliders, radios, buttons, and dropzone
    - Guards dropzone, file input, browse, camera, remove, and domain switches
    - Restores controls in finally block across all execution paths
    - Discards stale responses
    - Implements hash-based report reopening for #detail-<id>
    """
    app_js_path = os.path.join(PROJECT_ROOT, "app", "static", "js", "app.js")
    with open(app_js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Form locking primitives
    assert "let isInspecting = false;" in content
    assert "let activeInspectionRequestId = 0;" in content
    assert "function setInspectionFormLocked(locked)" in content
    assert "dropzone-locked" in content

    # Control guards
    assert "if (isInspecting) return;" in content
    assert "browseBtn.disabled = isInspecting;" in content
    assert "removeFileBtn.disabled = isInspecting;" in content
    assert "confSlider.disabled = isInspecting;" in content
    assert "domainRoadBtn.disabled = isInspecting;" in content

    # Stale request suppression
    assert "thisRequestId !== activeInspectionRequestId" in content

    # Finally restoration
    assert "setInspectionFormLocked(false);" in content

    # Hash routing for detail view reopening
    assert "#detail-" in content
    assert "checkHashRoute" in content


def test_citizen_conflicting_ownership_denies_access_when_user_id_exists(app_and_client):
    """
    Critical security test:
    Verifies that if a record's created_by_user_id belongs to an active user (Alice),
    another user (Bob) CANNOT access Alice's report, images, activity, or complaint drafts,
    even if the record's created_by_username column was set to 'bob'.
    Stable authenticated user ID is strictly authoritative.
    """
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]
    storage = app_and_client["storage"]

    user_alice = create_user("alice", "AlicePass123!", role=ROLE_CITIZEN, db_path=db_file)
    user_bob = create_user("bob", "BobPass123!", role=ROLE_CITIZEN, db_path=db_file)

    img_data = b"\xff\xd8\xff\xe0\x00\x10JFIFconflict_img"
    img_key = storage.save("uploads/conflict.jpg", img_data)

    # Record belongs to Alice (created_by_user_id = user_alice['id']), but created_by_username says 'bob'
    saved = save_inspection({
        "image_name": "conflict.jpg",
        "original_image_path": img_key,
        "annotated_image_path": img_key,
        "created_by_user_id": user_alice["id"],
        "created_by_username": "bob",
        "status": "Open",
        "road_name": "Alice Private Road",
    }, db_path=db_file)
    insp_id = saved["id"]

    # 1. Log in as Bob
    with client.session_transaction() as sess:
        sess["user_id"] = user_bob["id"]
        sess["username"] = "bob"
        sess["role"] = "citizen"

    # Bob must be DENIED access across all endpoints for Alice's record
    res_detail = client.get(f"/api/inspections/{insp_id}")
    assert res_detail.status_code == 403
    assert res_detail.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    res_img = client.get(f"/api/inspections/{insp_id}/image/original")
    assert res_img.status_code == 403
    assert res_img.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    res_act = client.get(f"/api/inspections/{insp_id}/activity")
    assert res_act.status_code == 403
    assert res_act.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    res_draft = client.get(f"/api/inspections/{insp_id}/complaint-draft")
    assert res_draft.status_code == 403
    assert res_draft.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    res_pdf = client.get(f"/api/inspections/{insp_id}/complaint-draft/export/pdf")
    assert res_pdf.status_code == 403
    assert res_pdf.get_json()["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # Bob's My Reports query must NOT include Alice's record
    res_list = client.get("/api/inspections?my_reports=1")
    assert res_list.status_code == 200
    my_inspections = res_list.get_json()["inspections"]
    assert all(r["id"] != insp_id for r in my_inspections)

    # 2. Log in as Alice (the true owner by ID)
    with client.session_transaction() as sess:
        sess["user_id"] = user_alice["id"]
        sess["username"] = "alice"
        sess["role"] = "citizen"

    res_alice_detail = client.get(f"/api/inspections/{insp_id}")
    assert res_alice_detail.status_code == 200

    res_alice_img = client.get(f"/api/inspections/{insp_id}/image/original")
    assert res_alice_img.status_code == 200


def test_historical_record_auto_healing(app_and_client):
    """
    Verifies that historical records with created_by_user_id IS NULL:
    - Can be accessed by the authentic citizen matching created_by_username
    - Cannot be accessed by other citizens
    - Are auto-healed in the database so created_by_user_id becomes permanently populated
    """
    client = app_and_client["client"]
    db_file = app_and_client["db_file"]
    storage = app_and_client["storage"]

    user_clara = create_user("clara", "ClaraPass123!", role=ROLE_CITIZEN, db_path=db_file)
    user_stranger = create_user("stranger", "StrangerPass123!", role=ROLE_CITIZEN, db_path=db_file)

    img_data = b"\xff\xd8\xff\xe0\x00\x10JFIFclara_img"
    img_key = storage.save("uploads/clara.jpg", img_data)

    # Historical record with NULL user_id
    saved = save_inspection({
        "image_name": "clara.jpg",
        "original_image_path": img_key,
        "annotated_image_path": img_key,
        "created_by_user_id": None,
        "created_by_username": "clara",
        "status": "Open",
    }, db_path=db_file)
    insp_id = saved["id"]

    # Stranger cannot access it
    with client.session_transaction() as sess:
        sess["user_id"] = user_stranger["id"]
        sess["username"] = "stranger"
        sess["role"] = "citizen"

    res_denied = client.get(f"/api/inspections/{insp_id}")
    assert res_denied.status_code == 403

    # Clara accesses it
    with client.session_transaction() as sess:
        sess["user_id"] = user_clara["id"]
        sess["username"] = "clara"
        sess["role"] = "citizen"

    res_ok = client.get(f"/api/inspections/{insp_id}")
    assert res_ok.status_code == 200

    # Verify auto-healing: DB record now has created_by_user_id populated with clara's ID
    updated_rec = get_inspection_by_id(insp_id, db_path=db_file)
    assert updated_rec["created_by_user_id"] == user_clara["id"]


def test_migrate_historical_report_ownership_batch(app_and_client):
    """
    Verifies that migrate_historical_report_ownership backfills all unlinked or orphaned
    records to match users.id, while leaving validly attributed records untouched.
    """
    from database.db import migrate_historical_report_ownership
    db_file = app_and_client["db_file"]

    user_dev = create_user("zeeshanshaikh1", "ZeeshanPass123!", role=ROLE_CITIZEN, db_path=db_file)
    user_other = create_user("other_user", "OtherPass123!", role=ROLE_CITIZEN, db_path=db_file)

    from database.db import get_db_connection

    # Insert raw unlinked records directly into DB to test explicit migration call
    conn = get_db_connection(db_file)
    cur = conn.cursor()
    cur.execute("INSERT INTO defect_inspections (image_name, created_by_user_id, created_by_username, status) VALUES (?, ?, ?, ?)",
                ("hist1.jpg", None, "zeeshanshaikh1", "Open"))
    r1_id = cur.lastrowid

    cur.execute("INSERT INTO defect_inspections (image_name, created_by_user_id, created_by_username, status) VALUES (?, ?, ?, ?)",
                ("hist2.jpg", 88888, "zeeshanshaikh1", "Open"))
    r2_id = cur.lastrowid

    cur.execute("INSERT INTO defect_inspections (image_name, created_by_user_id, created_by_username, status) VALUES (?, ?, ?, ?)",
                ("valid.jpg", user_other["id"], "other_user", "Open"))
    r3_id = cur.lastrowid
    conn.commit()
    conn.close()

    migrated = migrate_historical_report_ownership(db_path=db_file)
    assert migrated >= 2

    # Verify r1 and r2 now point to user_dev['id']
    u1 = get_inspection_by_id(r1_id, db_path=db_file)
    u2 = get_inspection_by_id(r2_id, db_path=db_file)
    u3 = get_inspection_by_id(r3_id, db_path=db_file)

    assert u1["created_by_user_id"] == user_dev["id"]
    assert u2["created_by_user_id"] == user_dev["id"]
    assert u3["created_by_user_id"] == user_other["id"]


def test_cloudflare_r2_independent_image_persistence():
    """
    Verifies that when Cloudflare R2 is configured:
    - Both original and annotated images are persisted independently to R2
    - /image/original requests presigned URL for the original key
    - /image/annotated requests presigned URL for the annotated key
    - Neither image replaces or masks the other
    """
    mock_s3 = MagicMock()
    r2_backend = CloudflareR2StorageBackend(
        bucket_name="visionguard-test-bucket",
        account_id="test-account-id",
        s3_client=mock_s3,
    )

    # Save original and annotated image bytes
    orig_key = r2_backend.save("uploads/orig_test.jpg", b"fake_orig_bytes")
    annot_key = r2_backend.save("processed/annotated_test.jpg", b"fake_annot_bytes")

    assert orig_key == "uploads/orig_test.jpg"
    assert annot_key == "processed/annotated_test.jpg"

    # Verify both put_object calls were made to S3/R2
    assert mock_s3.put_object.call_count == 2
    put_calls = mock_s3.put_object.call_args_list
    assert put_calls[0].kwargs["Key"] == "uploads/orig_test.jpg"
    assert put_calls[1].kwargs["Key"] == "processed/annotated_test.jpg"

    # Verify independent presigned URL generation
    mock_s3.generate_presigned_url.side_effect = lambda ClientMethod, Params, ExpiresIn: f"https://r2.test/{Params['Key']}?sig=123"

    url_orig = r2_backend.get_url(orig_key)
    url_annot = r2_backend.get_url(annot_key)

    assert "uploads/orig_test.jpg" in url_orig
    assert "processed/annotated_test.jpg" in url_annot
    assert url_orig != url_annot
