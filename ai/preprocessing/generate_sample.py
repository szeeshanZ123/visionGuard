"""
Generates a synthetic sample road image with texture for testing and verification.
"""

import os
import cv2
import numpy as np


def generate_sample_image(output_path: str = os.path.join("data", "sample_road.jpg")):
    """Generates a textured synthetic road asphalt image."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    height, width = 720, 1280
    # Base dark asphalt gray
    img = np.full((height, width, 3), 75, dtype=np.uint8)

    # Add realistic texture noise
    noise = np.random.normal(0, 15, (height, width, 3)).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Road lane markings
    cv2.line(img, (width // 2, 0), (width // 2, height), (240, 240, 240), thickness=6)
    cv2.line(img, (80, 0), (80, height), (220, 220, 50), thickness=8)
    cv2.line(img, (width - 80, 0), (width - 80, height), (220, 220, 50), thickness=8)

    cv2.imwrite(output_path, img)
    return output_path


if __name__ == "__main__":
    path = generate_sample_image()
    print(f"Generated sample road image at: {path}")
