"""
AI Detection engine module for VisionGuard AI.
"""

from .detector import (
    DefectDetectionService,
    HomeDefectDetectionService,
    RoadDefectDetectionService,
    CLASS_NAMES,
    CLASS_DISPLAY_NAMES,
    HOME_CLASS_NAMES,
    HOME_CLASS_DISPLAY_NAMES,
    DEFAULT_ROAD_MODEL_PATH,
    DEFAULT_HOME_MODEL_PATH,
)

__all__ = [
    "DefectDetectionService",
    "HomeDefectDetectionService",
    "RoadDefectDetectionService",
    "CLASS_NAMES",
    "CLASS_DISPLAY_NAMES",
    "HOME_CLASS_NAMES",
    "HOME_CLASS_DISPLAY_NAMES",
    "DEFAULT_ROAD_MODEL_PATH",
    "DEFAULT_HOME_MODEL_PATH",
]
