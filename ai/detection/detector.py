"""
Detection service and model inference layer for VisionGuard AI.

Adheres strictly to docs/PRD.md and docs/SYSTEM_ARCHITECTURE.md principles:
- Model inference is strictly decoupled from presentation code.
- Genuine predictions only; no simulated or mock bounding boxes.
- Real YOLOv8 object detection on road distress categories:
  D00 (Longitudinal Crack), D10 (Transverse Crack), D20 (Alligator Crack), D40 (Pothole).
- Robust handling when trained weights (best.pt) are missing or in Google Drive.
- Visual overlay engine rendering genuine detections using OpenCV.
"""

from typing import List, Dict, Any, Optional, Tuple
import base64
import os
import time
import cv2
import numpy as np

import logging

from ai.detection.slicer import SlicedInferenceEngine

from pathlib import Path

logger = logging.getLogger("visionguard.detector")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Anchor default model paths to the project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ROAD_MODEL_PATH = str(PROJECT_ROOT / "ai" / "models" / "best.pt")
DEFAULT_HOME_MODEL_PATH = str(PROJECT_ROOT / "ai" / "models" / "home_best.pt")
DEFAULT_MODEL_PATH = DEFAULT_ROAD_MODEL_PATH

# Canonical class taxonomy from Phase 3.4 (RDD2022 India dataset)
ROAD_CLASS_NAMES = {
    0: "D00_longitudinal_crack",
    1: "D10_transverse_crack",
    2: "D20_alligator_crack",
    3: "D40_pothole",
}

ROAD_CLASS_DISPLAY_NAMES = {
    "D00_longitudinal_crack": "Longitudinal Crack",
    "D10_transverse_crack": "Transverse Crack",
    "D20_alligator_crack": "Alligator Crack",
    "D40_pothole": "Pothole",
}

ROAD_CLASS_COLORS_BGR = {
    0: (0, 215, 255),    # Yellow / Gold (D00)
    1: (0, 140, 255),    # Orange (D10)
    2: (0, 0, 230),      # Red / Crimson (D20)
    3: (200, 50, 200),   # Purple / Magenta (D40)
}

# Canonical class taxonomy for Home & Building Defect Model
HOME_CLASS_NAMES = {
    0: "wall_crack",
    1: "damp_or_water_damage",
    2: "peeling_paint_or_plaster",
    3: "spalling_or_surface_damage",
}

HOME_CLASS_DISPLAY_NAMES = {
    "wall_crack": "Wall Crack",
    "damp_or_water_damage": "Damp / Water Damage",
    "peeling_paint_or_plaster": "Peeling Paint / Plaster",
    "spalling_or_surface_damage": "Spalling / Surface Damage",
}

HOME_CLASS_COLORS_BGR = {
    0: (0, 140, 255),    # Orange (Wall Crack)
    1: (255, 144, 30),   # Deep Sky Blue (Damp / Water Damage)
    2: (0, 215, 255),    # Gold / Yellow (Peeling Paint / Plaster)
    3: (0, 0, 220),      # Crimson / Red (Spalling / Surface Damage)
}

# Backward compatibility aliases for existing road defect tests and code
CLASS_NAMES = ROAD_CLASS_NAMES
CLASS_DISPLAY_NAMES = ROAD_CLASS_DISPLAY_NAMES
CLASS_COLORS_BGR = ROAD_CLASS_COLORS_BGR


def compute_box_iou(box1: Dict[str, float], box2: Dict[str, float]) -> float:
    """Computes Intersection-over-Union (IoU) between two bounding boxes."""
    x1 = max(float(box1.get("x1", 0)), float(box2.get("x1", 0)))
    y1 = max(float(box1.get("y1", 0)), float(box2.get("y1", 0)))
    x2 = min(float(box1.get("x2", 0)), float(box2.get("x2", 0)))
    y2 = min(float(box1.get("y2", 0)), float(box2.get("y2", 0)))
    inter_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, float(box1.get("x2", 0)) - float(box1.get("x1", 0))) * max(0.0, float(box1.get("y2", 0)) - float(box1.get("y1", 0)))
    area2 = max(0.0, float(box2.get("x2", 0)) - float(box2.get("x1", 0))) * max(0.0, float(box2.get("y2", 0)) - float(box2.get("y1", 0)))
    union_area = area1 + area2 - inter_area
    return inter_area / union_area if union_area > 0.0 else 0.0


def compute_box_iom(box1: Dict[str, float], box2: Dict[str, float]) -> float:
    """
    Computes Intersection-over-Minimum (IoM / containment) between two bounding boxes.
    Handles nested boxes where one bounding box is largely contained inside another.
    """
    x1 = max(float(box1.get("x1", 0)), float(box2.get("x1", 0)))
    y1 = max(float(box1.get("y1", 0)), float(box2.get("y1", 0)))
    x2 = min(float(box1.get("x2", 0)), float(box2.get("x2", 0)))
    y2 = min(float(box1.get("y2", 0)), float(box2.get("y2", 0)))
    inter_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, float(box1.get("x2", 0)) - float(box1.get("x1", 0))) * max(0.0, float(box1.get("y2", 0)) - float(box1.get("y1", 0)))
    area2 = max(0.0, float(box2.get("x2", 0)) - float(box2.get("x1", 0))) * max(0.0, float(box2.get("y2", 0)) - float(box2.get("y1", 0)))
    min_area = min(area1, area2)
    return inter_area / min_area if min_area > 0.0 else 0.0


def suppress_overlapping_detections(
    detections: List[Dict[str, Any]],
    same_class_iou_thresh: float = 0.45,
    cross_class_iou_thresh: Optional[float] = None,
    iou_threshold: Optional[float] = None,
    same_class_iom_thresh: float = 0.60,
    class_aware: bool = True,
) -> List[Dict[str, Any]]:
    """
    Suppresses redundant overlapping bounding boxes using Non-Maximum Suppression (NMS).
    Applies IoU and containment (IoM) suppression for same-class duplicates.
    By default (class_aware=True), detections from different classes are strictly preserved.
    """
    if not detections or len(detections) <= 1:
        return detections

    if iou_threshold is not None:
        same_class_iou_thresh = float(iou_threshold)

    sorted_dets = sorted(detections, key=lambda d: d.get("confidence", 0.0), reverse=True)
    kept: List[Dict[str, Any]] = []

    def same_class(d1: Dict[str, Any], d2: Dict[str, Any]) -> bool:
        if d1.get("class_id") is not None and d2.get("class_id") is not None:
            return d1["class_id"] == d2["class_id"]
        if d1.get("class_name") and d2.get("class_name"):
            return d1["class_name"] == d2["class_name"]
        if d1.get("distress_category") and d2.get("distress_category"):
            return d1["distress_category"] == d2["distress_category"]
        return True

    for cand in sorted_dets:
        cand_bbox = cand.get("bbox", {})
        suppress = False
        for chosen in kept:
            chosen_bbox = chosen.get("bbox", {})
            is_same = same_class(cand, chosen)
            iou = compute_box_iou(cand_bbox, chosen_bbox)
            iom = compute_box_iom(cand_bbox, chosen_bbox)

            if is_same:
                if iou >= same_class_iou_thresh or iom >= same_class_iom_thresh:
                    suppress = True
                    logger.debug(
                        "Suppressed same-class duplicate [%s conf=%.3f] by [%s conf=%.3f] (IoU=%.3f, IoM=%.3f)",
                        cand.get("class_name") or cand.get("distress_category"),
                        cand.get("confidence", 0.0),
                        chosen.get("class_name") or chosen.get("distress_category"),
                        chosen.get("confidence", 0.0),
                        iou,
                        iom,
                    )
                    break
            else:
                # Different classes: only suppress if class_aware is explicitly set to False
                if not class_aware and cross_class_iou_thresh is not None and iou > cross_class_iou_thresh:
                    suppress = True
                    break

        if not suppress:
            kept.append(cand)

    return kept


class DefectDetectionService:
    """
    Defect detection engine interface.
    Manages genuine model loading, inference, and OpenCV overlay generation.
    Supports both 'road' (RDD2022) and 'home' (Building Defects) domains.
    """

    def __init__(self, model_path: Optional[str] = None, domain: str = "road", lazy: bool = False):
        self.domain = (domain or "road").lower().strip()
        if self.domain not in ("road", "home"):
            self.domain = "road"

        if model_path is not None:
            self.model_path = model_path
        elif self.domain == "home":
            self.model_path = os.getenv("VISIONGUARD_HOME_MODEL_PATH", DEFAULT_HOME_MODEL_PATH)
        else:
            self.model_path = os.getenv("VISIONGUARD_MODEL_PATH", DEFAULT_ROAD_MODEL_PATH)

        self.model = None
        self.is_loaded = False
        self.status_message = "Model uninitialized"

        model_name = (
            "YOLOv8 Home Defect Detector"
            if self.domain == "home"
            else "YOLOv8 Nano (RDD2022 India)"
        )
        supported_classes = [self.classes_map[i] for i in sorted(self.classes_map.keys())]

        self.model_info = {
            "name": model_name,
            "domain": self.domain,
            "version": "1.0",
            "supported_classes": supported_classes,
            "checkpoint_path": self.model_path,
            "inference_hardware": "CPU/CUDA",
        }
        self.last_inference_stats = {
            "raw_candidate_count": 0,
            "top_raw_confidence": 0.0,
            "top_raw_class": "",
            "suggested_threshold": None,
        }
        # Sliced / Tiled inference engine for capturing continuous cracks at native resolution
        # Tile size 512, overlap 0.20, max_slices 12 for CPU-friendly high-resolution crack preservation
        self.slicer = SlicedInferenceEngine(slice_size=512, overlap_ratio=0.20, merge_iou_threshold=0.40, max_slices=12)

        if lazy:
            # On-demand loading: verify file existence and metadata without allocating weights to RAM
            resolved = self._resolve_model_path()
            if resolved and os.path.isfile(resolved):
                self.model_path = resolved
                self.model_info["checkpoint_path"] = resolved
                self.is_loaded = True
                self.status_message = f"Model verified and ready (on-demand loading) from '{resolved}'"
            else:
                self.is_loaded = False
                self.status_message = f"Model checkpoint not found at '{self.model_path}'"
        else:
            # Eagerly load checkpoint into memory
            self.load_model()

    @property
    def classes_map(self) -> Dict[int, str]:
        return HOME_CLASS_NAMES if self.domain == "home" else ROAD_CLASS_NAMES

    @property
    def display_names_map(self) -> Dict[str, str]:
        return HOME_CLASS_DISPLAY_NAMES if self.domain == "home" else ROAD_CLASS_DISPLAY_NAMES

    @property
    def colors_bgr_map(self) -> Dict[int, Tuple[int, int, int]]:
        return HOME_CLASS_COLORS_BGR if self.domain == "home" else ROAD_CLASS_COLORS_BGR

    def _resolve_model_path(self) -> Optional[str]:
        """Resolves model path across candidate locations for path independence."""
        candidates = [
            self.model_path,
            str(PROJECT_ROOT / self.model_path) if self.model_path else None,
            str(PROJECT_ROOT / "ai" / "models" / os.path.basename(self.model_path)) if self.model_path else None,
            os.path.abspath(self.model_path) if self.model_path else None,
            os.path.join(os.getcwd(), self.model_path) if self.model_path else None,
        ]
        for cand in candidates:
            if cand and os.path.isfile(cand):
                return os.path.abspath(cand)
        return None

    def load_model(self) -> bool:
        """
        Loads the genuine YOLOv8 defect detection model into memory.

        Returns:
            True if model checkpoint was successfully loaded, False otherwise.
        """
        # Multi-location candidate resolution to ensure path-independence
        resolved_path = self._resolve_model_path()

        if not resolved_path:
            self.is_loaded = False
            self.model = None
            if self.domain == "home":
                self.status_message = (
                    f"Home model checkpoint not found at '{self.model_path}'. "
                    "If trained in Google Colab, download 'home_best.pt' from your Google Drive "
                    "('VisionGuard_Artifacts/home_best.pt') or run "
                    "'from google.colab import files; files.download(BEST_WEIGHTS_PATH)' "
                    f"and place it at '{self.model_path}'."
                )
            else:
                self.status_message = (
                    f"Model checkpoint not found at '{self.model_path}'. "
                    "If trained in Google Colab, download 'best.pt' from your Google Drive "
                    "('VisionGuard_Artifacts/best.pt') or run "
                    "'from google.colab import files; files.download(BEST_WEIGHTS_PATH)' "
                    f"and place it at '{self.model_path}'."
                )
            return False

        self.model_path = resolved_path
        self.model_info["checkpoint_path"] = resolved_path

        try:
            import gc
            try:
                cv2.setNumThreads(1)
            except Exception:
                pass
            try:
                import torch
                # Limit PyTorch CPU thread allocation to prevent thread pool memory explosion
                torch.set_num_threads(1)
                if hasattr(torch, "set_num_interop_threads"):
                    try:
                        torch.set_num_interop_threads(1)
                    except RuntimeError:
                        pass
            except Exception:
                pass

            from ultralytics import YOLO

            t_load_start = time.perf_counter()
            self.model = YOLO(resolved_path)
            t_load_elapsed = time.perf_counter() - t_load_start
            self.is_loaded = True
            self.status_message = f"Model loaded successfully from '{resolved_path}'"

            # Reconcile class names with checkpoint metadata if available
            names = getattr(self.model, "names", self.classes_map)
            if isinstance(names, dict):
                classes = [names.get(i, self.classes_map.get(i, f"Class_{i}")) for i in sorted(names.keys())]
            else:
                classes = list(names)

            self.model_info["classes"] = classes
            self.model_info["checkpoint_path"] = self.model_path
            self.model_info["domain"] = self.domain

            # Single warmup pass in inference mode to compile graph without caching activations
            try:
                import torch
                with torch.inference_mode():
                    self.model.predict(source=np.zeros((64, 64, 3), dtype=np.uint8), conf=0.25, verbose=False)
                gc.collect()
            except Exception as e_warm:
                logger.debug("Model warmup pass skipped: %s", e_warm)

            logger.info(
                "Model '%s' loaded once in %.3fs from '%s' (domain=%s, classes=%d)",
                self.model_info["name"],
                t_load_elapsed,
                resolved_path,
                self.domain,
                len(classes),
            )
            return True

        except Exception as exc:
            self.is_loaded = False
            self.model = None
            self.status_message = f"Failed to load YOLO model from '{self.model_path}': {str(exc)}"
            return False

    def detect(
        self,
        image_bgr: np.ndarray,
        conf_threshold: float = 0.25,
        raise_if_unloaded: bool = False,
        inspection_mode: str = "standard",
        slice_size: Optional[int] = None,
        overlap_ratio: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Runs defect detection on an OpenCV BGR image using the authentic model.
        Supports standard full-frame inference or high-resolution tiled/sliced inference.

        Args:
            image_bgr: NumPy ndarray in BGR format.
            conf_threshold: Minimum detection confidence threshold (default 0.25).
            raise_if_unloaded: Whether to raise FileNotFoundError if weights are missing.
            inspection_mode: 'standard' (full image) or 'tiled'/'sliced' (overlapping high-res tiles).
            slice_size: Custom tile size in pixels (for tiled mode).
            overlap_ratio: Overlap ratio between adjacent tiles (e.g. 0.20 = 20%).

        Returns:
            List of detection dicts: [{
                'class_id': int,
                'class_name': str,
                'distress_category': str,
                'confidence': float,
                'bbox': {
                    'x1': float, 'y1': float, 'x2': float, 'y2': float,
                    'width': float, 'height': float,
                    'aspect_ratio': float, 'pixel_area': float
                },
                'disclaimer': str
            }]
            Strict guardrail: Returns empty list if no defects are detected or image is invalid.
        """
        mode = (inspection_mode or "standard").lower().strip()
        if mode in ("tiled", "sliced"):
            return self.detect_sliced(
                image_bgr=image_bgr,
                conf_threshold=conf_threshold,
                slice_size=slice_size,
                overlap_ratio=overlap_ratio,
                fuse_with_global=True,
                raise_if_unloaded=raise_if_unloaded,
            )

        return self._detect_standard(
            image_bgr=image_bgr,
            conf_threshold=conf_threshold,
            raise_if_unloaded=raise_if_unloaded,
        )

    def detect_sliced(
        self,
        image_bgr: np.ndarray,
        conf_threshold: float = 0.25,
        slice_size: Optional[int] = None,
        overlap_ratio: Optional[float] = None,
        fuse_with_global: bool = True,
        raise_if_unloaded: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Runs high-resolution sliced/tiled defect detection across overlapping image patches.
        Preserves fine crack continuity and prevents downsampling degradation.
        """
        if not self.is_loaded:
            if raise_if_unloaded:
                raise FileNotFoundError(self.status_message)
            return []

        if self.model is None:
            if not self.load_model():
                if raise_if_unloaded:
                    raise FileNotFoundError(self.status_message)
                return []

        if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.size == 0:
            return []

        detections = self.slicer.execute_sliced_inference(
            detector=self,
            image_bgr=image_bgr,
            conf_threshold=conf_threshold,
            slice_size=slice_size,
            overlap_ratio=overlap_ratio,
            fuse_with_global=fuse_with_global,
            raise_if_unloaded=raise_if_unloaded,
        )

        # Synchronize telemetry stats from slicer
        if hasattr(self.slicer, "last_sliced_stats"):
            self.last_inference_stats = dict(self.slicer.last_sliced_stats)

        # Consistent suppression check across all detections
        detections = suppress_overlapping_detections(
            detections,
            same_class_iou_thresh=self.slicer.merge_iou_threshold,
            same_class_iom_thresh=self.slicer.merge_iom_threshold,
            class_aware=True,
        )

        return detections

    def _detect_standard(
        self,
        image_bgr: np.ndarray,
        conf_threshold: float = 0.25,
        raise_if_unloaded: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Internal execution for single-frame full-image YOLOv8 inference.
        """
        if not self.is_loaded:
            if raise_if_unloaded:
                raise FileNotFoundError(self.status_message)
            return []

        if self.model is None:
            if not self.load_model():
                if raise_if_unloaded:
                    raise FileNotFoundError(self.status_message)
                return []

        if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.size == 0:
            return []

        try:
            t0 = time.perf_counter()
            # Optimize for CPU: predict directly at caller's conf_threshold under inference_mode
            # Eliminates evaluating thousands of near-zero noise candidates on CPU
            import torch
            with torch.inference_mode():
                results = self.model.predict(
                    source=image_bgr,
                    conf=conf_threshold,
                    verbose=False,
                )
            t_infer = time.perf_counter() - t0

            detections: List[Dict[str, Any]] = []
            if not results or len(results) == 0 or results[0].boxes is None:
                self.last_inference_stats = {
                    "raw_candidate_count": 0,
                    "top_raw_confidence": 0.0,
                    "top_raw_class": "",
                    "suggested_threshold": None,
                }
                return detections

            boxes = results[0].boxes
            raw_count = len(boxes)
            if raw_count == 0:
                self.last_inference_stats = {
                    "raw_candidate_count": 0,
                    "top_raw_confidence": 0.0,
                    "top_raw_class": "",
                    "suggested_threshold": None,
                }
                return detections

            img_h, img_w = image_bgr.shape[:2]
            model_names = getattr(self.model, "names", self.classes_map)

            # Vectorized tensor-to-numpy conversion for zero-overhead CPU loop
            xyxy_arr = boxes.xyxy.cpu().numpy()
            conf_arr = boxes.conf.cpu().numpy()
            cls_arr = boxes.cls.cpu().numpy()
            del boxes
            del results

            top_raw_conf = float(np.max(conf_arr)) if raw_count > 0 else 0.0
            best_idx = int(np.argmax(conf_arr)) if raw_count > 0 else 0
            top_raw_cls_id = int(cls_arr[best_idx]) if raw_count > 0 else 0
            if isinstance(model_names, dict):
                top_raw_cls_raw = model_names.get(top_raw_cls_id, self.classes_map.get(top_raw_cls_id, f"Class_{top_raw_cls_id}"))
            elif isinstance(model_names, (list, tuple)) and top_raw_cls_id < len(model_names):
                top_raw_cls_raw = model_names[top_raw_cls_id]
            else:
                top_raw_cls_raw = f"Class_{top_raw_cls_id}"
            top_raw_class = self.display_names_map.get(top_raw_cls_raw, top_raw_cls_raw.replace("_", " ").title())

            self.last_inference_stats = {
                "raw_candidate_count": raw_count,
                "top_raw_confidence": round(top_raw_conf, 4),
                "top_raw_class": top_raw_class,
                "suggested_threshold": None,
            }

            for i in range(raw_count):
                conf = float(conf_arr[i])
                if conf < conf_threshold:
                    continue

                cls_id = int(cls_arr[i])
                x1 = max(0.0, min(float(img_w), float(xyxy_arr[i][0])))
                y1 = max(0.0, min(float(img_h), float(xyxy_arr[i][1])))
                x2 = max(0.0, min(float(img_w), float(xyxy_arr[i][2])))
                y2 = max(0.0, min(float(img_h), float(xyxy_arr[i][3])))

                box_w = max(0.0, x2 - x1)
                box_h = max(0.0, y2 - y1)
                if box_w <= 0.0 or box_h <= 0.0:
                    continue

                if isinstance(model_names, dict):
                    cls_raw = model_names.get(cls_id, self.classes_map.get(cls_id, f"Class_{cls_id}"))
                elif isinstance(model_names, (list, tuple)) and cls_id < len(model_names):
                    cls_raw = model_names[cls_id]
                else:
                    cls_raw = f"Class_{cls_id}"

                distress_category = self.display_names_map.get(
                    cls_raw, cls_raw.replace("_", " ").title()
                )

                disclaimer = (
                    "Detection confidence is statistical likelihood, not building structural integrity or physical safety."
                    if self.domain == "home"
                    else "Detection confidence is statistical likelihood, not pavement structural safety."
                )
                detections.append({
                    "domain": self.domain,
                    "class_id": cls_id,
                    "class_name": cls_raw,
                    "distress_category": distress_category,
                    "confidence": round(conf, 4),
                    "bbox": {
                        "x1": round(x1, 1),
                        "y1": round(y1, 1),
                        "x2": round(x2, 1),
                        "y2": round(y2, 1),
                        "width": round(box_w, 1),
                        "height": round(box_h, 1),
                        "aspect_ratio": round(box_w / box_h, 3) if box_h > 0 else 0.0,
                        "pixel_area": round(box_w * box_h, 1),
                    },
                    "disclaimer": disclaimer,
                })

            logger.info(
                "YOLO inference (%s): %d detection(s) at conf >= %.2f in %.3fs (raw_count=%d, top_conf=%.4f [%s])",
                self.domain,
                len(detections),
                conf_threshold,
                t_infer,
                raw_count,
                top_raw_conf,
                top_raw_class,
            )

            # Suppress overlapping boxes to avoid overwhelming user interface
            detections = suppress_overlapping_detections(
                detections,
                same_class_iou_thresh=0.45,
                same_class_iom_thresh=0.60,
                class_aware=True,
            )

            self.last_inference_stats = {
                "raw_candidate_count": raw_count,
                "top_raw_confidence": round(top_raw_conf, 4),
                "top_raw_class": top_raw_class,
                "suggested_threshold": round(max(0.05, top_raw_conf - 0.004), 2) if top_raw_conf >= 0.045 else None,
            }

            logger.info(
                "Threshold filtering complete: %d of %d raw detection(s) meet confidence threshold >= %.2f (domain=%s)",
                len(detections),
                raw_count,
                conf_threshold,
                self.domain,
            )
            return detections

        except Exception as exc:
            # Re-raise if instructed, otherwise return empty list safely
            if raise_if_unloaded:
                raise RuntimeError(f"Error during model inference: {str(exc)}")
            return []

    @classmethod
    def draw_annotations(
        cls,
        image_bgr: np.ndarray,
        detections: List[Dict[str, Any]],
        domain: Optional[str] = None,
    ) -> np.ndarray:
        """
        Renders genuine visual overlays (bounding boxes and labels) using OpenCV.
        Never fabricates annotations; if detections is empty, returns an unaltered copy.

        Args:
            image_bgr: Original image as BGR NumPy array.
            detections: List of detection dictionaries.
            domain: Optional inspection domain ('road' or 'home') to pick color palettes.

        Returns:
            Annotated BGR NumPy array.
        """
        if image_bgr is None:
            raise ValueError("Input image cannot be None")

        annotated = image_bgr.copy()
        if not detections:
            return annotated

        h, w = annotated.shape[:2]

        for det in detections:
            bbox = det.get("bbox", {})
            x1 = int(round(bbox.get("x1", 0)))
            y1 = int(round(bbox.get("y1", 0)))
            x2 = int(round(bbox.get("x2", 0)))
            y2 = int(round(bbox.get("y2", 0)))

            # Clip coordinates to image boundary
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))

            cls_id = det.get("class_id", 0)
            conf = det.get("confidence", 0.0)
            category = det.get("distress_category", det.get("class_name", "Defect"))

            det_domain = det.get("domain") or domain or "road"
            colors = HOME_CLASS_COLORS_BGR if det_domain == "home" else ROAD_CLASS_COLORS_BGR
            color = colors.get(cls_id, (0, 255, 0))

            # Draw bounding rectangle
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness=2)

            # Prepare label text: "Category: 85.2%"
            label_text = f"{category}: {conf * 100:.1f}%"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            thickness = 1

            (text_w, text_h), baseline = cv2.getTextSize(label_text, font, font_scale, thickness)

            # Compute label background coordinates
            pill_y1 = max(0, y1 - text_h - 8)
            pill_y2 = y1
            pill_x1 = x1
            pill_x2 = min(w, x1 + text_w + 10)

            # Draw filled label pill
            cv2.rectangle(annotated, (pill_x1, pill_y1), (pill_x2, pill_y2), color, cv2.FILLED)

            # Draw white text over label pill
            text_x = pill_x1 + 5
            text_y = pill_y2 - 4
            cv2.putText(
                annotated,
                label_text,
                (text_x, text_y),
                font,
                font_scale,
                (255, 255, 255),
                thickness,
                cv2.LINE_AA,
            )

        return annotated

    @staticmethod
    def encode_image_to_base64(image_bgr: np.ndarray, ext: str = ".jpg") -> str:
        """
        Encodes an OpenCV BGR image array into a Base64 data URL string.
        """
        if image_bgr is None:
            return ""
        success, encoded = cv2.imencode(ext, image_bgr)
        if not success:
            return ""
        b64_str = base64.b64encode(encoded).decode("utf-8")
        mime = "image/jpeg" if ext.lower() in [".jpg", ".jpeg"] else "image/png"
        return f"data:{mime};base64,{b64_str}"


class HomeDefectDetectionService(DefectDetectionService):
    """Specialized Home & Building Defect Detection Service."""

    def __init__(self, model_path: Optional[str] = None, lazy: bool = True):
        super().__init__(model_path=model_path, domain="home", lazy=lazy)


class RoadDefectDetectionService(DefectDetectionService):
    """Specialized Road Defect Detection Service."""

    def __init__(self, model_path: Optional[str] = None):
        super().__init__(model_path=model_path, domain="road")


__all__ = [
    "DefectDetectionService",
    "HomeDefectDetectionService",
    "RoadDefectDetectionService",
    "SlicedInferenceEngine",
    "CLASS_NAMES",
    "CLASS_DISPLAY_NAMES",
    "CLASS_COLORS_BGR",
    "DEFAULT_MODEL_PATH",
    "ROAD_CLASS_NAMES",
    "ROAD_CLASS_DISPLAY_NAMES",
    "ROAD_CLASS_COLORS_BGR",
    "DEFAULT_ROAD_MODEL_PATH",
    "HOME_CLASS_NAMES",
    "HOME_CLASS_DISPLAY_NAMES",
    "HOME_CLASS_COLORS_BGR",
    "DEFAULT_HOME_MODEL_PATH",
    "suppress_overlapping_detections",
    "compute_box_iou",
]
