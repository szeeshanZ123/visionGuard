"""
Inspection and application coordination service for VisionGuard AI.

Orchestrates between database, preprocessing, and detection services.
Adheres strictly to docs/PRD.md and docs/SYSTEM_ARCHITECTURE.md principles:
- Pure coordination layer; does not modify genuine detection outputs.
- Keeps model statistical confidence distinct from structural road safety.
"""

from typing import Dict, Any, Optional, List, Tuple
import io
import os
import cv2
import numpy as np

from database.db import check_db_health, init_db, get_db_connection
from ai.preprocessing.image_ops import (
    validate_image_stream,
    load_image_as_opencv,
    SUPPORTED_EXTENSIONS,
    MAX_RECOMMENDED_SIZE_MB,
)
from ai.detection.detector import (
    DefectDetectionService,
    CLASS_NAMES,
    CLASS_DISPLAY_NAMES,
)


class InspectionService:
    """Service handling defect inspection workflows and persistence."""

    def __init__(
        self,
        detector: Optional[DefectDetectionService] = None,
        home_detector: Optional[DefectDetectionService] = None,
    ):
        self.detector = detector or DefectDetectionService(domain="road")
        self.road_detector = self.detector
        self.home_detector = home_detector or DefectDetectionService(domain="home")

    def get_system_health(self) -> Dict[str, Any]:
        """Returns consolidated health and telemetry status."""
        db_health = check_db_health()
        return {
            "database": db_health,
            "ai_engine": {
                "loaded": self.detector.is_loaded,
                "status_message": self.detector.status_message,
                "model_info": self.detector.model_info,
            },
            "home_engine": {
                "loaded": self.home_detector.is_loaded,
                "status_message": self.home_detector.status_message,
                "model_info": self.home_detector.model_info,
            },
            "storage_ready": db_health.get("connected", False),
            "limits": {
                "max_file_size_mb": MAX_RECOMMENDED_SIZE_MB,
                "supported_formats": sorted(list(SUPPORTED_EXTENSIONS)),
            },
        }

    @staticmethod
    def validate_upload(file_stream: io.BytesIO, filename: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Validates uploaded image and extracts technical attributes."""
        return validate_image_stream(file_stream, filename)

    def process_inspection(
        self,
        file_bytes: io.BytesIO,
        filename: str,
        conf_threshold: float = 0.25,
        save_record: bool = False,
        domain: str = "road",
    ) -> Dict[str, Any]:
        """
        Executes end-to-end inspection:
        1. Validates image stream.
        2. Decodes image array via OpenCV.
        3. Routes to genuine YOLOv8 road or home model.
        4. Renders genuine visual overlay on detected distresses.
        5. Optionally logs inspection to local SQLite database.

        Returns structured result dict.
        """
        norm_domain = (domain or "road").lower().strip()
        if norm_domain not in ("road", "home"):
            norm_domain = "road"

        active_detector = self.home_detector if norm_domain == "home" else self.detector

        is_valid, err_msg, metadata = self.validate_upload(file_bytes, filename)
        if not is_valid:
            return {
                "success": False,
                "error": err_msg or "Validation failed",
                "error_code": "INVALID_IMAGE",
                "domain": norm_domain,
            }

        # Check model loaded status
        if not active_detector.is_loaded:
            instructions = (
                "Place your trained 'home_best.pt' file in 'ai/models/home_best.pt'. "
                "If trained in Google Colab, download it from Google Drive "
                "('VisionGuard_Artifacts/home_best.pt')."
            ) if norm_domain == "home" else (
                "Place your trained 'best.pt' file in 'ai/models/best.pt'. "
                "If trained in Google Colab, download it from Google Drive "
                "('VisionGuard_Artifacts/best.pt')."
            )
            return {
                "success": False,
                "error": active_detector.status_message,
                "error_code": "MODEL_WEIGHTS_MISSING",
                "domain": norm_domain,
                "metadata": metadata,
                "instructions": instructions,
            }

        # Decode image
        cv_img = load_image_as_opencv(file_bytes)
        if cv_img is None:
            return {
                "success": False,
                "error": "Failed to decode image with OpenCV.",
                "error_code": "IMAGE_DECODE_FAILED",
                "domain": norm_domain,
            }

        # Run genuine detection
        detections = active_detector.detect(cv_img, conf_threshold=conf_threshold)

        # Generate genuine visual overlay
        annotated_bgr = active_detector.draw_annotations(cv_img, detections)
        annotated_b64 = active_detector.encode_image_to_base64(annotated_bgr)

        # Record into database if requested
        record_id = None
        if save_record:
            summary_defect = detections[0]["class_name"] if detections else "none"
            top_conf = max([d["confidence"] for d in detections], default=0.0)
            record_id = self.record_inspection(
                image_name=filename,
                defect_type=summary_defect,
                confidence=top_conf,
                notes=f"Detections: {len(detections)} instances ({norm_domain})",
                inspection_type=norm_domain,
            )

        disclaimer = (
            "Notice: Detection confidence measures model statistical likelihood, "
            "not building structural integrity or physical safety."
        ) if norm_domain == "home" else (
            "Notice: Detection confidence measures model statistical likelihood, "
            "not physical crack severity, cavity depth, or roadway structural safety."
        )

        return {
            "success": True,
            "domain": norm_domain,
            "filename": filename,
            "metadata": metadata,
            "model_info": active_detector.model_info,
            "confidence_threshold": conf_threshold,
            "detections": detections,
            "defect_count": len(detections),
            "annotated_image_base64": annotated_b64,
            "inspection_record_id": record_id,
            "disclaimer": disclaimer,
        }

    @staticmethod
    def record_inspection(
        image_name: str,
        file_path: Optional[str] = None,
        defect_type: Optional[str] = None,
        confidence: Optional[float] = None,
        notes: Optional[str] = None,
        inspection_type: str = "road",
    ) -> int:
        """Stores a new inspection record into SQLite database."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO defect_inspections (image_name, file_path, defect_type, confidence, notes, inspection_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (image_name, file_path, defect_type, confidence, notes, inspection_type),
        )
        conn.commit()
        record_id = cursor.lastrowid
        conn.close()
        return record_id


__all__ = ["InspectionService"]
