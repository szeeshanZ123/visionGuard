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
from flask import Flask, request, jsonify, render_template, send_file

from database.db import (
    init_db,
    check_db_health,
    get_db_connection,
    row_to_dict,
    save_inspection,
    get_inspections,
    get_dashboard_analytics,
    get_inspection_by_id,
    update_inspection_status,
    update_inspection,
    delete_inspection,
    ALLOWED_STATUSES,
    DEFAULT_DB_PATH,
)
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

    # Initialize persistence with configured database path
    db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
    init_db(db_path)

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
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        db_health = check_db_health(db_path)
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

        # Persist original uploaded image to data/uploads
        uploads_dir = os.path.join("data", "uploads")
        orig_filename = f"orig_{uuid.uuid4().hex[:8]}_{filename}"
        orig_path = os.path.join(uploads_dir, orig_filename)
        try:
            os.makedirs(uploads_dir, exist_ok=True)
            with open(orig_path, "wb") as f_orig:
                f_orig.write(raw_bytes)
        except Exception as e:
            logger.warning(f"Failed to persist original image: {e}")
            orig_path = None

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
            "original_file_path": orig_path,
            "processed_file_path": saved_path,
            "disclaimer": (
                "Notice: Detection confidence measures model statistical likelihood, "
                "not physical crack severity, cavity depth, or roadway structural safety."
            ),
        }), 200

    # -------------------------------------------------------------------------
    # Inspection Records API Routes
    # -------------------------------------------------------------------------
    @app.route("/api/dashboard/stats", methods=["GET"])
    def api_get_dashboard_stats():
        """
        Returns aggregate defect metrics, category distribution, and recent records
        calculated dynamically from actual SQLite database rows.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        stats = get_dashboard_analytics(db_path=db_path)
        return jsonify({
            "status": "success",
            "stats": stats,
            "disclaimer": (
                "Notice: Dashboard statistics and resolution states are compiled from "
                "administrative workflow records and do not certify that physical pavement repairs "
                "have occurred or engineering structural integrity has been verified."
            )
        }), 200

    @app.route("/api/inspections", methods=["GET"])
    def api_get_inspections():
        """
        Lists saved inspection records with optional filtering.
        Query params: status, category, q (search query), limit, offset.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        status_filter = request.args.get("status")
        if (
            status_filter
            and status_filter.strip()
            and status_filter.strip() not in ALLOWED_STATUSES
            and status_filter.strip().lower() not in ["all", "in progress group", "in-progress", "active"]
        ):
            return jsonify({
                "status": "error",
                "error_code": "INVALID_STATUS_FILTER",
                "message": f"Status '{status_filter}' is invalid. Allowed: {ALLOWED_STATUSES}",
            }), 400

        category_filter = request.args.get("category")
        search_query = request.args.get("q") or request.args.get("search")
        has_coords_raw = request.args.get("has_coords")
        has_coords = None
        if has_coords_raw is not None:
            has_coords = has_coords_raw.strip().lower() in ["true", "1", "yes"]

        try:
            limit = min(500, max(1, int(request.args.get("limit", 100))))
            offset = max(0, int(request.args.get("offset", 0)))
        except (TypeError, ValueError):
            limit = 100
            offset = 0

        inspections = get_inspections(
            status=status_filter if status_filter and status_filter.lower() != "all" else None,
            limit=limit,
            offset=offset,
            category=category_filter if category_filter and category_filter.lower() != "all" else None,
            search_query=search_query,
            has_coords=has_coords,
            db_path=db_path
        )
        return jsonify({
            "status": "success",
            "count": len(inspections),
            "inspections": inspections,
        }), 200

    def validate_coordinates(latitude, longitude):
        """
        Validates optional geographic coordinates.
        Returns (is_valid, parsed_lat, parsed_lon, error_msg).
        Coordinates can be None or empty string when unknown.
        Latitude must be between -90.0 and 90.0.
        Longitude must be between -180.0 and 180.0.
        """
        parsed_lat = None
        parsed_lon = None

        if latitude is not None and str(latitude).strip() != "":
            try:
                parsed_lat = float(latitude)
            except (ValueError, TypeError):
                return False, None, None, f"Latitude '{latitude}' is not a valid numeric coordinate."
            if not (-90.0 <= parsed_lat <= 90.0):
                return False, None, None, f"Latitude {parsed_lat} is out of bounds. Must be between -90.0 and 90.0 degrees."

        if longitude is not None and str(longitude).strip() != "":
            try:
                parsed_lon = float(longitude)
            except (ValueError, TypeError):
                return False, None, None, f"Longitude '{longitude}' is not a valid numeric coordinate."
            if not (-180.0 <= parsed_lon <= 180.0):
                return False, None, None, f"Longitude {parsed_lon} is out of bounds. Must be between -180.0 and 180.0 degrees."

        return True, parsed_lat, parsed_lon, None

    @app.route("/api/inspections", methods=["POST"])
    def api_save_inspection():
        """
        Saves a completed road inspection into the database.
        Stores authentic detection coordinates, confidence, metadata, location, and status.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}

        image_name = payload.get("image_name") or payload.get("filename")
        if not image_name or not str(image_name).strip():
            return jsonify({
                "status": "error",
                "error_code": "MISSING_IMAGE_NAME",
                "message": "Field 'image_name' is required to save an inspection record.",
            }), 400

        status = payload.get("status", "Open")
        if status not in ALLOWED_STATUSES:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_STATUS",
                "message": f"Status '{status}' is invalid. Allowed: {ALLOWED_STATUSES}",
            }), 400

        # Location metadata validation
        road_name = payload.get("road_name", "")
        if road_name and len(str(road_name)) > 150:
            return jsonify({
                "status": "error",
                "error_code": "ROAD_NAME_TOO_LONG",
                "message": "Road/location name cannot exceed 150 characters.",
            }), 400

        area = payload.get("area", "")
        if area and len(str(area)) > 100:
            return jsonify({
                "status": "error",
                "error_code": "AREA_TOO_LONG",
                "message": "Area/neighborhood name cannot exceed 100 characters.",
            }), 400

        city = payload.get("city", "")
        if city and len(str(city)) > 100:
            return jsonify({
                "status": "error",
                "error_code": "CITY_TOO_LONG",
                "message": "City name cannot exceed 100 characters.",
            }), 400

        # Validate GPS Coordinates
        lat_input = payload.get("latitude")
        lon_input = payload.get("longitude")
        is_valid_coords, parsed_lat, parsed_lon, coord_err = validate_coordinates(lat_input, lon_input)
        if not is_valid_coords:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_COORDINATES",
                "message": coord_err,
            }), 400

        payload["latitude"] = parsed_lat
        payload["longitude"] = parsed_lon

        original_image_path = payload.get("original_image_path", "").strip()
        if original_image_path:
            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM defect_inspections WHERE original_image_path = ? AND original_image_path != '' LIMIT 1;",
                (original_image_path,)
            )
            existing = cursor.fetchone()
            conn.close()
            if existing:
                existing_dict = row_to_dict(existing)
                return jsonify({
                    "status": "error",
                    "error_code": "DUPLICATE_INSPECTION",
                    "message": f"This inspection has already been saved as Record #{existing_dict['id']}.",
                    "inspection": existing_dict,
                }), 409

        try:
            record = save_inspection(payload, db_path=db_path)
            return jsonify({
                "status": "success",
                "message": "Inspection record saved successfully.",
                "inspection": record,
            }), 201
        except Exception as e:
            logger.exception(f"Failed to persist inspection record: {e}")
            return jsonify({
                "status": "error",
                "error_code": "PERSISTENCE_FAILED",
                "message": f"Database save error: {str(e)}",
            }), 500

    @app.route("/api/inspections/<int:inspection_id>", methods=["GET"])
    def api_get_inspection_detail(inspection_id: int):
        """
        Retrieves full details of a specific inspection by ID.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        record = get_inspection_by_id(inspection_id, db_path=db_path)
        if not record:
            return jsonify({
                "status": "error",
                "error_code": "INSPECTION_NOT_FOUND",
                "message": f"Inspection record #{inspection_id} not found.",
            }), 404

        disclaimer_text = (
            "VisionGuard AI defect detections represent 2D camera bounding boxes only. "
            "Confidence scores indicate visual recognition likelihood, not defect severity or structural safety. "
            "Pixel bounding boxes do not provide real-world crack dimensions or structural load capacity. "
            "Status classifications are administrative workflow tracking and do not prove physical road repair."
        )
        record["disclaimer"] = disclaimer_text

        return jsonify({
            "status": "success",
            "inspection": record,
            "disclaimer": disclaimer_text,
        }), 200

    @app.route("/api/inspections/<int:inspection_id>/status", methods=["PATCH"])
    def api_update_inspection_status(inspection_id: int):
        """
        Updates the status of an inspection record.
        Allowed initial states: Open, Under Review, Repair in Progress, Resolved.
        Also accepts optional location metadata updates.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}
        new_status = payload.get("status")

        if not new_status:
            return jsonify({
                "status": "error",
                "error_code": "MISSING_STATUS",
                "message": "Field 'status' is required.",
            }), 400

        if new_status not in ALLOWED_STATUSES:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_STATUS",
                "message": f"Status '{new_status}' is invalid. Allowed: {ALLOWED_STATUSES}",
            }), 400

        # Validate coordinates if provided
        if "latitude" in payload or "longitude" in payload:
            is_valid_coords, parsed_lat, parsed_lon, coord_err = validate_coordinates(
                payload.get("latitude"), payload.get("longitude")
            )
            if not is_valid_coords:
                return jsonify({
                    "status": "error",
                    "error_code": "INVALID_COORDINATES",
                    "message": coord_err,
                }), 400
            payload["latitude"] = parsed_lat
            payload["longitude"] = parsed_lon

        if "road_name" in payload and payload["road_name"] and len(str(payload["road_name"])) > 150:
            return jsonify({
                "status": "error",
                "error_code": "ROAD_NAME_TOO_LONG",
                "message": "Road/location name cannot exceed 150 characters.",
            }), 400

        if "area" in payload and payload["area"] and len(str(payload["area"])) > 100:
            return jsonify({
                "status": "error",
                "error_code": "AREA_TOO_LONG",
                "message": "Area/neighborhood name cannot exceed 100 characters.",
            }), 400

        if "city" in payload and payload["city"] and len(str(payload["city"])) > 100:
            return jsonify({
                "status": "error",
                "error_code": "CITY_TOO_LONG",
                "message": "City name cannot exceed 100 characters.",
            }), 400

        try:
            updated = update_inspection(inspection_id, payload, db_path=db_path)
            if not updated:
                return jsonify({
                    "status": "error",
                    "error_code": "INSPECTION_NOT_FOUND",
                    "message": f"Inspection record #{inspection_id} not found.",
                }), 404

            disclaimer_text = (
                "Notice: Status changes represent administrative workflow tracking. "
                "A 'Resolved' or 'Repair in Progress' status does not prove physical road repair "
                "and does not verify or certify that physical roadway engineering repairs have taken place."
            )
            updated["disclaimer"] = disclaimer_text

            return jsonify({
                "status": "success",
                "message": f"Inspection #{inspection_id} status updated to '{new_status}'.",
                "disclaimer": disclaimer_text,
                "status_disclaimer": disclaimer_text,
                "inspection": updated,
            }), 200
        except Exception as e:
            logger.exception(f"Failed to update inspection #{inspection_id} status: {e}")
            return jsonify({
                "status": "error",
                "error_code": "UPDATE_FAILED",
                "message": f"Status update failed: {str(e)}",
            }), 500

    @app.route("/api/inspections/<int:inspection_id>", methods=["PATCH", "PUT"])
    def api_update_inspection(inspection_id: int):
        """
        Updates location metadata, notes, and/or status for an existing inspection.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}

        if "status" in payload and payload["status"] not in ALLOWED_STATUSES:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_STATUS",
                "message": f"Status '{payload['status']}' is invalid. Allowed: {ALLOWED_STATUSES}",
            }), 400

        if "latitude" in payload or "longitude" in payload:
            is_valid_coords, parsed_lat, parsed_lon, coord_err = validate_coordinates(
                payload.get("latitude"), payload.get("longitude")
            )
            if not is_valid_coords:
                return jsonify({
                    "status": "error",
                    "error_code": "INVALID_COORDINATES",
                    "message": coord_err,
                }), 400
            payload["latitude"] = parsed_lat
            payload["longitude"] = parsed_lon

        if "road_name" in payload and payload["road_name"] and len(str(payload["road_name"])) > 150:
            return jsonify({
                "status": "error",
                "error_code": "ROAD_NAME_TOO_LONG",
                "message": "Road/location name cannot exceed 150 characters.",
            }), 400

        if "area" in payload and payload["area"] and len(str(payload["area"])) > 100:
            return jsonify({
                "status": "error",
                "error_code": "AREA_TOO_LONG",
                "message": "Area/neighborhood name cannot exceed 100 characters.",
            }), 400

        if "city" in payload and payload["city"] and len(str(payload["city"])) > 100:
            return jsonify({
                "status": "error",
                "error_code": "CITY_TOO_LONG",
                "message": "City name cannot exceed 100 characters.",
            }), 400

        try:
            updated = update_inspection(inspection_id, payload, db_path=db_path)
            if not updated:
                return jsonify({
                    "status": "error",
                    "error_code": "INSPECTION_NOT_FOUND",
                    "message": f"Inspection record #{inspection_id} not found.",
                }), 404

            return jsonify({
                "status": "success",
                "message": f"Inspection #{inspection_id} updated successfully.",
                "inspection": updated,
            }), 200
        except Exception as e:
            logger.exception(f"Failed to update inspection #{inspection_id}: {e}")
            return jsonify({
                "status": "error",
                "error_code": "UPDATE_FAILED",
                "message": f"Inspection update failed: {str(e)}",
            }), 500

    @app.route("/api/inspections/<int:inspection_id>/image/<img_type>", methods=["GET"])
    def api_get_inspection_image(inspection_id: int, img_type: str):
        """
        Serves the original or annotated image file for a saved inspection.
        img_type: 'original' or 'annotated'.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        record = get_inspection_by_id(inspection_id, db_path=db_path)
        if not record:
            return jsonify({"status": "error", "message": f"Inspection #{inspection_id} not found."}), 404

        if img_type == "original":
            target_path = record.get("original_image_path") or record.get("file_path")
        elif img_type == "annotated":
            target_path = record.get("annotated_image_path")
        else:
            return jsonify({"status": "error", "message": "Invalid image type. Use 'original' or 'annotated'."}), 400

        if not target_path or not os.path.exists(target_path):
            return jsonify({
                "status": "error",
                "error_code": "IMAGE_FILE_NOT_FOUND",
                "message": f"Image file '{target_path or ''}' does not exist on disk.",
            }), 404

        abs_target = os.path.abspath(target_path)
        return send_file(abs_target)

    return app


# Module-level application instance for WSGI servers / flask run
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

