"""
VisionGuard AI — Production WSGI Entry Point.

This module provides the WSGI application object for production deployment servers:
- Windows (Recommended): Waitress
    python -m waitress --listen=127.0.0.1:5000 --threads=4 wsgi:app
  Or directly:
    python wsgi.py

- Linux / Container (Recommended): Gunicorn
    gunicorn --workers=4 --bind=127.0.0.1:5000 --access-logfile - wsgi:app
"""

import os
import sys
from pathlib import Path

# Ensure project root is present in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.server import app

# Expose 'application' as alias for WSGI servers that expect that name
application = app

if __name__ == "__main__":
    try:
        from waitress import serve
        host = os.environ.get("VISIONGUARD_HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
        port = int(os.environ.get("VISIONGUARD_PORT", os.environ.get("PORT", "5000")))
        threads = int(os.environ.get("VISIONGUARD_THREADS", "4"))
        
        print(f"[*] Starting VisionGuard AI production server (Waitress) on http://{host}:{port} ({threads} worker threads)")
        serve(app, host=host, port=port, threads=threads)
    except ImportError:
        print("[!] Waitress is not installed. Falling back to development server.")
        print("[!] Install waitress with: pip install waitress")
        app.run(host="127.0.0.1", port=5000, debug=False)
