"""
Image processing and validation utilities for VisionGuard AI.

Implements input validation and preprocessing requirements from docs/PRD.md & docs/SYSTEM_ARCHITECTURE.md:
- Format, size, and integrity checks.
- Dimensionality, color space, and channel extraction.
- Decoding to OpenCV BGR arrays and conversion to RGB.
"""

from typing import Dict, Any, Tuple, Optional
import io
import cv2
import numpy as np
from PIL import Image

SUPPORTED_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "webp"}
MAX_RECOMMENDED_SIZE_MB = 15.0


def validate_image_stream(
    file_stream: io.BytesIO, filename: str = "upload.jpg"
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validates uploaded image byte stream, verifying image integrity and metadata.

    Args:
        file_stream: In-memory byte stream of the image file.
        filename: Name of the uploaded file for extension verification.

    Returns:
        Tuple: (is_valid: bool, error_message: Optional[str], metadata: Optional[Dict])
    """
    try:
        # Check extension
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext not in SUPPORTED_EXTENSIONS:
            return (
                False,
                f"Unsupported file extension '.{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
                None,
            )

        # Check byte size
        file_stream.seek(0, io.SEEK_END)
        file_size_bytes = file_stream.tell()
        file_stream.seek(0)

        if file_size_bytes == 0:
            return False, "Uploaded file is empty (0 bytes).", None

        size_mb = file_size_bytes / (1024 * 1024)
        if size_mb > MAX_RECOMMENDED_SIZE_MB:
            return (
                False,
                f"File size ({size_mb:.2f} MB) exceeds maximum allowed {MAX_RECOMMENDED_SIZE_MB} MB limit.",
                None,
            )

        # Verify decoding with PIL
        try:
            image = Image.open(file_stream)
            image.verify()  # Verifies file integrity
            file_stream.seek(0)
            # Reopen after verify() as recommended by PIL docs
            image = Image.open(file_stream)
        except Exception as e:
            return False, f"Corrupted or invalid image stream: {str(e)}", None

        width, height = image.size
        channels = len(image.getbands()) if hasattr(image, "getbands") else 3

        metadata = {
            "filename": filename,
            "format": image.format or ext.upper(),
            "width": width,
            "height": height,
            "aspect_ratio": f"{width}:{height} ({width/height:.2f}:1)" if height > 0 else "N/A",
            "channels": channels,
            "mode": image.mode,
            "file_size_bytes": file_size_bytes,
            "file_size_formatted": f"{size_mb * 1024:.1f} KB" if size_mb < 1 else f"{size_mb:.2f} MB",
        }

        return True, None, metadata

    except Exception as exc:
        return False, f"Unexpected error while validating image: {str(exc)}", None


def load_image_as_opencv(file_stream: io.BytesIO) -> Optional[np.ndarray]:
    """
    Loads an image stream into an OpenCV BGR numpy array.

    Args:
        file_stream: In-memory byte stream.

    Returns:
        numpy ndarray in BGR format, or None if reading failed.
    """
    try:
        file_stream.seek(0)
        file_bytes = np.asarray(bytearray(file_stream.read()), dtype=np.uint8)
        img_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        file_stream.seek(0)
        return img_bgr
    except Exception:
        return None


def opencv_to_rgb(img_bgr: np.ndarray) -> np.ndarray:
    """Converts OpenCV BGR image array to RGB for Streamlit/PIL rendering."""
    if img_bgr is None:
        raise ValueError("Cannot convert None BGR image to RGB")
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
