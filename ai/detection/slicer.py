"""
Sliced / Tiled Inference Engine for VisionGuard AI.

Implements high-resolution sliding-window inference (SAHI style) without external dependencies:
1. Slices arbitrary-resolution road imagery into overlapping tiles.
2. Runs authentic model inference on each local tile at native pixel density.
3. Translates local tile bounding boxes to global image coordinates.
4. Fuses global and tiled predictions using Non-Maximum Suppression (NMS).
5. Captures continuous longitudinal and alligator cracks along their full length without downsampling loss.
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np


def compute_iou(box1: Dict[str, float], box2: Dict[str, float]) -> float:
    """Computes Intersection over Union between two bbox dicts with keys x1, y1, x2, y2."""
    ix1 = max(box1["x1"], box2["x1"])
    iy1 = max(box1["y1"], box2["y1"])
    ix2 = min(box1["x2"], box2["x2"])
    iy2 = min(box1["y2"], box2["y2"])

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih

    a1 = max(0.0, (box1["x2"] - box1["x1"]) * (box1["y2"] - box1["y1"]))
    a2 = max(0.0, (box2["x2"] - box2["x1"]) * (box2["y2"] - box2["y1"]))
    union = a1 + a2 - intersection

    return intersection / union if union > 0 else 0.0


def apply_nms(detections: List[Dict[str, Any]], iou_threshold: float = 0.45) -> List[Dict[str, Any]]:
    """
    Applies per-class Non-Maximum Suppression (NMS) to merge overlapping candidate boxes.
    Higher-confidence boxes take priority. Overlapping boxes above iou_threshold with the same class_id are suppressed.
    """
    if not detections:
        return []

    # Sort descending by confidence score
    sorted_dets = sorted(detections, key=lambda d: d.get("confidence", 0.0), reverse=True)
    kept: List[Dict[str, Any]] = []

    while sorted_dets:
        best = sorted_dets.pop(0)
        kept.append(best)
        remaining = []
        for cand in sorted_dets:
            # Different classes do not suppress each other
            if cand.get("class_id") != best.get("class_id"):
                remaining.append(cand)
            else:
                iou = compute_iou(best["bbox"], cand["bbox"])
                if iou < iou_threshold:
                    remaining.append(cand)
        sorted_dets = remaining

    return kept


class SlicedInferenceEngine:
    """
    High-resolution tiled inference processor.
    Preserves fine crack continuity and avoids resolution degradation on road surfaces.
    """

    def __init__(
        self,
        slice_size: int = 384,
        overlap_ratio: float = 0.20,
        merge_iou_threshold: float = 0.40,
    ):
        self.slice_size = max(160, slice_size)
        self.overlap_ratio = max(0.05, min(0.60, overlap_ratio))
        self.merge_iou_threshold = merge_iou_threshold
        self.last_sliced_stats: Dict[str, Any] = {
            "slice_count": 0,
            "raw_candidate_count": 0,
            "top_raw_confidence": 0.0,
            "top_raw_class": "",
            "suggested_threshold": None,
        }

    def calculate_slices(
        self,
        img_w: int,
        img_h: int,
        slice_size: Optional[int] = None,
        overlap_ratio: Optional[float] = None,
    ) -> List[Tuple[int, int, int, int]]:
        """
        Calculates slice bounding coordinates: (x_min, y_min, x_max, y_max)
        with the specified overlap ratio.
        """
        eff_size = slice_size or self.slice_size
        eff_overlap = overlap_ratio if overlap_ratio is not None else self.overlap_ratio

        eff_size = max(160, eff_size)
        eff_overlap = max(0.05, min(0.60, eff_overlap))

        tile_w = min(img_w, eff_size)
        tile_h = min(img_h, eff_size)

        step_x = max(1, int(tile_w * (1.0 - eff_overlap)))
        step_y = max(1, int(tile_h * (1.0 - eff_overlap)))

        x_coords = []
        x = 0
        while x < img_w:
            x_end = min(x + tile_w, img_w)
            x_start = max(0, x_end - tile_w)
            x_coords.append((x_start, x_end))
            if x_end == img_w:
                break
            x += step_x

        y_coords = []
        y = 0
        while y < img_h:
            y_end = min(y + tile_h, img_h)
            y_start = max(0, y_end - tile_h)
            y_coords.append((y_start, y_end))
            if y_end == img_h:
                break
            y += step_y

        # Build unique grid combinations
        slices = []
        seen = set()
        for y_min, y_max in y_coords:
            for x_min, x_max in x_coords:
                coord = (x_min, y_min, x_max, y_max)
                if coord not in seen:
                    seen.add(coord)
                    slices.append(coord)

        return slices

    def execute_sliced_inference(
        self,
        detector,
        image_bgr: np.ndarray,
        conf_threshold: float = 0.25,
        slice_size: Optional[int] = None,
        overlap_ratio: Optional[float] = None,
        fuse_with_global: bool = True,
        raise_if_unloaded: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Executes tiled inference across overlapping image slices:
        1. Optionally runs global pass on full image.
        2. Generates overlapping tiles and runs genuine inference on each tile.
        3. Shifts tile bboxes back to global coordinates.
        4. Fuses all candidates using per-class NMS.
        5. Tracks aggregate diagnostic telemetry (raw candidate count, top confidence).
        """
        if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.size == 0:
            self.last_sliced_stats = {
                "slice_count": 0,
                "raw_candidate_count": 0,
                "top_raw_confidence": 0.0,
                "top_raw_class": "",
                "suggested_threshold": None,
            }
            return []

        h, w = image_bgr.shape[:2]
        all_candidates: List[Dict[str, Any]] = []

        total_raw_count = 0
        top_raw_conf = 0.0
        top_raw_class = ""

        # Function to invoke standard inference without recursive slicing
        def run_standard(img: np.ndarray) -> List[Dict[str, Any]]:
            if hasattr(detector, "_detect_standard"):
                return detector._detect_standard(img, conf_threshold=conf_threshold, raise_if_unloaded=raise_if_unloaded)
            return detector.detect(img, conf_threshold=conf_threshold, raise_if_unloaded=raise_if_unloaded)

        # 1. Global pass (captures wide multi-tile context, e.g. broad potholes)
        if fuse_with_global:
            global_dets = run_standard(image_bgr)
            for gd in global_dets:
                cand = dict(gd)
                cand["source"] = "global"
                all_candidates.append(cand)

            # Check detector's stats from global pass
            if hasattr(detector, "last_inference_stats"):
                g_stats = detector.last_inference_stats or {}
                total_raw_count += g_stats.get("raw_candidate_count", 0)
                if g_stats.get("top_raw_confidence", 0.0) > top_raw_conf:
                    top_raw_conf = g_stats["top_raw_confidence"]
                    top_raw_class = g_stats.get("top_raw_class", "")

        # 2. Sliced pass
        slice_coords = self.calculate_slices(w, h, slice_size=slice_size, overlap_ratio=overlap_ratio)
        for (x_min, y_min, x_max, y_max) in slice_coords:
            # If the single slice covers the exact entire image, skip redundant slice
            if x_min == 0 and y_min == 0 and x_max == w and y_max == h and fuse_with_global:
                continue

            tile = image_bgr[y_min:y_max, x_min:x_max]
            tile_dets = run_standard(tile)

            # Check detector's stats from tile pass
            if hasattr(detector, "last_inference_stats"):
                t_stats = detector.last_inference_stats or {}
                total_raw_count += t_stats.get("raw_candidate_count", 0)
                if t_stats.get("top_raw_confidence", 0.0) > top_raw_conf:
                    top_raw_conf = t_stats["top_raw_confidence"]
                    top_raw_class = t_stats.get("top_raw_class", "")

            for td in tile_dets:
                tb = td["bbox"]
                gx1 = round(tb["x1"] + x_min, 1)
                gy1 = round(tb["y1"] + y_min, 1)
                gx2 = round(tb["x2"] + x_min, 1)
                gy2 = round(tb["y2"] + y_min, 1)
                bw = round(max(0.0, gx2 - gx1), 1)
                bh = round(max(0.0, gy2 - gy1), 1)
                ar = round(bw / bh, 3) if bh > 0 else 0.0
                pa = round(bw * bh, 1)

                shifted_det = dict(td)
                shifted_det["bbox"] = {
                    "x1": gx1,
                    "y1": gy1,
                    "x2": gx2,
                    "y2": gy2,
                    "width": bw,
                    "height": bh,
                    "aspect_ratio": ar,
                    "pixel_area": pa,
                }
                shifted_det["source"] = "tiled"
                shifted_det["tile_coords"] = [x_min, y_min, x_max, y_max]
                all_candidates.append(shifted_det)

        # 3. Fuse and deduplicate using NMS
        fused = apply_nms(all_candidates, iou_threshold=self.merge_iou_threshold)

        # 4. Save aggregate sliced stats
        suggested = round(max(0.05, top_raw_conf - 0.004), 2) if top_raw_conf >= 0.045 else None
        self.last_sliced_stats = {
            "slice_count": len(slice_coords),
            "raw_candidate_count": total_raw_count,
            "top_raw_confidence": round(top_raw_conf, 4),
            "top_raw_class": top_raw_class,
            "suggested_threshold": suggested,
        }

        return fused
