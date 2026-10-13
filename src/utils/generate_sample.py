"""Utility script to generate sample test images for manual and integration inspection."""

import os
import numpy as np
import cv2

def generate_sample_road_image(output_path: str = "data/sample_road.jpg"):
    """Generates a realistic asphalt-style test texture with lane marking."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    height, width = 600, 800
    # Base dark asphalt texture with subtle noise
    asphalt = np.random.normal(loc=70, scale=12, size=(height, width)).clip(0, 255).astype(np.uint8)
    asphalt_bgr = cv2.cvtColor(asphalt, cv2.COLOR_GRAY2BGR)

    # Add yellow road center marking line
    cv2.line(asphalt_bgr, (width // 2, 0), (width // 2, height), (30, 200, 240), thickness=16)

    # Add white shoulder stripe
    cv2.line(asphalt_bgr, (100, 0), (100, height), (220, 220, 220), thickness=12)

    cv2.imwrite(output_path, asphalt_bgr)
    print(f"Generated sample road image at: {output_path}")

if __name__ == "__main__":
    generate_sample_road_image()
