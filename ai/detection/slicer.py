import time
"""
Sliced / Tiled Inference Engine for VisionGuard AI.

Implements high-resolution sliding-window inference (SAHI style) without external dependencies:
1. Slices arbitrary-resolution road imagery into overlapping tiles.
2. Runs authentic model inference on each local tile at native pixel density.
3. Translates local tile bounding boxes to global image coordinates.
4. Fuses global and tiled predictions using Non-Maximum Suppression (NMS).
5. Captures continuous longitudinal and alligator cracks along their full length without downsampling loss.
"""

import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

logger = logging.getLogger("visionguard.slicer")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def compute_iou(box1: Dict[str, float], box2: Dict[str, float]) -> float:
    """Computes Intersection over Union between two bbox dicts with keys x1, y1, x2, y2."""
    ix1 = max(float(box1.get("x1", 0.0)), float(box2.get("x1", 0.0)))
    iy1 = max(float(box1.get("y1", 0.0)), float(box2.get("y1", 0.0)))
    ix2 = min(float(box1.get("x2", 0.0)), float(box2.get("x2", 0.0)))
    iy2 = min(float(box1.get("y2", 0.0)), float(box2.get("y2", 0.0)))

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih

    a1 = max(0.0, (float(box1.get("x2", 0.0)) - float(box1.get("x1", 0.0))) * (float(box1.get("y2", 0.0)) - float(box1.get("y1", 0.0))))
    a2 = max(0.0, (float(box2.get("x2", 0.0)) - float(box2.get("x1", 0.0))) * (float(box2.get("y2", 0.0)) - float(box2.get("y1", 0.0))))
    union = a1 + a2 - intersection

    return intersection / union if union > 0 else 0.0


def compute_iom(box1: Dict[str, float], box2: Dict[str, float]) -> float:
    """
    Computes Intersection over Minimum (IoM / containment) between two bbox dicts.
    Useful for multi-scale / nested boxes where a smaller tile detection is largely
    contained inside an oversized global detection.
    """
    ix1 = max(float(box1.get("x1", 0.0)), float(box2.get("x1", 0.0)))
    iy1 = max(float(box1.get("y1", 0.0)), float(box2.get("y1", 0.0)))
    ix2 = min(float(box1.get("x2", 0.0)), float(box2.get("x2", 0.0)))
    iy2 = min(float(box1.get("y2", 0.0)), float(box2.get("y2", 0.0)))

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih

    a1 = max(0.0, (float(box1.get("x2", 0.0)) - float(box1.get("x1", 0.0))) * (float(box1.get("y2", 0.0)) - float(box1.get("y1", 0.0))))
    a2 = max(0.0, (float(box2.get("x2", 0.0)) - float(box2.get("x1", 0.0))) * (float(box2.get("y2", 0.0)) - float(box2.get("y1", 0.0))))
    min_area = min(a1, a2)

    return intersection / min_area if min_area > 0 else 0.0


def apply_nms(
    detections: List[Dict[str, Any]],
    iou_threshold: float = 0.40,
    iom_threshold: float = 0.60,
    class_aware: bool = True,
) -> List[Dict[str, Any]]:
    """
    Applies per-class Non-Maximum Suppression (NMS) to merge overlapping candidate boxes.
    Supports both standard IoU and Intersection-over-Minimum (IoM / containment)
    to handle multi-scale/nested boxes from global vs tiled passes and tile boundary overlaps.

    Higher-confidence boxes take priority. When class_aware is True (default), detections
    from different classes (e.g. wall crack vs peeling paint) never suppress each other.
    Overlapping boxes of the same class exceeding iou_threshold OR iom_threshold are suppressed.
    """
    if not detections:
        return []

    def same_class(d1: Dict[str, Any], d2: Dict[str, Any]) -> bool:
        if d1.get("class_id") is not None and d2.get("class_id") is not None:
            return d1["class_id"] == d2["class_id"]
        if d1.get("class_name") and d2.get("class_name"):
            return d1["class_name"] == d2["class_name"]
        if d1.get("distress_category") and d2.get("distress_category"):
            return d1["distress_category"] == d2["distress_category"]
        return True

    # Sort descending by confidence score
    sorted_dets = sorted(detections, key=lambda d: d.get("confidence", 0.0), reverse=True)
    kept: List[Dict[str, Any]] = []

    while sorted_dets:
        best = sorted_dets.pop(0)
        kept.append(best)
        remaining = []
        for cand in sorted_dets:
            # When class-aware, different classes do not suppress each other
            if class_aware and not same_class(best, cand):
                remaining.append(cand)
            else:
                iou = compute_iou(best["bbox"], cand["bbox"])
                iom = compute_iom(best["bbox"], cand["bbox"])
                if iou >= iou_threshold or iom >= iom_threshold:
                    logger.debug(
                        "Suppressed duplicate [%s conf=%.3f src=%s] by [%s conf=%.3f src=%s] (IoU=%.3f, IoM=%.3f)",
                        cand.get("class_name") or cand.get("distress_category"),
                        cand.get("confidence", 0.0),
                        cand.get("source", "unknown"),
                        best.get("class_name") or best.get("distress_category"),
                        best.get("confidence", 0.0),
                        best.get("source", "unknown"),
                        iou,
                        iom,
                    )
                else:
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
        merge_iom_threshold: float = 0.60,
        max_slices: int = 16,
    ):
        self.slice_size = max(160, slice_size)
        self.overlap_ratio = max(0.05, min(0.60, overlap_ratio))
        self.merge_iou_threshold = merge_iou_threshold
        self.merge_iom_threshold = merge_iom_threshold
        self.max_slices = max_slices
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
        max_slices: Optional[int] = None,
    ) -> List[Tuple[int, int, int, int]]:
        """
        Calculates slice bounding coordinates: (x_min, y_min, x_max, y_max)
        with the specified overlap ratio. Safeguards against excessive slice counts.
        """
        eff_size = slice_size or self.slice_size
        eff_overlap = overlap_ratio if overlap_ratio is not None else self.overlap_ratio
        eff_max_slices = max_slices if max_slices is not None else getattr(self, "max_slices", 16)

        eff_size = max(160, eff_size)
        eff_overlap = max(0.05, min(0.60, eff_overlap))

        # Dynamic tile size adjustment if image would exceed max_slices
        if eff_max_slices and eff_max_slices > 0:
            import math
            step_factor = max(0.40, 1.0 - eff_overlap)
            target_dim = int(math.ceil(math.sqrt((img_w * img_h) / eff_max_slices) / step_factor))
            if target_dim > eff_size:
                eff_size = target_dim

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
        3. Shifts tile bboxes back to global coordinates and clips to image boundaries.
        4. Fuses all candidates using per-class NMS with IoU + IoM containment.
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
                cand["tile_index"] = -1
                cand["tile_coords"] = [0, 0, w, h]

                # Clip global bounding box coordinates to image boundaries
                gb = cand.get("bbox", {})
                gx1 = max(0.0, min(float(w), float(gb.get("x1", 0.0))))
                gy1 = max(0.0, min(float(h), float(gb.get("y1", 0.0))))
                gx2 = max(0.0, min(float(w), float(gb.get("x2", 0.0))))
                gy2 = max(0.0, min(float(h), float(gb.get("y2", 0.0))))
                bw = round(max(0.0, gx2 - gx1), 1)
                bh = round(max(0.0, gy2 - gy1), 1)
                if bw <= 0.0 or bh <= 0.0:
                    continue

                cand["bbox"] = {
                    "x1": round(gx1, 1),
                    "y1": round(gy1, 1),
                    "x2": round(gx2, 1),
                    "y2": round(gy2, 1),
                    "width": bw,
                    "height": bh,
                    "aspect_ratio": round(bw / bh, 3) if bh > 0 else 0.0,
                    "pixel_area": round(bw * bh, 1),
                }
                all_candidates.append(cand)

            # Check detector's stats from global pass
            if hasattr(detector, "last_inference_stats"):
                g_stats = detector.last_inference_stats or {}
                total_raw_count += g_stats.get("raw_candidate_count", 0)
                if g_stats.get("top_raw_confidence", 0.0) > top_raw_conf:
                    top_raw_conf = g_stats["top_raw_confidence"]
                    top_raw_class = g_stats.get("top_raw_class", "")

        # 2. Sliced pass
        t_slice_start = time.perf_counter()
        slice_coords = self.calculate_slices(w, h, slice_size=slice_size, overlap_ratio=overlap_ratio)
        t_slicing_calc_ms = (time.perf_counter() - t_slice_start) * 1000
        logger.info(
            "Tiled inference starting: %d slices generated in %.2fms (image %dx%d, slice_size=%d, overlap=%.2f, fuse_with_global=%s)",
            len(slice_coords),
            t_slicing_calc_ms,
            w,
            h,
            slice_size or self.slice_size,
            overlap_ratio if overlap_ratio is not None else self.overlap_ratio,
            fuse_with_global,
        )

        total_tile_fwd_ms = 0.0
        for tile_idx, (x_min, y_min, x_max, y_max) in enumerate(slice_coords):
            # If the single slice covers the exact entire image, skip redundant slice
            if x_min == 0 and y_min == 0 and x_max == w and y_max == h and fuse_with_global:
                continue

            tile = image_bgr[y_min:y_max, x_min:x_max]
            t_t0 = time.perf_counter()
            tile_dets = run_standard(tile)
            total_tile_fwd_ms += (time.perf_counter() - t_t0) * 1000

            # Check detector's stats from tile pass
            if hasattr(detector, "last_inference_stats"):
                t_stats = detector.last_inference_stats or {}
                total_raw_count += t_stats.get("raw_candidate_count", 0)
                if t_stats.get("top_raw_confidence", 0.0) > top_raw_conf:
                    top_raw_conf = t_stats["top_raw_confidence"]
                    top_raw_class = t_stats.get("top_raw_class", "")

            for td in tile_dets:
                tb = td["bbox"]
                # Translate tile coordinates to global space and strictly clip to image boundaries
                gx1 = max(0.0, min(float(w), round(tb["x1"] + x_min, 1)))
                gy1 = max(0.0, min(float(h), round(tb["y1"] + y_min, 1)))
                gx2 = max(0.0, min(float(w), round(tb["x2"] + x_min, 1)))
                gy2 = max(0.0, min(float(h), round(tb["y2"] + y_min, 1)))
                bw = round(max(0.0, gx2 - gx1), 1)
                bh = round(max(0.0, gy2 - gy1), 1)
                if bw <= 0.0 or bh <= 0.0:
                    continue

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
                shifted_det["tile_index"] = tile_idx
                shifted_det["tile_coords"] = [x_min, y_min, x_max, y_max]
                all_candidates.append(shifted_det)

        # 3. Fuse and deduplicate using NMS with IoU + IoM containment
        raw_count = len(all_candidates)
        t_fus0 = time.perf_counter()
        fused = apply_nms(
            all_candidates,
            iou_threshold=self.merge_iou_threshold,
            iom_threshold=self.merge_iom_threshold,
            class_aware=True,
        )
        t_fusion_ms = (time.perf_counter() - t_fus0) * 1000
        logger.info(
            "Tiled inference candidate fusion complete: %d raw candidates -> %d fused detections (suppressed %d duplicates, IoU thresh=%.2f, IoM thresh=%.2f)",
            raw_count,
            len(fused),
            raw_count - len(fused),
            self.merge_iou_threshold,
            self.merge_iom_threshold,
        )

        # 4. Save aggregate sliced stats
        suggested = round(max(0.05, top_raw_conf - 0.004), 2) if top_raw_conf >= 0.045 else None
        self.last_sliced_stats = {
            "slice_count": len(slice_coords),
            "raw_candidate_count": total_raw_count,
            "top_raw_confidence": round(top_raw_conf, 4),
            "top_raw_class": top_raw_class,
            "suggested_threshold": suggested,
            "timings": {
                "model_load_ms": 0.0,
                "forward_pass_ms": round(total_tile_fwd_ms, 1),
                "slicing_ms": round(t_slicing_calc_ms, 1),
                "fusion_ms": round(t_fusion_ms, 1),
                "slice_count": len(slice_coords),
            },
        }

        return fused
