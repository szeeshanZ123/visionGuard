"""
VisionGuard AI 2.0 — Visual Annotation Engine (OpenCV).

Generates high-contrast visual overlays with bounding boxes, defect IDs,
defect labels, and preliminary severity badges on civil infrastructure imagery.
Preserves the original image; operates strictly on a memory copy.
"""

import copy
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger("visionguard.annotator")

try:
    import cv2
except ImportError:
    cv2 = None

# High-contrast color palette (BGR format for OpenCV)
# Mapped by defect severity rating
SEVERITY_COLORS = {
    "critical": (30, 30, 235),     # Vibrant Crimson Red (#EF4444 in RGB)
    "high": (20, 115, 249),        # Vivid Orange (#F97316 in RGB)
    "moderate": (11, 158, 245),    # Vibrant Amber / Yellow-Orange (#F59E0B in RGB)
    "low": (246, 130, 59),         # Electric Blue (#3B82F6 in RGB)
    "uncertain": (139, 116, 100),   # Slate Gray (#64748B in RGB)
}

# Domain accent palettes
DOMAIN_BORDER_COLORS = {
    "road": (11, 158, 245),
    "home": (246, 130, 59),
}


class OpenCVAnnotationEngine:
    """
    Dedicated visual annotation service for VisionGuard AI.
    Renders clean, readable bounding boxes and identification banners
    using standard OpenCV primitives.
    """

    def __init__(self):
        pass

    def annotate_image(
        self,
        image: np.ndarray,
        defects: List[Dict[str, Any]],
        domain: str = "road",
    ) -> np.ndarray:
        """
        Draws localized bounding boxes and defect labels on a copy of the image.

        Args:
            image: Original BGR image as a NumPy array.
            defects: List of defect dictionaries containing 'bounding_box', 'id', 'type', 'severity'.
            domain: 'road' or 'home'

        Returns:
            A new annotated NumPy image array (original is untouched).
        """
        if image is None or cv2 is None:
            return image

        # Operate strictly on a copy to preserve the original image asset
        annotated = image.copy()
        h, w = annotated.shape[:2]

        if not defects:
            return annotated

        # Scale line thickness and font size dynamically based on image resolution
        base_dim = max(h, w)
        thickness = max(2, int(round(base_dim / 450.0)))
        font_scale = max(0.45, min(1.1, base_dim / 1100.0))
        font = cv2.FONT_HERSHEY_SIMPLEX

        # Track used label positions to prevent overlapping banner text
        occupied_label_regions = []

        for defect in defects:
            box = defect.get("bounding_box") or defect.get("normalized_box")
            if not box or not isinstance(box, dict):
                continue

            try:
                x1_norm = float(box.get("x1", 0.0))
                y1_norm = float(box.get("y1", 0.0))
                x2_norm = float(box.get("x2", 1.0))
                y2_norm = float(box.get("y2", 1.0))
            except (ValueError, TypeError):
                continue

            # Convert normalized [0, 1] coordinates into actual image pixel coordinates
            px1 = int(round(x1_norm * w))
            py1 = int(round(y1_norm * h))
            px2 = int(round(x2_norm * w))
            py2 = int(round(y2_norm * h))

            # Clamp coordinates to image boundaries
            px1 = max(0, min(w - 1, px1))
            py1 = max(0, min(h - 1, py1))
            px2 = max(0, min(w - 1, px2))
            py2 = max(0, min(h - 1, py2))

            # Skip degenerate boxes
            if px2 <= px1 or py2 <= py1:
                continue

            severity = str(defect.get("severity", "moderate")).lower().strip()
            color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["moderate"])

            # 1. Draw outer bounding box rectangle
            cv2.rectangle(annotated, (px1, py1), (px2, py2), color, thickness, cv2.LINE_AA)

            # 2. Draw subtle semi-transparent corner accents
            corner_len = min(20, max(8, int((px2 - px1) * 0.15)), int((py2 - py1) * 0.15))
            accent_thickness = thickness + 1
            # Top-left corner
            cv2.line(annotated, (px1, py1), (px1 + corner_len, py1), color, accent_thickness, cv2.LINE_AA)
            cv2.line(annotated, (px1, py1), (px1, py1 + corner_len), color, accent_thickness, cv2.LINE_AA)
            # Top-right corner
            cv2.line(annotated, (px2, py1), (px2 - corner_len, py1), color, accent_thickness, cv2.LINE_AA)
            cv2.line(annotated, (px2, py1), (px2, py1 + corner_len), color, accent_thickness, cv2.LINE_AA)
            # Bottom-left corner
            cv2.line(annotated, (px1, py2), (px1 + corner_len, py2), color, accent_thickness, cv2.LINE_AA)
            cv2.line(annotated, (px1, py2), (px1, py2 - corner_len), color, accent_thickness, cv2.LINE_AA)
            # Bottom-right corner
            cv2.line(annotated, (px2, py2), (px2 - corner_len, py2), color, accent_thickness, cv2.LINE_AA)
            cv2.line(annotated, (px2, py2), (px2, py2 - corner_len), color, accent_thickness, cv2.LINE_AA)

            # 3. Format defect label: "[D001] POTHOLE — MODERATE"
            defect_id = str(defect.get("id") or "DEFECT").upper()
            defect_type_str = str(defect.get("type") or defect.get("title") or "DISTRESS").replace("_", " ").upper()
            severity_str = severity.upper()
            label_text = f"[{defect_id}] {defect_type_str} - {severity_str}"

            # Calculate label text dimensions
            (text_w, text_h), baseline = cv2.getTextSize(label_text, font, font_scale, max(1, thickness - 1))
            pad_x = 8
            pad_y = 6

            # Determine label banner position (prefer above bounding box, else below or inside)
            label_y2 = py1
            label_y1 = label_y2 - (text_h + pad_y * 2)

            if label_y1 < 0:
                # If above top edge of image, place label just below or inside top edge
                label_y1 = py1
                label_y2 = label_y1 + (text_h + pad_y * 2)

            label_x1 = px1
            label_x2 = label_x1 + text_w + pad_x * 2
            if label_x2 > w:
                label_x2 = w
                label_x1 = max(0, label_x2 - (text_w + pad_x * 2))

            # Anti-collision check with existing banners
            for ox1, oy1, ox2, oy2 in occupied_label_regions:
                # Overlaps vertically and horizontally
                if not (label_x2 < ox1 or label_x1 > ox2 or label_y2 < oy1 or label_y1 > oy2):
                    # Shift down slightly
                    shift = (oy2 - label_y1) + 2
                    if (label_y2 + shift) < h:
                        label_y1 += shift
                        label_y2 += shift

            occupied_label_regions.append((label_x1, label_y1, label_x2, label_y2))

            # 4. Render solid background pill for crisp readability on any asphalt/wall texture
            cv2.rectangle(
                annotated,
                (label_x1, label_y1),
                (label_x2, label_y2),
                color,
                cv2.FILLED,
            )

            # Draw 1px dark border around pill for extra separation
            cv2.rectangle(
                annotated,
                (label_x1, label_y1),
                (label_x2, label_y2),
                (15, 23, 42),  # Slate dark
                1,
                cv2.LINE_AA,
            )

            # 5. Draw bold white text label inside pill
            text_pos_x = label_x1 + pad_x
            text_pos_y = label_y2 - pad_y
            cv2.putText(
                annotated,
                label_text,
                (text_pos_x, text_pos_y),
                font,
                font_scale,
                (255, 255, 255),  # Pure white
                max(1, thickness - 1),
                cv2.LINE_AA,
            )

        return annotated


# Global engine instance
annotation_engine = OpenCVAnnotationEngine()

