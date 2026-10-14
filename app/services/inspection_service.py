"""
Inspection and application coordination service for VisionGuard AI.
Orchestrates between database, preprocessing, and detection services.
"""

from typing import Dict, Any, Optional
import io
from database.db import check_db_health, init_db, get_db_connection
from ai.preprocessing.image_ops import validate_image_stream, load_image_as_opencv
from ai.detection.detector import DefectDetectionService


class InspectionService:
    """Service handling defect inspection workflows and persistence."""

    def __init__(self):
        self.detector = DefectDetectionService()

    @staticmethod
    def get_system_health() -> Dict[str, Any]:
        """Returns consolidated health and telemetry status."""
        db_health = check_db_health()
        return {
            "database": db_health,
            "ai_engine": "Phase 2 Research Staged",
            "storage_ready": db_health.get("connected", False),
        }

    @staticmethod
    def validate_upload(file_stream: io.BytesIO, filename: str):
        """Validates uploaded image and extracts technical attributes."""
        return validate_image_stream(file_stream, filename)

    @staticmethod
    def record_inspection(
        image_name: str,
        file_path: Optional[str] = None,
        defect_type: Optional[str] = None,
        confidence: Optional[float] = None,
        notes: Optional[str] = None
    ) -> int:
        """Stores a new inspection record into SQLite database."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO defect_inspections (image_name, file_path, defect_type, confidence, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (image_name, file_path, defect_type, confidence, notes)
        )
        conn.commit()
        record_id = cursor.lastrowid
        conn.close()
        return record_id
