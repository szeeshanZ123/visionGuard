"""Unit tests for image verification and processing utilities."""

import io
import pytest
import numpy as np
from PIL import Image

from src.utils.image_ops import (
    validate_image_stream,
    load_image_as_opencv,
    opencv_to_rgb,
    SUPPORTED_EXTENSIONS,
)


def create_in_memory_image(width: int = 100, height: int = 80, fmt: str = "PNG") -> io.BytesIO:
    """Helper to create a valid synthetic image stream for testing."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf


def test_valid_png_stream():
    """Verifies that a valid PNG image passes checks and returns accurate metadata."""
    stream = create_in_memory_image(120, 90, "PNG")
    is_valid, err, meta = validate_image_stream(stream, "road_sample.png")

    assert is_valid is True
    assert err is None
    assert meta is not None
    assert meta["width"] == 120
    assert meta["height"] == 90
    assert meta["format"] == "PNG"
    assert meta["channels"] == 3


def test_valid_jpeg_stream():
    """Verifies that a valid JPEG image passes validation."""
    stream = create_in_memory_image(200, 150, "JPEG")
    is_valid, err, meta = validate_image_stream(stream, "pothole_test.jpg")

    assert is_valid is True
    assert err is None
    assert meta is not None
    assert meta["width"] == 200
    assert meta["height"] == 150
    assert meta["format"] == "JPEG"


def test_unsupported_extension():
    """Verifies that unsupported file extensions are rejected."""
    stream = create_in_memory_image(50, 50, "PNG")
    is_valid, err, meta = validate_image_stream(stream, "document.pdf")

    assert is_valid is False
    assert "Unsupported file extension" in err
    assert meta is None


def test_empty_stream():
    """Verifies that zero-byte streams are rejected gracefully."""
    empty_stream = io.BytesIO(b"")
    is_valid, err, meta = validate_image_stream(empty_stream, "empty.png")

    assert is_valid is False
    assert "empty" in err.lower()
    assert meta is None


def test_corrupted_stream():
    """Verifies that corrupted bytes masquerading as an image are caught."""
    corrupted_stream = io.BytesIO(b"this_is_not_an_image_header_bytes")
    is_valid, err, meta = validate_image_stream(corrupted_stream, "fake.jpg")

    assert is_valid is False
    assert "corrupted" in err.lower() or "invalid" in err.lower()
    assert meta is None


def test_load_image_as_opencv():
    """Verifies that OpenCV decodes image stream into expected numpy array."""
    stream = create_in_memory_image(64, 48, "PNG")
    cv_img = load_image_as_opencv(stream)

    assert cv_img is not None
    assert isinstance(cv_img, np.ndarray)
    assert cv_img.shape == (48, 64, 3)

    # Test RGB conversion
    rgb_img = opencv_to_rgb(cv_img)
    assert rgb_img.shape == (48, 64, 3)
