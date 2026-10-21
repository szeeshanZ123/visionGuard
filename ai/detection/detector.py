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
import cv2
import numpy as np

import logging

from ai.detection.slicer import SlicedInferenceEngine

logger = logging.getLogger("visionguard.detector")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

DEFAULT_MODEL_PATH = os.path.join("ai", "models", "best.pt")

# Canonical class taxonomy from Phase 3.4 (RDD2022 India dataset)
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

# Distinguishable BGR colors for OpenCV rendering
CLASS_COLORS_BGR = {
    0: (0, 215, 255),    # Yellow / Gold (D00)
    1: (0, 140, 255),    # Orange (D10)
    2: (0, 0, 230),      # Red / Crimson (D20)
    3: (200, 50, 200),   # Purple / Magenta (D40)
}


class DefectDetectionService:
    """
    Defect detection engine interface.
    Manages genuine model loading, inference, and OpenCV overlay generation.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or os.getenv("VISIONGUARD_MODEL_PATH", DEFAULT_MODEL_PATH)
        self.model = None
        self.is_loaded = False
        self.status_message = "Model uninitialized"
        self.model_info = {
            "name": "YOLOv8 Nano (RDD2022 India)",
            "version": "1.0",
            "supported_classes": [CLASS_NAMES[i] for i in sorted(CLASS_NAMES.keys())],
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
        self.slicer = SlicedInferenceEngine(slice_size=384, overlap_ratio=0.20, merge_iou_threshold=0.40)

        # Attempt to load checkpoint if present
        self.load_model()

    def load_model(self) -> bool:
        """
        Loads the genuine YOLOv8 defect detection model into memory.

        Returns:
            True if model checkpoint was successfully loaded, False otherwise.
        """
        if not os.path.exists(self.model_path):
            self.is_loaded = False
            self.model = None
            self.status_message = (
                f"Model checkpoint not found at '{self.model_path}'. "
                "If trained in Google Colab, download 'best.pt' from your Google Drive "
                "('VisionGuard_Artifacts/best.pt') or run "
                "'from google.colab import files; files.download(BEST_WEIGHTS_PATH)' "
                f"and place it at '{self.model_path}'."
            )
            return False

        try:
            from ultralytics import YOLO

            self.model = YOLO(self.model_path)
            self.is_loaded = True
            self.status_message = f"Model loaded successfully from '{self.model_path}'"

            # Reconcile class names with checkpoint metadata if available
            names = getattr(self.model, "names", CLASS_NAMES)
            if isinstance(names, dict):
                classes = [names.get(i, CLASS_NAMES.get(i, f"Class_{i}")) for i in sorted(names.keys())]
            else:
                classes = list(names)

            self.model_info["classes"] = classes
            self.model_info["checkpoint_path"] = self.model_path
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

        if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.size == 0:
            return []

        try:
            # Predict using min(conf_threshold, 0.01) so raw candidates are visible for logging
            diagnostic_threshold = min(conf_threshold, 0.01)
            results = self.model.predict(
                source=image_bgr,
                conf=diagnostic_threshold,
                verbose=False,
            )

            detections: List[Dict[str, Any]] = []
            if not results or len(results) == 0:
                logger.info("Zero raw candidate detections found at diagnostic threshold (conf=%.4f).", diagnostic_threshold)
                self.last_inference_stats = {
                    "raw_candidate_count": 0,
                    "top_raw_confidence": 0.0,
                    "top_raw_class": "",
                    "suggested_threshold": None,
                }
                return detections

            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                logger.info("Zero raw candidate boxes found at diagnostic threshold (conf=%.4f).", diagnostic_threshold)
                self.last_inference_stats = {
                    "raw_candidate_count": 0,
                    "top_raw_confidence": 0.0,
                    "top_raw_class": "",
                    "suggested_threshold": None,
                }
                return detections

            model_names = getattr(self.model, "names", CLASS_NAMES)
            raw_count = len(boxes)
            logger.info(
                "YOLO inference: %d raw candidate box(es) detected before filtering (target threshold >= %.2f):",
                raw_count,
                conf_threshold,
            )

            top_raw_conf = 0.0
            top_raw_class = ""

            for i in range(raw_count):
                xyxy = boxes.xyxy[i].cpu().numpy().tolist()
                x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
                conf = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())

                if isinstance(model_names, dict):
                    cls_raw = model_names.get(cls_id, CLASS_NAMES.get(cls_id, f"Class_{cls_id}"))
                elif isinstance(model_names, (list, tuple)) and cls_id < len(model_names):
                    cls_raw = model_names[cls_id]
                else:
                    cls_raw = f"Class_{cls_id}"

                distress_category = CLASS_DISPLAY_NAMES.get(
                    cls_raw, cls_raw.replace("_", " ").title()
                )

                if conf > top_raw_conf:
                    top_raw_conf = conf
                    top_raw_class = distress_category

                box_w = max(0.0, x2 - x1)
                box_h = max(0.0, y2 - y1)
                aspect_ratio = round(box_w / box_h, 3) if box_h > 0 else 0.0
                pixel_area = round(box_w * box_h, 1)

                is_kept = conf >= conf_threshold
                logger.info(
                    "  [Raw Detection #%d] class_id=%d, class_name=%s (%s), conf=%.4f, bbox=[%.1f, %.1f, %.1f, %.1f] -> %s",
                    i + 1,
                    cls_id,
                    cls_raw,
                    distress_category,
                    conf,
                    x1,
                    y1,
                    x2,
                    y2,
                    "ACCEPTED" if is_kept else "FILTERED OUT",
                )

                if is_kept:
                    detections.append({
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
                            "aspect_ratio": aspect_ratio,
                            "pixel_area": pixel_area,
                        },
                        "disclaimer": "Detection confidence is statistical likelihood, not pavement structural safety.",
                    })

            self.last_inference_stats = {
                "raw_candidate_count": raw_count,
                "top_raw_confidence": round(top_raw_conf, 4),
                "top_raw_class": top_raw_class,
                "suggested_threshold": round(max(0.05, top_raw_conf - 0.004), 2) if top_raw_conf >= 0.045 else None,
            }

            logger.info(
                "Threshold filtering complete: %d of %d raw detection(s) meet confidence threshold >= %.2f",
                len(detections),
                raw_count,
                conf_threshold,
            )
            return detections

        except Exception as exc:
            # Re-raise if instructed, otherwise return empty list safely
            if raise_if_unloaded:
                raise RuntimeError(f"Error during model inference: {str(exc)}")
            return []

    @staticmethod
    def draw_annotations(
        image_bgr: np.ndarray,
        detections: List[Dict[str, Any]],
    ) -> np.ndarray:
        """
        Renders genuine visual overlays (bounding boxes and labels) using OpenCV.
        Never fabricates annotations; if detections is empty, returns an unaltered copy.

        Args:
            image_bgr: Original image as BGR NumPy array.
            detections: List of detection dictionaries.

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

            color = CLASS_COLORS_BGR.get(cls_id, (0, 255, 0))

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


__all__ = [
    "DefectDetectionService",
    "SlicedInferenceEngine",
    "CLASS_NAMES",
    "CLASS_DISPLAY_NAMES",
    "CLASS_COLORS_BGR",
    "DEFAULT_MODEL_PATH",
]
