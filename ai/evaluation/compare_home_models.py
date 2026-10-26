"""
Isolated evaluation and comparative analysis script for VisionGuard AI Home Defect models.

Enables side-by-side benchmarking of candidate Home model checkpoints (e.g. home_exp_a_test.pt)
against the production Home model (ai/models/home_best.pt) without modifying, renaming,
or overwriting production checkpoints.

Preserves strict isolation:
- Does NOT touch ai/models/home_best.pt or ai/models/best.pt.
- Compares predictions on identical representative images using identical inference parameters.
- Generates side-by-side visual comparison images and an analytical CSV.
"""

from typing import List, Dict, Any, Optional, Tuple
import argparse
import csv
import json
import os
import sys
import cv2
import numpy as np

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ai.detection.detector import (
    DefectDetectionService,
    HOME_CLASS_NAMES,
    HOME_CLASS_DISPLAY_NAMES,
    HOME_CLASS_COLORS_BGR,
    compute_box_iou,
)


def render_side_by_side_comparison(
    image_bgr: np.ndarray,
    baseline_dets: List[Dict[str, Any]],
    candidate_dets: Optional[List[Dict[str, Any]]],
    title: str,
    baseline_label: str = "Production Baseline (home_best.pt)",
    candidate_label: str = "Candidate (home_exp_a_test.pt)",
    missing_candidate_msg: Optional[str] = None,
) -> np.ndarray:
    """
    Renders a side-by-side visual comparison:
    Left: Baseline Model Detections
    Right: Candidate Model Detections (or Placeholder if Candidate Checkpoint is missing)
    """
    h, w = image_bgr.shape[:2]

    # Target display width per panel (keep aspect ratio or cap at 800px width for readability)
    panel_w = min(800, max(480, w))
    panel_h = int(round(h * (panel_w / w)))

    # Draw left panel
    left_annotated = DefectDetectionService.draw_annotations(
        image_bgr.copy(), baseline_dets, domain="home"
    )
    left_resized = cv2.resize(left_annotated, (panel_w, panel_h), interpolation=cv2.INTER_AREA)

    # Draw right panel
    if candidate_dets is not None:
        right_annotated = DefectDetectionService.draw_annotations(
            image_bgr.copy(), candidate_dets, domain="home"
        )
        right_resized = cv2.resize(right_annotated, (panel_w, panel_h), interpolation=cv2.INTER_AREA)
    else:
        # Candidate weights not present; render informational panel
        right_resized = cv2.resize(image_bgr.copy(), (panel_w, panel_h), interpolation=cv2.INTER_AREA)
        # Darken slightly to indicate pending/candidate placeholder
        overlay = right_resized.copy()
        cv2.rectangle(overlay, (0, 0), (panel_w, panel_h), (20, 20, 20), cv2.FILLED)
        right_resized = cv2.addWeighted(overlay, 0.45, right_resized, 0.55, 0)

        msg = missing_candidate_msg or "Candidate Checkpoint Missing"
        cv2.putText(
            right_resized,
            msg,
            (20, panel_h // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 215, 255),
            2,
            cv2.LINE_AA,
        )

    # Banner height
    header_h = 44
    combined_w = panel_w * 2 + 10  # 10px divider
    combined_h = panel_h + header_h

    canvas = np.zeros((combined_h, combined_w, 3), dtype=np.uint8)
    canvas[:] = (35, 35, 35)  # Dark slate background

    # Left header
    cv2.putText(
        canvas,
        f"{baseline_label} [{len(baseline_dets)} det]",
        (15, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )

    # Right header
    cand_count = len(candidate_dets) if candidate_dets is not None else "N/A"
    cv2.putText(
        canvas,
        f"{candidate_label} [{cand_count} det]",
        (panel_w + 20, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 215, 255) if candidate_dets is not None else (150, 150, 150),
        1,
        cv2.LINE_AA,
    )

    # Paste panels
    canvas[header_h : header_h + panel_h, 0:panel_w] = left_resized
    canvas[header_h : header_h + panel_h, panel_w + 10 : panel_w + 10 + panel_w] = right_resized

    return canvas


def run_home_model_comparison(
    baseline_path: str = "ai/models/home_best.pt",
    candidate_path: str = "ai/models/home_exp_a_test.pt",
    images_dir: str = "data/test_representative_home_defects",
    output_dir: str = "reports/evaluation_audit/home_model_comparison",
    conf_threshold: float = 0.20,
    inspection_mode: str = "standard",
    allow_missing_candidate: bool = False,
) -> Dict[str, Any]:
    """
    Executes isolated comparison between baseline and candidate home checkpoints.
    Requires both checkpoints to be valid YOLO models unless allow_missing_candidate is explicitly set.
    """
    os.makedirs(output_dir, exist_ok=True)
    images_out_dir = os.path.join(output_dir, "visual_comparisons")
    os.makedirs(images_out_dir, exist_ok=True)

    print("=" * 70)
    print("VisionGuard AI — Home Defect Model Comparative Evaluation")
    print("=" * 70)
    print(f"Baseline Checkpoint:  {baseline_path}")
    print(f"Candidate Checkpoint: {candidate_path}")
    print(f"Representative Suite: {images_dir}")
    print(f"Output Directory:     {output_dir}")
    print(f"Confidence Threshold: {conf_threshold:.2f}")
    print(f"Inspection Mode:      {inspection_mode}")
    print("-" * 70)

    # 1. Check baseline
    if not os.path.exists(baseline_path):
        raise FileNotFoundError(f"Baseline Home checkpoint not found at: {baseline_path}")

    baseline_detector = DefectDetectionService(model_path=baseline_path, domain="home")
    if not baseline_detector.is_loaded:
        raise RuntimeError(f"Failed to load baseline Home model from '{baseline_path}': {baseline_detector.status_message}")
    print(f" Baseline loaded: {baseline_path} (size: {os.path.getsize(baseline_path):,} bytes)")

    # 2. Check candidate
    candidate_present = os.path.exists(candidate_path)
    candidate_detector = None
    if not candidate_present:
        if not allow_missing_candidate:
            raise FileNotFoundError(
                f"Candidate Home checkpoint not found at '{candidate_path}'. "
                "Comparative evaluation cannot proceed without the candidate model. "
                "Do not silently skip candidate inference or report a successful comparison."
            )
        print(f"  [WARNING] Candidate checkpoint NOT found at '{candidate_path}' (allow_missing_candidate=True).")
        print("  Evaluating baseline only.")
    else:
        candidate_detector = DefectDetectionService(model_path=candidate_path, domain="home")
        if not candidate_detector.is_loaded:
            raise RuntimeError(
                f"Candidate checkpoint at '{candidate_path}' failed to load as a valid YOLO model: "
                f"{candidate_detector.status_message}"
            )
        print(f" Candidate loaded: {candidate_path} (size: {os.path.getsize(candidate_path):,} bytes)")

    # 3. Discover test images
    image_paths = []
    if os.path.isdir(images_dir):
        for fname in sorted(os.listdir(images_dir)):
            if fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                image_paths.append(os.path.join(images_dir, fname))

    if not image_paths:
        raise FileNotFoundError(f"No valid image files found in '{images_dir}'")

    print(f"\nProcessing {len(image_paths)} representative images...\n")

    csv_rows = []
    summary_stats = {
        "images_tested": len(image_paths),
        "baseline_detections_total": 0,
        "candidate_detections_total": 0 if candidate_detector else None,
        "baseline_by_class": {},
        "candidate_by_class": {} if candidate_detector else None,
        "per_image_results": [],
    }

    for idx, img_path in enumerate(image_paths, start=1):
        filename = os.path.basename(img_path)
        img_bgr = cv2.imread(img_path)
        if img_bgr is None:
            print(f"[{idx}/{len(image_paths)}] Skipping unreadable image: {filename}")
            continue

        h, w = img_bgr.shape[:2]

        # Run Baseline Inference
        baseline_dets = baseline_detector.detect(
            img_bgr, conf_threshold=conf_threshold, inspection_mode=inspection_mode
        )
        summary_stats["baseline_detections_total"] += len(baseline_dets)

        for d in baseline_dets:
            cname = d.get("class_name", "unknown")
            summary_stats["baseline_by_class"][cname] = summary_stats["baseline_by_class"].get(cname, 0) + 1

        # Run Candidate Inference (if available)
        candidate_dets = None
        if candidate_detector is not None:
            candidate_dets = candidate_detector.detect(
                img_bgr, conf_threshold=conf_threshold, inspection_mode=inspection_mode
            )
            summary_stats["candidate_detections_total"] += len(candidate_dets)
            for d in candidate_dets:
                cname = d.get("class_name", "unknown")
                summary_stats["candidate_by_class"][cname] = summary_stats["candidate_by_class"].get(cname, 0) + 1

        # Render Side-by-Side Comparison Image
        vis_img = render_side_by_side_comparison(
            image_bgr=img_bgr,
            baseline_dets=baseline_dets,
            candidate_dets=candidate_dets,
            title=filename,
            missing_candidate_msg="Candidate weights pending download" if not candidate_present else "Candidate Failed",
        )
        vis_out_path = os.path.join(images_out_dir, f"compare_{idx:02d}_{os.path.splitext(filename)[0]}.jpg")
        cv2.imwrite(vis_out_path, vis_img)

        # Build CSV Records
        # Detail baseline detections
        baseline_summary = "; ".join([
            f"{d['distress_category']} ({d['confidence']:.2f}) [{d['bbox']['x1']:.0f},{d['bbox']['y1']:.0f},{d['bbox']['x2']:.0f},{d['bbox']['y2']:.0f}]"
            for d in baseline_dets
        ]) or "None"

        candidate_summary = "Checkpoint missing"
        if candidate_dets is not None:
            candidate_summary = "; ".join([
                f"{d['distress_category']} ({d['confidence']:.2f}) [{d['bbox']['x1']:.0f},{d['bbox']['y1']:.0f},{d['bbox']['x2']:.0f},{d['bbox']['y2']:.0f}]"
                for d in candidate_dets
            ]) or "None"

        # Match defects between baseline and candidate if both available
        diff_notes = []
        if candidate_dets is not None:
            if len(candidate_dets) > len(baseline_dets):
                diff_notes.append(f"+{len(candidate_dets) - len(baseline_dets)} additional detection(s)")
            elif len(candidate_dets) < len(baseline_dets):
                diff_notes.append(f"-{len(baseline_dets) - len(candidate_dets)} fewer detection(s)")
            else:
                diff_notes.append("Equal detection count")

            # Check class changes on overlapping boxes
            for cd in candidate_dets:
                for bd in baseline_dets:
                    iou = compute_box_iou(cd["bbox"], bd["bbox"])
                    if iou > 0.40:
                        if cd["class_name"] != bd["class_name"]:
                            diff_notes.append(
                                f"Class shift (IoU={iou:.2f}): Baseline={bd['distress_category']} -> Candidate={cd['distress_category']}"
                            )
                        else:
                            conf_delta = cd["confidence"] - bd["confidence"]
                            diff_notes.append(f"Confidence shift ({cd['distress_category']}): {conf_delta:+.2f}")
        else:
            diff_notes.append("Candidate checkpoint not loaded on local disk")

        csv_rows.append({
            "image_index": idx,
            "filename": filename,
            "resolution": f"{w}x{h}",
            "baseline_count": len(baseline_dets),
            "candidate_count": len(candidate_dets) if candidate_dets is not None else "N/A",
            "baseline_predictions": baseline_summary,
            "candidate_predictions": candidate_summary,
            "diff_analysis": " | ".join(diff_notes),
            "visualization_path": os.path.relpath(vis_out_path, REPO_ROOT).replace("\\", "/"),
        })

        cand_str = f"{len(candidate_dets)} candidate" if candidate_dets is not None else "N/A"
        print(f"[{idx:02d}/{len(image_paths)}] {filename:<40} -> Baseline: {len(baseline_dets):2d} det | Candidate: {cand_str} | Saved: {os.path.basename(vis_out_path)}")

    # 4. Save CSV
    csv_out_path = os.path.join(output_dir, "predictions_comparison.csv")
    with open(csv_out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "image_index",
                "filename",
                "resolution",
                "baseline_count",
                "candidate_count",
                "baseline_predictions",
                "candidate_predictions",
                "diff_analysis",
                "visualization_path",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\n Predictions CSV saved: {csv_out_path}")

    # 5. Save JSON summary
    summary_out_path = os.path.join(output_dir, "comparison_summary.json")
    comparison_completed = candidate_detector is not None
    summary_data = {
        "status": "success" if comparison_completed else "incomplete",
        "comparison_completed": comparison_completed,
        "baseline_path": baseline_path,
        "candidate_path": candidate_path,
        "candidate_present_on_disk": candidate_present,
        "confidence_threshold": conf_threshold,
        "inspection_mode": inspection_mode,
        "summary_stats": summary_stats,
        "csv_path": csv_out_path,
    }
    with open(summary_out_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print(f" Summary JSON saved: {summary_out_path}")
    print("=" * 70)
    return summary_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisionGuard AI Home Model Checkpoint Comparison")
    parser.add_argument("--baseline", default="ai/models/home_best.pt", help="Baseline Home model checkpoint")
    parser.add_argument("--candidate", default="ai/models/home_exp_a_test.pt", help="Candidate Home model checkpoint")
    parser.add_argument("--images-dir", default="data/test_representative_home_defects", help="Test images directory")
    parser.add_argument("--output-dir", default="reports/evaluation_audit/home_model_comparison", help="Output directory")
    parser.add_argument("--conf", type=float, default=0.20, help="Confidence threshold")
    parser.add_argument("--mode", default="standard", choices=["standard", "tiled", "sliced"], help="Inspection mode")
    parser.add_argument("--allow-missing-candidate", action="store_true", help="Allow running baseline-only evaluation if candidate is missing")

    args = parser.parse_args()
    try:
        run_home_model_comparison(
            baseline_path=args.baseline,
            candidate_path=args.candidate,
            images_dir=args.images_dir,
            output_dir=args.output_dir,
            conf_threshold=args.conf,
            inspection_mode=args.mode,
            allow_missing_candidate=args.allow_missing_candidate,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"\n[FATAL ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

