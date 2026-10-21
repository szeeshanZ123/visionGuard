"""
Flask Backend Application for VisionGuard AI.

Provides REST API endpoints and web client serving for infrastructure inspection:
- POST /api/inspect: Validates road imagery and runs genuine YOLOv8 defect detection.
- GET  /api/health: Returns system status, DB connection, and model readiness.
- GET  /api/classes: Returns supported distress classes and metadata.
- GET  /: Serves the inspection web interface.
"""

import io
import os
import sys
import uuid
import logging
from pathlib import Path
from typing import Optional

# Configure application logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("visionguard")

# Ensure project root is present in sys.path when running app/server.py directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
from flask import Flask, request, jsonify, render_template

from database.db import init_db, check_db_health
from ai.preprocessing.image_ops import (
    validate_image_stream,
    load_image_as_opencv,
    SUPPORTED_EXTENSIONS,
    MAX_RECOMMENDED_SIZE_MB,
)
from ai.detection.detector import (
    DefectDetectionService,
    CLASS_NAMES,
    CLASS_DISPLAY_NAMES,
    DEFAULT_MODEL_PATH,
)


def create_app(detector: Optional[DefectDetectionService] = None, test_config: Optional[dict] = None) -> Flask:
    """
    Application factory for the VisionGuard AI Flask backend.
    """
    app_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(app_dir, "templates")
    static_dir = os.path.join(app_dir, "static")

    app = Flask(
        __name__,
        template_folder=templates_dir,
        static_folder=static_dir,
        static_url_path="/static",
    )

    # Enforce maximum upload size (15 MB)
    max_mb = test_config.get("MAX_CONTENT_LENGTH_MB", MAX_RECOMMENDED_SIZE_MB) if test_config else MAX_RECOMMENDED_SIZE_MB
    app.config["MAX_CONTENT_LENGTH"] = int(max_mb * 1024 * 1024)

    if test_config:
        app.config.update(test_config)

    # Initialize persistence
    init_db()

    # Initialize DefectDetectionService
    app.detector = detector or DefectDetectionService()

    # -------------------------------------------------------------------------
    # Error Handlers
    # -------------------------------------------------------------------------
    @app.errorhandler(413)
    def file_too_large(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "FILE_TOO_LARGE",
                "message": f"File size exceeds the maximum allowed limit of {max_mb:.1f} MB.",
            }),
            413,
        )

    @app.errorhandler(400)
    def bad_request(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "BAD_REQUEST",
                "message": getattr(error, "description", "Bad Request"),
            }),
            400,
        )

    @app.errorhandler(404)
    def not_found(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "NOT_FOUND",
                "message": "The requested endpoint was not found.",
            }),
            404,
        )

    @app.errorhandler(500)
    def internal_error(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred during processing.",
            }),
            500,
        )

    # -------------------------------------------------------------------------
    # API Routes
    # -------------------------------------------------------------------------
    @app.route("/", methods=["GET"])
    def index():
        """Serves the main inspection dashboard and upload interface."""
        return render_template("index.html")

    @app.route("/api/health", methods=["GET"])
    def api_health():
        """
        Telemetry and health check reporting database and AI model status.
        """
        db_health = check_db_health()
        return jsonify({
            "status": "healthy",
            "database": db_health,
            "model": {
                "loaded": app.detector.is_loaded,
                "status_message": app.detector.status_message,
                "checkpoint_path": app.detector.model_path,
                "supported_classes": [CLASS_NAMES[i] for i in sorted(CLASS_NAMES.keys())],
            },
            "limits": {
                "max_file_size_mb": max_mb,
                "supported_extensions": sorted(list(SUPPORTED_EXTENSIONS)),
            },
        }), 200

    @app.route("/api/classes", methods=["GET"])
    def api_classes():
        """
        Returns supported defect classes and their descriptions.
        """
        classes_data = []
        for cid, cname in sorted(CLASS_NAMES.items()):
            display_name = CLASS_DISPLAY_NAMES.get(cname, cname)
            classes_data.append({
                "class_id": cid,
                "class_name": cname,
                "display_name": display_name,
                "category": "crack" if "crack" in cname else "pothole",
            })
        return jsonify({
            "status": "success",
            "classes": classes_data,
        }), 200

    @app.route("/api/reload-model", methods=["POST"])
    def api_reload_model():
        """
        Re-attempts loading the model checkpoint from disk.
        """
        success = app.detector.load_model()
        status_code = 200 if success else 503
        return jsonify({
            "status": "success" if success else "error",
            "loaded": success,
            "message": app.detector.status_message,
            "checkpoint_path": app.detector.model_path,
        }), status_code

    @app.route("/api/inspect", methods=["POST"])
    def api_inspect():
        """
        Primary defect inspection endpoint.
        Accepts multipart/form-data image stream, validates format,
        runs genuine YOLOv8 defect detection, and renders visual overlay.
        """
        # 1. Check for file part
        file = None
        if "image" in request.files:
            file = request.files["image"]
        elif "file" in request.files:
            file = request.files["file"]

        if file is None or file.filename == "":
            return (
                jsonify({
                    "status": "error",
                    "error_code": "NO_FILE_UPLOADED",
                    "message": "No image file provided in request. Use 'image' or 'file' form-data field.",
                }),
                400,
            )

        filename = file.filename
        raw_bytes = file.read()
        file_stream = io.BytesIO(raw_bytes)

        # 2. Validate image stream (format, size, integrity)
        is_valid, err_msg, metadata = validate_image_stream(file_stream, filename)
        if not is_valid:
            return (
                jsonify({
                    "status": "error",
                    "error_code": "INVALID_IMAGE",
                    "message": err_msg or "Image validation failed.",
                }),
                400,
            )

        # 3. Verify model checkpoint readiness
        if not app.detector.is_loaded:
            return (
                jsonify({
                    "status": "error",
                    "error_code": "MODEL_WEIGHTS_MISSING",
                    "message": (
                        f"Model weights checkpoint '{app.detector.model_path}' is not present on the server. "
                        "VisionGuard AI requires authentic model weights and does not fabricate detections."
                    ),
                    "setup_instructions": (
                        "1. Download 'best.pt' from your Google Drive ('VisionGuard_Artifacts/best.pt') "
                        "or Google Colab export.\n"
                        f"2. Copy 'best.pt' to '{app.detector.model_path}'.\n"
                        "3. Call 'POST /api/reload-model' or restart the server."
                    ),
                    "metadata": metadata,
                }),
                503,
            )

        # 4. Decode with OpenCV
        file_stream.seek(0)
        cv_img = load_image_as_opencv(file_stream)
        if cv_img is None:
            return (
                jsonify({
                    "status": "error",
                    "error_code": "IMAGE_DECODE_FAILED",
                    "message": "OpenCV failed to decode image into an array. File may be corrupted.",
                }),
                400,
            )

        # 5. Execute genuine detection
        conf_param = request.form.get("confidence_threshold", "0.25")
        try:
            conf_thresh = float(conf_param)
            conf_thresh = max(0.05, min(0.95, conf_thresh))
        except ValueError:
            conf_thresh = 0.25

        inspection_mode = request.form.get("inspection_mode", "standard").lower().strip()
        if inspection_mode not in ["standard", "tiled", "sliced"]:
            inspection_mode = "standard"

        try:
            if inspection_mode in ["tiled", "sliced"] and hasattr(app.detector, "detect_sliced"):
                detections = app.detector.detect_sliced(
                    cv_img,
                    conf_threshold=conf_thresh,
                    raise_if_unloaded=True,
                )
            else:
                detections = app.detector.detect(
                    cv_img,
                    conf_threshold=conf_thresh,
                    raise_if_unloaded=True,
                )
            # 6. Generate genuine visual overlay
            annotated_bgr = app.detector.draw_annotations(cv_img, detections)
            annotated_b64 = app.detector.encode_image_to_base64(annotated_bgr)
        except Exception as exc:
            logger.exception(f"Inference error processing '{filename}': {str(exc)}")
            return (
                jsonify({
                    "status": "error",
                    "error_code": "INFERENCE_FAILED",
                    "message": f"Inference execution failed: {str(exc)}",
                }),
                500,
            )

        # Optionally persist annotated image to data/processed
        processed_dir = os.path.join("data", "processed")
        saved_filename = f"annotated_{uuid.uuid4().hex[:8]}_{filename}"
        saved_path = os.path.join(processed_dir, saved_filename)
        try:
            os.makedirs(processed_dir, exist_ok=True)
            cv2.imwrite(saved_path, annotated_bgr)
        except Exception:
            saved_path = None

        return jsonify({
            "status": "success",
            "filename": filename,
            "metadata": metadata,
            "model_info": app.detector.model_info,
            "inspection_mode": inspection_mode,
            "confidence_threshold": conf_thresh,
            "candidate_summary": getattr(app.detector, "last_inference_stats", {}),
            "detections": detections,
            "defect_count": len(detections),
            "annotated_image": annotated_b64,
            "processed_file_path": saved_path,
            "disclaimer": (
                "Notice: Detection confidence measures model statistical likelihood, "
                "not physical crack severity, cavity depth, or roadway structural safety."
            ),
        }), 200

    return app


# Module-level application instance for WSGI servers / flask run
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

