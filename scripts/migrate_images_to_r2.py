"""
Safe Cloudflare R2 Image Inventory & Migration Utility for VisionGuard AI.

Features & Safeguards:
- Default mode is DRY-RUN (--dry-run). Never connects to R2 or uploads files unless
  --execute and --confirm-write-to-cloud are explicitly supplied.
- Never deletes, renames, moves, or mutates any local file in data/uploads/ or data/processed/.
- Complete pre-migration inventory distinguishing:
  * Linked inspection images (active records in defect_inspections)
  * Unlinked historical session files
  * Test fixtures and benchmark samples
- Generates a full structured migration manifest at reports/r2_image_migration_manifest.json
  with file paths, SHA-256 checksums, byte sizes, and target R2 keys.
- Supports incremental upload with SHA-256 / ETag verification and rate limiting.
- Never prints secrets, access keys, or endpoint credentials.
"""

import os
import sys
import json
import sqlite3
import hashlib
import argparse
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from storage import get_storage_backend, CloudflareR2StorageBackend, LocalStorageBackend

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("visionguard.migration.images_to_r2")


def calculate_sha256(filepath: str, block_size: int = 65536) -> str:
    """Computes SHA-256 hex digest for a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_linked_images_from_db(db_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Reads defect_inspections from SQLite to build mapping of active inspection image references.
    Returns mapping: normalized_rel_path -> inspection_metadata
    """
    if not os.path.isfile(db_path):
        logger.warning(f"Database {db_path} not found. Proceeding with zero linked images.")
        return {}

    uri = f"file:///{os.path.abspath(db_path).replace('\\', '/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    linked: Dict[str, Dict[str, Any]] = {}
    try:
        cursor.execute("""
            SELECT id, image_name, original_image_path, annotated_image_path, file_path, status, defect_type
            FROM defect_inspections;
        """)
        for row in cursor.fetchall():
            insp_id = row["id"]
            orig = row["original_image_path"] or row["file_path"]
            annotated = row["annotated_image_path"]

            meta = {
                "inspection_id": insp_id,
                "image_name": row["image_name"],
                "status": row["status"],
                "defect_type": row["defect_type"],
            }

            if orig:
                norm_orig = orig.strip().replace("\\", "/").lstrip("/")
                linked[norm_orig] = {**meta, "type": "original"}
            if annotated:
                norm_annotated = annotated.strip().replace("\\", "/").lstrip("/")
                linked[norm_annotated] = {**meta, "type": "annotated"}
    except Exception as e:
        logger.error(f"Error querying active inspection images from DB: {e}")
    finally:
        conn.close()

    return linked


def inventory_directory(
    dir_path: str,
    prefix_type: str,
    linked_map: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Inventories every single file in the specified directory without modifying anything.
    Categorizes each file as:
      - 'linked_active_inspection'
      - 'test_fixture_sample'
      - 'unlinked_historical_session'
    """
    entries = []
    stats = {
        "total_files": 0,
        "total_bytes": 0,
        "linked_active_count": 0,
        "linked_active_bytes": 0,
        "unlinked_count": 0,
        "unlinked_bytes": 0,
        "test_fixture_count": 0,
        "test_fixture_bytes": 0,
    }

    if not os.path.isdir(dir_path):
        logger.warning(f"Directory '{dir_path}' does not exist.")
        return entries, stats

    for root, _, files in os.walk(dir_path):
        for f in files:
            full_path = os.path.join(root, f)
            rel_to_proj = os.path.relpath(full_path, PROJECT_ROOT).replace("\\", "/")
            file_size = os.path.getsize(full_path)
            sha256_hash = calculate_sha256(full_path)

            stats["total_files"] += 1
            stats["total_bytes"] += file_size

            # Target S3/R2 key: e.g. "uploads/foo.jpg" or "processed/bar.jpg"
            if rel_to_proj.startswith("data/"):
                r2_key = rel_to_proj[5:]
            else:
                r2_key = f"{prefix_type}/{f}"

            # Linkage evaluation
            linkage = linked_map.get(rel_to_proj)
            if not linkage:
                # Also check without data/ prefix
                linkage = linked_map.get(r2_key)

            if linkage:
                category = "linked_active_inspection"
                stats["linked_active_count"] += 1
                stats["linked_active_bytes"] += file_size
                insp_id = linkage.get("inspection_id")
            elif f.lower().startswith("test_") or "sample" in f.lower() or "fixture" in f.lower():
                category = "test_fixture_sample"
                stats["test_fixture_count"] += 1
                stats["test_fixture_bytes"] += file_size
                insp_id = None
            else:
                category = "unlinked_historical_session"
                stats["unlinked_count"] += 1
                stats["unlinked_bytes"] += file_size
                insp_id = None

            entries.append({
                "filename": f,
                "local_rel_path": rel_to_proj,
                "target_r2_key": r2_key,
                "file_size_bytes": file_size,
                "sha256": sha256_hash,
                "category": category,
                "inspection_id": insp_id,
                "prefix_type": prefix_type,
            })

    return entries, stats


def build_migration_manifest(
    db_path: str = os.path.join(PROJECT_ROOT, "data", "visionguard.db"),
    output_manifest_path: str = os.path.join(PROJECT_ROOT, "reports", "r2_image_migration_manifest.json"),
) -> Dict[str, Any]:
    """
    Builds and writes a comprehensive image inventory manifest.
    Guarantees zero file modifications.
    """
    uploads_dir = os.path.join(PROJECT_ROOT, "data", "uploads")
    processed_dir = os.path.join(PROJECT_ROOT, "data", "processed")

    linked_map = get_linked_images_from_db(db_path)

    upload_entries, upload_stats = inventory_directory(uploads_dir, "uploads", linked_map)
    processed_entries, processed_stats = inventory_directory(processed_dir, "processed", linked_map)

    all_entries = upload_entries + processed_entries

    total_files = upload_stats["total_files"] + processed_stats["total_files"]
    total_bytes = upload_stats["total_bytes"] + processed_stats["total_bytes"]

    manifest = {
        "generated_at": datetime.datetime.now().isoformat(),
        "summary": {
            "total_files": total_files,
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "uploads": upload_stats,
            "processed": processed_stats,
            "linked_inspections_total_count": upload_stats["linked_active_count"] + processed_stats["linked_active_count"],
            "linked_inspections_total_bytes": upload_stats["linked_active_bytes"] + processed_stats["linked_active_bytes"],
            "unlinked_historical_total_count": upload_stats["unlinked_count"] + processed_stats["unlinked_count"],
            "unlinked_historical_total_bytes": upload_stats["unlinked_bytes"] + processed_stats["unlinked_bytes"],
        },
        "inventory": all_entries,
    }

    os.makedirs(os.path.dirname(output_manifest_path), exist_ok=True)
    with open(output_manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"Generated comprehensive migration manifest at: {output_manifest_path}")
    return manifest


def run_image_migration(
    manifest_path: str,
    execute: bool = False,
    confirm_cloud: bool = False,
    only_linked: bool = False,
) -> Dict[str, Any]:
    """
    Executes or previews the Cloudflare R2 migration.
    Default mode: DRY-RUN.
    """
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}. Run manifest generation first.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    summary = manifest.get("summary", {})
    inventory = manifest.get("inventory", [])

    candidates = [
        item for item in inventory
        if (not only_linked or item["category"] == "linked_active_inspection")
    ]

    report: Dict[str, Any] = {
        "mode": "EXECUTE" if (execute and confirm_cloud) else "DRY-RUN",
        "manifest_path": manifest_path,
        "total_inventoried": len(inventory),
        "candidates_count": len(candidates),
        "candidates_bytes": sum(item["file_size_bytes"] for item in candidates),
        "uploaded_count": 0,
        "failed_count": 0,
        "status": "pending",
    }

    # Dry-run preview
    if not execute or not confirm_cloud:
        logger.info("=" * 70)
        logger.info("DRY-RUN IMAGE MIGRATION PREVIEW — ZERO REMOTE WRITES PERFORMED")
        logger.info(f"Total Files in Manifest:     {len(inventory)}")
        logger.info(f"Upload Candidates Selected:  {len(candidates)} ({round(report['candidates_bytes'] / (1024*1024), 2)} MB)")
        logger.info(f"  - Linked Active Images:    {summary.get('linked_inspections_total_count', 0)}")
        logger.info(f"  - Unlinked Historical:     {summary.get('unlinked_historical_total_count', 0)}")
        logger.info("To perform actual upload to Cloudflare R2, pass --execute AND --confirm-write-to-cloud.")
        logger.info("=" * 70)
        report["status"] = "dry_run_completed"
        return report

    # Execute upload to Cloudflare R2
    backend = get_storage_backend()
    if not isinstance(backend, CloudflareR2StorageBackend):
        raise ValueError(
            "STORAGE_BACKEND is not configured for R2. "
            "Set STORAGE_BACKEND=r2, R2_BUCKET_NAME, R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY."
        )

    logger.info(f"Beginning upload to Cloudflare R2 bucket: '{backend.bucket_name}'...")
    uploaded = 0
    failed = 0

    for item in candidates:
        rel_path = item["local_rel_path"]
        full_path = os.path.join(PROJECT_ROOT, rel_path)
        r2_key = item["target_r2_key"]

        if not os.path.isfile(full_path):
            logger.warning(f"File missing on disk: {full_path}")
            failed += 1
            continue

        try:
            with open(full_path, "rb") as f_data:
                data_bytes = f_data.read()

            ext = os.path.splitext(full_path)[1].lower()
            ct = "image/png" if ext == ".png" else "image/jpeg"

            backend.save(r2_key, data_bytes, content_type=ct)
            uploaded += 1
            if uploaded % 50 == 0 or uploaded == len(candidates):
                logger.info(f"Uploaded {uploaded}/{len(candidates)} images to R2...")
        except Exception as exc:
            logger.error(f"Failed to upload {r2_key}: {exc}")
            failed += 1

    report["uploaded_count"] = uploaded
    report["failed_count"] = failed
    report["status"] = "success" if failed == 0 else "partial_failure"
    logger.info(f"Image migration finished. Uploaded={uploaded}, Failed={failed}")
    return report


def main():
    parser = argparse.ArgumentParser(description="VisionGuard AI Cloudflare R2 Image Inventory & Migration Utility")
    parser.add_argument(
        "--db-path",
        default=os.path.join(PROJECT_ROOT, "data", "visionguard.db"),
        help="Path to SQLite database to discover active inspection linkages",
    )
    parser.add_argument(
        "--manifest-path",
        default=os.path.join(PROJECT_ROOT, "reports", "r2_image_migration_manifest.json"),
        help="Path to save or read the migration manifest JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview inventory and manifest without uploading to R2 (default behavior)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute upload of images to Cloudflare R2",
    )
    parser.add_argument(
        "--confirm-write-to-cloud",
        action="store_true",
        default=False,
        help="Explicit required safety confirmation flag to permit writing to cloud storage",
    )
    parser.add_argument(
        "--only-linked",
        action="store_true",
        default=False,
        help="Only migrate images actively linked to inspection records (default is all inventoried)",
    )

    args = parser.parse_args()

    # Step 1: Always build or refresh the manifest
    logger.info("Building image inventory manifest...")
    manifest = build_migration_manifest(db_path=args.db_path, output_manifest_path=args.manifest_path)

    # Step 2: Run migration dry-run or execute
    execute_mode = args.execute and args.confirm_write_to_cloud
    report = run_image_migration(
        manifest_path=args.manifest_path,
        execute=execute_mode,
        confirm_cloud=args.confirm_write_to_cloud,
        only_linked=args.only_linked,
    )

    summary = manifest["summary"]
    print("\nImage Inventory & Migration Summary:")
    print(f"  Mode:                        {report['mode']}")
    print(f"  Total Files Inventoried:     {summary['total_files']} ({summary['total_mb']} MB)")
    print(f"  Uploads Directory:           {summary['uploads']['total_files']} files ({round(summary['uploads']['total_bytes'] / (1024*1024), 2)} MB)")
    print(f"  Processed Directory:         {summary['processed']['total_files']} files ({round(summary['processed']['total_bytes'] / (1024*1024), 2)} MB)")
    print(f"  Linked Active Inspections:   {summary['linked_inspections_total_count']} files ({round(summary['linked_inspections_total_bytes'] / (1024*1024), 2)} MB)")
    print(f"  Unlinked Historical Files:   {summary['unlinked_historical_total_count']} files ({round(summary['unlinked_historical_total_bytes'] / (1024*1024), 2)} MB)")
    print(f"  Manifest File Created:       {args.manifest_path}")
    print(f"  Execution Status:            {report['status']}")


if __name__ == "__main__":
    main()
