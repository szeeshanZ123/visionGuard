"""Integration tests for Streamlit interface using AppTest."""

from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def test_streamlit_landing_page_renders():
    """Verifies that the Streamlit application starts and renders the landing page."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    # Verify no unhandled exceptions occurred
    assert not at.exception

    # Verify title / header elements are present
    assert any("VisionGuard AI" in str(markdown.value) for markdown in at.markdown)


def test_streamlit_navigation_to_upload():
    """Verifies navigating to the upload section renders upload widgets and AI placeholders."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    # Switch radio to upload view
    assert len(at.sidebar.radio) > 0
    at.sidebar.radio[0].set_value("📷 Defect Inspection (Upload)").run()

    assert not at.exception
    # Check that file uploader is rendered
    assert len(at.file_uploader) > 0
    # Check that info prompt is rendered
    assert any("upload an image" in str(info.value).lower() for info in at.info)


def test_streamlit_upload_image_processing():
    """Verifies that uploading an image displays the image, metadata table, and Phase 2 placeholders."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    # Switch to upload view
    at.sidebar.radio[0].set_value("📷 Defect Inspection (Upload)").run()

    sample_road_path = Path(__file__).parent.parent / "data" / "sample_road.jpg"
    with open(sample_road_path, "rb") as f:
        img_bytes = f.read()

    # Upload image into the file uploader widget
    at.file_uploader[0].upload("sample_road.jpg", img_bytes, "image/jpeg").run()

    assert not at.exception
    # Image must be displayed
    assert len(at.image) > 0
    # Metadata dataframe must be present
    assert len(at.dataframe) > 0
    # Success alert must be present
    assert any("Image Verified" in str(s.value) for s in at.success)
    # Placeholder warning alert must be present
    assert any("AI Model Inference Pending" in str(w.value) for w in at.warning)
    # Check placeholder metrics
    metric_labels = [m.label for m in at.metric]
    assert "Model Status" in metric_labels
    assert "Defect Classification" in metric_labels
    assert "Confidence Score" in metric_labels

    # Check metric values (ensuring no fake detection values)
    metrics_by_label = {m.label: m.value for m in at.metric}
    assert metrics_by_label["Model Status"] == "Staged for Phase 2"
    assert metrics_by_label["Defect Classification"] == "[Not Evaluated]"
    assert metrics_by_label["Confidence Score"] == "N/A"


