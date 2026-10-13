"""Smoke tests verifying overall application module integrity and imports."""

def test_imports():
    """Verifies that all primary project modules import without error."""
    import src
    from src.utils import image_ops
    from src.database import db
    from src.components import landing, upload
    import app

    assert src.__version__ == "0.1.0"
    assert hasattr(landing, "render_landing_page")
    assert hasattr(upload, "render_upload_section")
    assert hasattr(image_ops, "validate_image_stream")
    assert hasattr(db, "init_db")
    assert hasattr(app, "main")
