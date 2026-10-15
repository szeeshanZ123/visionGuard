"""
VisionGuard AI Application Package.

Contains both the Flask REST API backend (`app.server`) and
the existing Streamlit application interface (`app.main`).
"""

from app.server import create_app, app

__all__ = ["create_app", "app"]
