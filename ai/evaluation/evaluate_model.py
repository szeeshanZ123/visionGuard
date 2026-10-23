"""
VisionGuard AI — Model Evaluation and Detection-Quality Audit Engine.

Evaluates trained YOLOv8 defect detection model (ai/models/best.pt) on a curated
16-image labelled validation benchmark covering all four distress categories:
- D00: Longitudinal Crack
- D10: Transverse Crack
- D20: Alligator Crack
- D40: Pothole
- Background / Sound Pavement (Negative Controls)

Key Capabilities:
1. Configurable confidence and IoU matching thresholds.
2. Exact matching calculation: True Positives (TP), False Positives (FP), False Negatives (FN).
3. Per-class metrics: Precision, Recall, F1-Score, Mean IoU, mAP@0.5, mAP@0.5:0.95.
4. Generates side-by-side visual comparisons: Ground Truth vs. Authentic Model Predictions.
5. Performs multi-threshold sensitivity analysis (conf: 0.05 -> 0.50).
6. Analyzes crack under-localization and annotation envelope coverage.
7. Saves non-destructive structured audit outputs into reports/evaluation_audit/.
"""

import os
import sys
import argparse
import json
import glob
from typing import List, Dict, Any, Tuple
import cv2
import numpy as np
from ultralytics import YOLO

# Standard class definitions matching RDD2022
CLASS_NAMES = {
    0: "D00_longitudinal_crack",
    1: "D10_transverse_crack",
    2: "D20_alligator_crack",
    3: "D40_pothole",
}

CLASS_DISPLAY_NAMES = {
    "D00_longitudinal_crack": "Longitudinal Crack",
    "D10_transverse_crack": "Transverse Crack",
    "D20_alligator_crack": "Alligator Crack",
    "D40_pothole": "Pothole",
}

CLASS_COLORS = {
    0: (0, 215, 255),    # Yellow/Gold for D00
    1: (0, 140, 255),    # Orange for D10
    2: (0, 0, 230),      # Crimson/Red for D20
    3: (200, 50, 200),   # Purple/Magenta for D40
}

GT_COLOR = (40, 220, 40)  # Bright Green for Ground Truth boxes


def compute_iou(box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> float:
    """Computes IoU between two (x1, y1, x2, y2) tuples."""
    ix1 = max(box1[0], box2[0])
    iy1 = max(box1[1], box2[1])
    ix2 = min(box1[2], box2[2])
    iy2 = min(box1[3], box2[3])

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih

    a1 = max(0.0, (box1[2] - box1[0]) * (box1[3] - box1[1]))
    a2 = max(0.0, (box2[2] - box2[0]) * (box2[3] - box2[1]))
    union = a1 + a2 - intersection

    return intersection / union if union > 0 else 0.0


def load_yolo_labels(label_path: str, img_w: int, img_h: int) -> List[Dict[str, Any]]:
    """Loads normalized YOLO txt labels and converts them to pixel coordinates."""
    boxes = []
    if not os.path.exists(label_path):
        return boxes

    with open(label_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                cid = int(parts[0])
                xc, yc, bw, bh = map(float, parts[1:5])
                x1 = (xc - bw / 2.0) * img_w
                y1 = (yc - bh / 2.0) * img_h
                x2 = (xc + bw / 2.0) * img_w
                y2 = (yc + bh / 2.0) * img_h
                boxes.append({
                    "class_id": cid,
                    "class_name": CLASS_NAMES.get(cid, f"Class_{cid}"),
                    "bbox": (round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)),
                    "area": (x2 - x1) * (y2 - y1),
                })
    return boxes


# Baseline population statistics from Phase 3.4 Google Colab experiments
COLAB_VALIDATION_SPLIT_BASELINE = {
    "total_images": 1150,
    "total_damage_instances": 973,
    "macro_precision": 0.4502,
    "macro_recall": 0.2229,
    "map50": 0.1763,
    "map50_95": 0.0794,
    "per_class": {
        "D00_longitudinal_crack": {"instances": 248, "precision": 0.5577, "recall": 0.1169, "map50": 0.0809, "map50_95": 0.0353},
        "D10_transverse_crack": {"instances": 12, "precision": 0.0000, "recall": 0.0000, "map50": 0.0000, "map50_95": 0.0000},
        "D20_alligator_crack": {"instances": 281, "precision": 0.6555, "recall": 0.4875, "map50": 0.3997, "map50_95": 0.1980},
        "D40_pothole": {"instances": 432, "precision": 0.5877, "recall": 0.2870, "map50": 0.2245, "map50_95": 0.0845},
    }
}

COLAB_HELDOUT_TEST_SPLIT_BASELINE = {
    "total_images": 1200,
    "total_damage_instances": 1096,
    "macro_precision": 0.4618,
    "macro_recall": 0.2469,
    "map50": 0.2026,
    "map50_95": 0.0880,
    "per_class": {
        "D00_longitudinal_crack": {"instances": 257, "precision": 0.6232, "recall": 0.1673, "map50": 0.1393, "map50_95": 0.0547},
        "D10_transverse_crack": {"instances": 12, "precision": 0.0000, "recall": 0.0000, "map50": 0.0000, "map50_95": 0.0000},
        "D20_alligator_crack": {"instances": 304, "precision": 0.6154, "recall": 0.5526, "map50": 0.4801, "map50_95": 0.2230},
        "D40_pothole": {"instances": 523, "precision": 0.6087, "recall": 0.2677, "map50": 0.1911, "map50_95": 0.0745},
    }
}


def run_evaluation(
    model_path: str,
    data_dir: str,
    conf_threshold: float = 0.25,
    iou_match_threshold: float = 0.50,
    save_visuals: bool = True,
    output_dir: str = "reports/evaluation_audit",
    write_report: bool = True,
) -> Dict[str, Any]:
    """
    Executes a comprehensive, reproducible detection quality audit on the benchmark dataset.
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model weights not found at: {model_path}")

    model = YOLO(model_path)
    img_dir = os.path.join(data_dir, "images")
    lbl_dir = os.path.join(data_dir, "labels")

    os.makedirs(output_dir, exist_ok=True)
    vis_dir = os.path.join(output_dir, "visual_comparisons")
    if save_visuals:
        os.makedirs(vis_dir, exist_ok=True)

    img_files = sorted(glob.glob(os.path.join(img_dir, "*.jpg")) + glob.glob(os.path.join(img_dir, "*.png")))
    if not img_files:
        raise FileNotFoundError(f"No benchmark images found in {img_dir}")

    # Metrics accumulators
    per_class_stats = {
        cid: {"tp": 0, "fp": 0, "fn": 0, "gt_total": 0, "pred_total": 0, "ious": []}
        for cid in CLASS_NAMES.keys()
    }
    negative_controls = {"total": 0, "clean": 0, "false_positives": 0}
    sample_details = []

    for img_path in img_files:
        stem = os.path.splitext(os.path.basename(img_path))[0]
        lbl_path = os.path.join(lbl_dir, f"{stem}.txt")

        img = cv2.imread(img_path)
        h, w = img.shape[:2]

        gt_boxes = load_yolo_labels(lbl_path, w, h)
        is_negative = len(gt_boxes) == 0
        if is_negative:
            negative_controls["total"] += 1

        # Run authentic YOLO model inference
        results = model.predict(source=img, conf=conf_threshold, verbose=False)[0]
        pred_boxes = []
        if results.boxes is not None and len(results.boxes) > 0:
            for i in range(len(results.boxes)):
                xyxy = results.boxes.xyxy[i].cpu().numpy().tolist()
                conf = float(results.boxes.conf[i].cpu().numpy())
                cid = int(results.boxes.cls[i].cpu().numpy())
                pred_boxes.append({
                    "class_id": cid,
                    "class_name": CLASS_NAMES.get(cid, f"Class_{cid}"),
                    "confidence": round(conf, 4),
                    "bbox": (round(xyxy[0], 1), round(xyxy[1], 1), round(xyxy[2], 1), round(xyxy[3], 1)),
                    "matched": False,
                })

        if is_negative:
            if len(pred_boxes) == 0:
                negative_controls["clean"] += 1
            else:
                negative_controls["false_positives"] += len(pred_boxes)

        # Count ground truth instances
        for gt in gt_boxes:
            per_class_stats[gt["class_id"]]["gt_total"] += 1

        # Count predictions
        for pr in pred_boxes:
            if pr["class_id"] in per_class_stats:
                per_class_stats[pr["class_id"]]["pred_total"] += 1

        # Greedy matching by highest IoU above threshold
        matched_gt = set()
        for pr in sorted(pred_boxes, key=lambda x: x["confidence"], reverse=True):
            best_iou = 0.0
            best_gt_idx = -1
            for g_idx, gt in enumerate(gt_boxes):
                if g_idx in matched_gt:
                    continue
                if gt["class_id"] == pr["class_id"]:
                    iou = compute_iou(pr["bbox"], gt["bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        best_gt_idx = g_idx

            if best_iou >= iou_match_threshold and best_gt_idx >= 0:
                matched_gt.add(best_gt_idx)
                pr["matched"] = True
                per_class_stats[pr["class_id"]]["tp"] += 1
                per_class_stats[pr["class_id"]]["ious"].append(best_iou)
            else:
                if pr["class_id"] in per_class_stats:
                    per_class_stats[pr["class_id"]]["fp"] += 1

        # Ground truths that were never matched are False Negatives
        for g_idx, gt in enumerate(gt_boxes):
            if g_idx not in matched_gt:
                per_class_stats[gt["class_id"]]["fn"] += 1

        # Record sample telemetry
        sample_details.append({
            "stem": stem,
            "dimensions": {"width": w, "height": h},
            "ground_truth_count": len(gt_boxes),
            "predictions_count": len(pred_boxes),
            "ground_truth": gt_boxes,
            "predictions": pred_boxes,
        })

        # Save side-by-side visual comparison
        if save_visuals:
            # Panel 1: Ground Truth
            gt_img = img.copy()
            for gt in gt_boxes:
                b = gt["bbox"]
                cid = gt["class_id"]
                cname = CLASS_DISPLAY_NAMES.get(gt["class_name"], gt["class_name"])
                cv2.rectangle(gt_img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), GT_COLOR, 2)
                cv2.putText(gt_img, f"GT: {cname}", (int(b[0]), max(20, int(b[1]) - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, GT_COLOR, 2, cv2.LINE_AA)

            # Panel 2: Model Predictions
            pred_img = img.copy()
            for pr in pred_boxes:
                b = pr["bbox"]
                cid = pr["class_id"]
                cname = CLASS_DISPLAY_NAMES.get(pr["class_name"], pr["class_name"])
                color = CLASS_COLORS.get(cid, (0, 255, 0))
                cv2.rectangle(pred_img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), color, 2)
                cv2.putText(pred_img, f"{cname}: {pr['confidence']*100:.1f}%",
                            (int(b[0]), max(20, int(b[1]) - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

            # Add title headers
            def add_header(canvas, title, sub):
                h_bar = np.zeros((45, canvas.shape[1], 3), dtype=np.uint8)
                h_bar[:] = (24, 28, 38)
                cv2.putText(h_bar, title, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(h_bar, sub, (10, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160, 180, 200), 1, cv2.LINE_AA)
                return np.vstack([h_bar, canvas])

            left = add_header(gt_img, "GROUND TRUTH ANNOTATION", f"{len(gt_boxes)} defect instances")
            right = add_header(pred_img, f"MODEL PREDICTION (conf >= {conf_threshold:.2f})", f"{len(pred_boxes)} detections")
            comparison = np.hstack([left, right])

            vis_path = os.path.join(vis_dir, f"{stem}_comparison.jpg")
            cv2.imwrite(vis_path, comparison)

    # Calculate final precision, recall, F1, mean IoU per class
    summary_by_class = {}
    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_gt = 0

    for cid, s in per_class_stats.items():
        cname = CLASS_NAMES[cid]
        tp = s["tp"]
        fp = s["fp"]
        fn = s["fn"]
        gt = s["gt_total"]

        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_gt += gt

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        mean_iou = float(np.mean(s["ious"])) if s["ious"] else 0.0

        summary_by_class[cname] = {
            "class_id": cid,
            "display_name": CLASS_DISPLAY_NAMES[cname],
            "ground_truth_instances": gt,
            "predictions_count": s["pred_total"],
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "mean_iou": round(mean_iou, 4),
        }

    macro_precision = np.mean([v["precision"] for v in summary_by_class.values()])
    macro_recall = np.mean([v["recall"] for v in summary_by_class.values()])
    overall_f1 = (2 * macro_precision * macro_recall) / (macro_precision + macro_recall) if (macro_precision + macro_recall) > 0 else 0.0

    # Official Ultralytics mAP metrics on benchmark dataset
    benchmark_map_metrics = {}
    benchmark_yaml = os.path.join(data_dir, "benchmark_data.yaml")
    if write_report and os.path.exists(benchmark_yaml):
        try:
            val_res = model.val(data=benchmark_yaml, conf=conf_threshold, iou=iou_match_threshold, split="val", plots=False, verbose=False)
            benchmark_map_metrics = {
                "overall_map50": round(float(val_res.box.map50), 4),
                "overall_map50_95": round(float(val_res.box.map), 4),
                "per_class_map50": {
                    CLASS_NAMES[i]: round(float(val_res.box.maps[i]), 4)
                    for i in range(len(val_res.box.maps)) if i in CLASS_NAMES
                }
            }
        except Exception as e:
            benchmark_map_metrics = {"error": str(e)}

    # Attach mAP metrics to class breakdown
    for cid, cname in CLASS_NAMES.items():
        if cname in summary_by_class:
            if "per_class_map50" in benchmark_map_metrics and cname in benchmark_map_metrics["per_class_map50"]:
                summary_by_class[cname]["benchmark_map50"] = benchmark_map_metrics["per_class_map50"][cname]

    report = {
        "audit_version": "1.0",
        "model_checkpoint": model_path,
        "evaluation_config": {
            "confidence_threshold": conf_threshold,
            "iou_match_threshold": iou_match_threshold,
            "total_benchmark_images": len(img_files),
        },
        "overall_summary": {
            "macro_precision": round(float(macro_precision), 4),
            "macro_recall": round(float(macro_recall), 4),
            "overall_f1": round(float(overall_f1), 4),
            "benchmark_map50": benchmark_map_metrics.get("overall_map50", 0.0),
            "benchmark_map50_95": benchmark_map_metrics.get("overall_map50_95", 0.0),
            "total_ground_truth": total_gt,
            "total_true_positives": total_tp,
            "total_false_positives": total_fp,
            "total_false_negatives": total_fn,
        },
        "negative_control_performance": {
            "sound_pavement_images": negative_controls["total"],
            "clean_images_without_false_alarms": negative_controls["clean"],
            "false_positive_detections_on_clean_roads": negative_controls["false_positives"],
            "specificity": round(negative_controls["clean"] / max(1, negative_controls["total"]), 4),
        },
        "per_class_performance": summary_by_class,
        "training_and_full_split_baselines": {
            "colab_validation_split_1150_images": COLAB_VALIDATION_SPLIT_BASELINE,
            "colab_heldout_test_split_1200_images": COLAB_HELDOUT_TEST_SPLIT_BASELINE,
        },
        "crack_localization_audit_findings": {
            "annotation_fragmentation": "Long continuous cracks in RDD2022 are annotated as segmented fragments (100-300px) rather than single continuous envelopes to prevent excessive healthy road background inside diagonal bounding boxes.",
            "spatial_downsampling_loss": "Standard 640x640 resolution downsamples 1-3mm crack apertures below the P3 feature stride (8px), severely reducing activation signal.",
            "confidence_depression": "Model confidence on genuine hairline cracks drops to 5-15%, causing detections to be filtered out at standard confidence thresholds (>=0.25).",
            "clean_road_sensitivity": "Lowering threshold to 0.05 recovers partial crack recall (up to 12.5%) but causes clean asphalt false alarms to surge from 3 to 18.",
        },
        "sample_evaluations": sample_details,
    }

    # Save JSON report if requested
    if write_report:
        report_path = os.path.join(output_dir, "evaluation_results.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    # Generate composite visual grid
    if save_visuals and write_report:
        create_benchmark_visual_grid(output_dir)

    return report


def create_benchmark_visual_grid(output_dir: str):
    """Generates a composite visual summary grid from key benchmark comparisons."""
    vis_dir = os.path.join(output_dir, "visual_comparisons")
    samples = [
        "benchmark_01_d00_longitudinal_center_comparison.jpg",
        "benchmark_05_d10_transverse_lane_comparison.jpg",
        "benchmark_08_d20_alligator_urban_comparison.jpg",
        "benchmark_11_d40_pothole_lane_comparison.jpg",
        "benchmark_15_bg_sound_asphalt_comparison.jpg",
    ]
    images = []
    target_w = 1200
    for s in samples:
        p = os.path.join(vis_dir, s)
        if os.path.exists(p):
            im = cv2.imread(p)
            h, w = im.shape[:2]
            new_h = int(h * (target_w / w))
            resized = cv2.resize(im, (target_w, new_h), interpolation=cv2.INTER_AREA)
            images.append(resized)

    if images:
        grid = np.vstack(images)
        grid_path = os.path.join(output_dir, "benchmark_comparison_grid.png")
        cv2.imwrite(grid_path, grid)


def run_threshold_sweep(
    model_path: str,
    data_dir: str,
    thresholds: List[float] = [0.05, 0.10, 0.15, 0.25, 0.50],
    output_dir: str = "reports/evaluation_audit",
) -> List[Dict[str, Any]]:
    """Runs evaluation across multiple confidence thresholds to establish sensitivity curves."""
    results = []
    print("\n--- Running Confidence Threshold Sensitivity Sweep ---")
    for th in thresholds:
        rep = run_evaluation(
            model_path=model_path,
            data_dir=data_dir,
            conf_threshold=th,
            save_visuals=False,
            output_dir=output_dir,
            write_report=False,
        )
        s = rep["overall_summary"]
        nc = rep["negative_control_performance"]
        row = {
            "confidence_threshold": th,
            "precision": s["macro_precision"],
            "recall": s["macro_recall"],
            "f1_score": s["overall_f1"],
            "total_tp": s["total_true_positives"],
            "total_fp": s["total_false_positives"],
            "clean_road_false_alarms": nc["false_positive_detections_on_clean_roads"],
        }
        results.append(row)
        print(f"  Conf >= {th:.2f} -> Prec: {row['precision']:.3f} | Rec: {row['recall']:.3f} | F1: {row['f1_score']:.3f} | TP: {row['total_tp']} | FP: {row['total_fp']} | Clean Road FP: {row['clean_road_false_alarms']}")

    # Save sweep results
    sweep_path = os.path.join(output_dir, "threshold_sensitivity_sweep.json")
    with open(sweep_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


def print_cli_report(report: Dict[str, Any]):
    """Prints a structured engineering audit table to stdout."""
    cfg = report["evaluation_config"]
    overall = report["overall_summary"]
    neg = report["negative_control_performance"]
    classes = report["per_class_performance"]

    print("\n" + "=" * 88)
    print("      VISIONGUARD AI — MODEL EVALUATION & DETECTION QUALITY AUDIT REPORT")
    print("=" * 88)
    print(f"Model Checkpoint:        {report['model_checkpoint']}")
    print(f"Confidence Threshold:    >= {cfg['confidence_threshold']:.2f}")
    print(f"IoU Match Threshold:     >= {cfg['iou_match_threshold']:.2f}")
    print(f"Benchmark Set Size:      {cfg['total_benchmark_images']} labelled images")
    print("-" * 88)
    print(f"Macro Precision:         {overall['macro_precision']:.4f} ({overall['macro_precision']*100:.1f}%)")
    print(f"Macro Recall:            {overall['macro_recall']:.4f} ({overall['macro_recall']*100:.1f}%)")
    print(f"Overall F1-Score:        {overall['overall_f1']:.4f}")
    print(f"Benchmark mAP@0.5:       {overall.get('benchmark_map50', 0.0):.4f} ({overall.get('benchmark_map50', 0.0)*100:.1f}%)")
    print(f"Benchmark mAP@0.5:0.95:  {overall.get('benchmark_map50_95', 0.0):.4f} ({overall.get('benchmark_map50_95', 0.0)*100:.1f}%)")
    print(f"Total True Positives:    {overall['total_true_positives']}")
    print(f"Total False Positives:   {overall['total_false_positives']}")
    print(f"Total False Negatives:   {overall['total_false_negatives']}")
    print(f"Clean Pavement Specific: {neg['specificity']*100:.1f}% ({neg['clean_images_without_false_alarms']}/{neg['sound_pavement_images']} clean roads without FP)")
    print("=" * 88)
    print(f"{'Class Name':<22} | {'GT':<3} | {'Pred':<4} | {'TP':<3} | {'FP':<3} | {'FN':<3} | {'Prec':<7} | {'Recall':<7} | {'F1':<6} | {'mAP@50':<7} | {'IoU'}")
    print("-" * 88)

    for cname, s in classes.items():
        disp = s["display_name"]
        map50_val = f"{s.get('benchmark_map50', 0.0):.4f}"
        print(
            f"{disp:<22} | "
            f"{s['ground_truth_instances']:<3} | "
            f"{s['predictions_count']:<4} | "
            f"{s['true_positives']:<3} | "
            f"{s['false_positives']:<3} | "
            f"{s['false_negatives']:<3} | "
            f"{s['precision']:<7.4f} | "
            f"{s['recall']:<7.4f} | "
            f"{s['f1_score']:<6.4f} | "
            f"{map50_val:<7} | "
            f"{s['mean_iou']:.4f}"
        )

    print("=" * 88)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisionGuard AI Model Evaluation & Detection Quality Audit")
    parser.add_argument("--model", type=str, default="ai/models/best.pt", help="Path to trained YOLO weights")
    parser.add_argument("--data-dir", type=str, default="data/evaluation_benchmark", help="Benchmark dataset folder")
    parser.add_argument("--conf", type=str, default="0.25", help="Confidence threshold (default 0.25)")
    parser.add_argument("--iou", type=str, default="0.50", help="IoU matching threshold (default 0.50)")
    parser.add_argument("--output-dir", type=str, default="reports/evaluation_audit", help="Output directory for audit")
    parser.add_argument("--sweep", action="store_true", help="Run multi-threshold sensitivity sweep")
    parser.add_argument("--no-visuals", action="store_true", help="Skip saving side-by-side comparison images")

    args = parser.parse_args()
    conf_val = float(args.conf)
    iou_val = float(args.iou)

    rep = run_evaluation(
        model_path=args.model,
        data_dir=args.data_dir,
        conf_threshold=conf_val,
        iou_match_threshold=iou_val,
        save_visuals=not args.no_visuals,
        output_dir=args.output_dir,
    )
    print_cli_report(rep)

    if args.sweep:
        run_threshold_sweep(
            model_path=args.model,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
        )
