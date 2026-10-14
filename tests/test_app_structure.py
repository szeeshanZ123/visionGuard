"""Smoke tests verifying overall application module integrity and starter zip compliance."""

import os
from pathlib import Path


def test_starter_zip_docs_present():
    """Verifies that all 8 planning documents from the starter zip exist."""
    docs_dir = Path(__file__).parent.parent / "docs"
    expected_docs = [
        "DATASET_AND_MODEL_RESEARCH.md",
        "DEVELOPMENT_ROADMAP.md",
        "FEATURES.md",
        "PRD.md",
        "PROJECT_OVERVIEW.md",
        "SYSTEM_ARCHITECTURE.md",
        "TECHNOLOGY_STACK.md",
        "TESTING_STRATEGY.md",
    ]
    for doc in expected_docs:
        doc_path = docs_dir / doc
        assert doc_path.exists(), f"Missing required document: {doc}"


def test_starter_zip_directories_present():
    """Verifies that all core architectural directories from the starter zip exist."""
    root = Path(__file__).parent.parent
    expected_dirs = [
        "app/components",
        "app/pages",
        "app/services",
        "ai/models",
        "ai/detection",
        "ai/preprocessing",
        "database",
        "data/uploads",
        "data/processed",
        "data/datasets",
        "reports",
        "assets",
        "docs",
        "tests",
    ]
    for d in expected_dirs:
        dir_path = root / d
        assert dir_path.is_dir(), f"Missing required directory: {d}"


def test_imports():
    """Verifies that all primary project modules import cleanly from the new architecture."""
    import app
    import app.main
    from app.components import landing, upload
    from app.services import inspection_service
    from ai.preprocessing import image_ops
    from ai.detection import detector
    from database import db

    assert hasattr(landing, "render_landing_page")
    assert hasattr(upload, "render_upload_section")
    assert hasattr(image_ops, "validate_image_stream")
    assert hasattr(detector, "DefectDetectionService")
    assert hasattr(db, "init_db")
    assert hasattr(app.main, "main")
    assert hasattr(inspection_service, "InspectionService")
