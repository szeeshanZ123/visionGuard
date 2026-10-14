"""
VisionGuard AI - Application Entry Point.

Delegates execution to app.main module, matching the repository layout.
Run via:
    streamlit run app.py
or
    streamlit run app/main.py
"""

from app.main import main

if __name__ == "__main__":
    main()
