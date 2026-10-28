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
import time
import uuid
import logging
import datetime
from pathlib import Path
from typing import Optional

# Configure application logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("visionguard")

# Ensure project root is present in sys.path when running app/server.py directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import secrets
import threading
import gc
from functools import wraps

# Process-level inference lock ensuring single-flight YOLO forward passes on CPU
INFERENCE_LOCK = threading.Lock()
# Process-level concurrency gate ensuring at most 1 heavy inspection is in-flight simultaneously
INSPECTION_SEMAPHORE = threading.Semaphore(1)
try:
    import cv2
    cv2.setNumThreads(1)
except Exception:
    cv2 = None
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template, send_file, session

from database.db import (
    init_db,
    check_db_health,
    get_db_connection,
    row_to_dict,
    save_inspection,
    get_inspections,
    get_dashboard_analytics,
    get_inspection_by_id,
    get_citizen_dashboard_summary,
    update_inspection_status,
    update_inspection,
    delete_inspection,
    validate_target_repair_date,
    get_inspection_activity,
    ALLOWED_STATUSES,
    DEFAULT_DB_PATH,
)
from database.auth import (
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    ROLE_MAINTENANCE,
    ROLE_CITIZEN,
    ALLOWED_ROLES,
    ROLE_DISPLAY_NAMES,
    create_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    count_users,
    count_admin_users,
    update_user,
    authenticate_user,
    init_admin_from_env,
    validate_username,
    validate_password_strength,
    validate_role,
)
from database.reports import (
    validate_report_filters,
    generate_report_data,
    generate_report_csv,
    generate_report_pdf,
)
from database.assignments import (
    assign_inspection_task,
    cancel_inspection_assignment,
    get_maintenance_work_queue,
    get_inspection_assignment_history,
    list_active_maintenance_staff,
    check_user_can_maintain_inspection,
    ASSIGNMENT_STATUS_DISPLAY,
    ALLOWED_ASSIGNMENT_STATUSES,
)
from database.complaints import (
    get_or_create_complaint_draft,
    update_complaint_draft,
    export_complaint_draft_pdf,
    COMPLAINT_DISCLAIMER_TEXT,
)
from ai.preprocessing.image_ops import (
    validate_image_stream,
    load_image_as_opencv,
    SUPPORTED_EXTENSIONS,
    MAX_RECOMMENDED_SIZE_MB,
)
from ai.detection.detector import (
    DefectDetectionService,
    HomeDefectDetectionService,
    RoadDefectDetectionService,
    CLASS_NAMES,
    CLASS_DISPLAY_NAMES,
    DEFAULT_MODEL_PATH,
    ROAD_CLASS_NAMES,
    ROAD_CLASS_DISPLAY_NAMES,
    DEFAULT_ROAD_MODEL_PATH,
    HOME_CLASS_NAMES,
    HOME_CLASS_DISPLAY_NAMES,
    DEFAULT_HOME_MODEL_PATH,
)
from storage import (
    get_storage_backend,
    StorageBackend,
    LocalStorageBackend,
    CloudflareR2StorageBackend,
)


def create_app(
    detector: Optional[DefectDetectionService] = None,
    home_detector: Optional[DefectDetectionService] = None,
    test_config: Optional[dict] = None
) -> Flask:
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

    # Environment identification (Phase 7: Production Hardening)
    vg_env = (
        (test_config.get("ENV") if test_config else None)
        or os.environ.get("VISIONGUARD_ENV")
        or os.environ.get("FLASK_ENV")
        or "development"
    ).lower().strip()
    is_production = vg_env == "production"
    app.config["ENV"] = vg_env
    app.config["PRODUCTION"] = is_production

    # In production, debug mode must strictly be disabled
    if is_production:
        app.config["DEBUG"] = False
        app.debug = False

    # Secret key configuration for cryptographic session signing
    explicit_secret = (
        (test_config.get("SECRET_KEY") if test_config else None)
        or os.environ.get("VISIONGUARD_SECRET_KEY")
    )

    if is_production:
        insecure_keys = {"secret", "changeme", "default", "admin", "12345678", "password", "visionguard", "test"}
        if not explicit_secret or len(explicit_secret.strip()) < 32 or explicit_secret.strip().lower() in insecure_keys:
            raise RuntimeError(
                "Production configuration error: VISIONGUARD_SECRET_KEY environment variable "
                "must be configured with a secure, random secret key (minimum 32 characters) "
                "when running in production mode (VISIONGUARD_ENV=production)."
            )
        secret_key = explicit_secret.strip()
    else:
        if explicit_secret:
            secret_key = explicit_secret.strip()
        else:
            secret_key = secrets.token_hex(32)
            logger.info("VISIONGUARD_SECRET_KEY not set. Using ephemeral development key. Set VISIONGUARD_SECRET_KEY in production to persist user sessions across server restarts.")

    app.secret_key = secret_key

    # Session cookie hardening (Phase 4.6 & Phase 7)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    default_cookie_secure = is_production and (os.environ.get("VISIONGUARD_COOKIE_SECURE", "1") == "1")
    if not is_production:
        default_cookie_secure = os.environ.get("VISIONGUARD_COOKIE_SECURE", "0") == "1"
    app.config["SESSION_COOKIE_SECURE"] = default_cookie_secure

    app.config.setdefault("PERMANENT_SESSION_LIFETIME", datetime.timedelta(hours=8))
    app.config.setdefault("SEND_FILE_MAX_AGE_DEFAULT", 0)

    # Authentication & CSRF enforcement flags
    if test_config and "AUTH_ENABLED" in test_config:
        app.config["AUTH_ENABLED"] = bool(test_config["AUTH_ENABLED"])
        app.config["AUTH_ENABLED_EXPLICIT"] = True
    else:
        app.config["AUTH_ENABLED_EXPLICIT"] = False

    if test_config and "ENFORCE_CSRF" in test_config:
        app.config["ENFORCE_CSRF"] = bool(test_config["ENFORCE_CSRF"])
        app.config["ENFORCE_CSRF_EXPLICIT"] = True
    else:
        app.config["ENFORCE_CSRF_EXPLICIT"] = False

    # Ensure persistent directories exist
    for dir_path in [
        os.path.join(PROJECT_ROOT, "data"),
        os.path.join(PROJECT_ROOT, "data", "uploads"),
        os.path.join(PROJECT_ROOT, "data", "processed"),
    ]:
        os.makedirs(dir_path, exist_ok=True)

    # Initialize persistent storage backend (Local filesystem or Cloudflare R2)
    if test_config and "storage_backend" in test_config:
        app.storage_backend = test_config["storage_backend"]
    else:
        app.storage_backend = get_storage_backend(app.config)

    # Initialize persistence with configured database path
    db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
    init_db(db_path)

    # Safe first-administrator bootstrap from environment variables
    admin_user_result = init_admin_from_env(db_path)
    if is_production and not os.environ.get("VISIONGUARD_ADMIN_PASSWORD"):
        logger.warning(
            "SECURITY NOTICE: VISIONGUARD_ADMIN_PASSWORD is not set in production. "
            "Ensure default development accounts have their passwords updated."
        )

    # Initialize road and home DefectDetectionService instances
    if test_config and "detector" in test_config:
        app.detector = test_config["detector"]
    else:
        app.detector = detector or DefectDetectionService(domain="road")

    app.road_detector = app.detector

    if test_config and "home_detector" in test_config:
        app.home_detector = test_config["home_detector"]
    else:
        app.home_detector = home_detector or DefectDetectionService(domain="home", lazy=True)

    # -------------------------------------------------------------------------
    # Authentication & Access Control Helpers / Decorators (Phase 4.6)
    # -------------------------------------------------------------------------
    def is_auth_enforced() -> bool:
        if app.config.get("AUTH_ENABLED_EXPLICIT"):
            return bool(app.config.get("AUTH_ENABLED", False))
        if app.config.get("TESTING", False):
            return False
        return bool(app.config.get("AUTH_ENABLED", True))

    def is_csrf_enforced() -> bool:
        if app.config.get("ENFORCE_CSRF_EXPLICIT"):
            return bool(app.config.get("ENFORCE_CSRF", False))
        if app.config.get("TESTING", False):
            return False
        return bool(app.config.get("ENFORCE_CSRF", True))

    def get_or_create_csrf_token() -> str:
        """Returns or creates a cryptographic CSRF token in the user's session."""
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return session["csrf_token"]

    def get_current_user_record() -> Optional[dict]:
        """Returns the authenticated user dict from DB, or None if invalid/inactive."""
        user_id = session.get("user_id")
        if not user_id:
            return None
        current_db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        user = get_user_by_id(user_id, db_path=current_db_path)
        if not user or not user.get("is_active"):
            session.clear()
            return None
        return user

    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not is_auth_enforced():
                return f(*args, **kwargs)
            user = get_current_user_record()
            if not user:
                return jsonify({
                    "status": "error",
                    "error_code": "UNAUTHORIZED",
                    "message": "Authentication required. Please log in.",
                }), 401
            return f(*args, **kwargs)
        return decorated_function

    def roles_required(*allowed_roles):
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if not is_auth_enforced():
                    return f(*args, **kwargs)
                user = get_current_user_record()
                if not user:
                    return jsonify({
                        "status": "error",
                        "error_code": "UNAUTHORIZED",
                        "message": "Authentication required. Please log in.",
                    }), 401
                if user.get("role") not in allowed_roles:
                    return jsonify({
                        "status": "error",
                        "error_code": "FORBIDDEN",
                        "message": f"Access denied. Requires one of roles: {list(allowed_roles)}.",
                    }), 403
                return f(*args, **kwargs)
            return decorated_function
        return decorator

    @app.before_request
    def check_csrf_protection():
        """Enforces CSRF protection on state-changing requests when enabled."""
        if not is_auth_enforced() or not is_csrf_enforced():
            return None

        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None

        # Exempt paths that initiate authentication, registration, or initial admin setup
        exempt_paths = [
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/setup-admin",
        ]
        if request.path in exempt_paths:
            return None

        client_token = request.headers.get("X-CSRF-Token")
        if not client_token:
            if request.is_json and isinstance(request.json, dict):
                client_token = request.json.get("csrf_token")
            elif request.form:
                client_token = request.form.get("csrf_token")

        expected_token = session.get("csrf_token")
        if not client_token or not expected_token or not secrets.compare_digest(str(client_token), str(expected_token)):
            return jsonify({
                "status": "error",
                "error_code": "CSRF_TOKEN_INVALID",
                "message": "Missing or invalid CSRF token.",
            }), 403

        return None

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

    @app.errorhandler(405)
    def method_not_allowed(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "METHOD_NOT_ALLOWED",
                "message": "The requested HTTP method is not allowed on this endpoint.",
            }),
            405,
        )

    @app.errorhandler(500)
    def internal_error(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": getattr(error, "description", "An unexpected error occurred during processing."),
            }),
            500,
        )

    @app.errorhandler(502)
    def bad_gateway(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "BAD_GATEWAY",
                "message": "Upstream inference worker timed out or was temporarily unavailable.",
            }),
            502,
        )

    @app.errorhandler(503)
    def service_unavailable(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "SERVICE_UNAVAILABLE",
                "message": getattr(error, "description", "Service temporarily unavailable. Please retry shortly."),
            }),
            503,
        )

    @app.errorhandler(504)
    def gateway_timeout(error):
        return (
            jsonify({
                "status": "error",
                "error_code": "GATEWAY_TIMEOUT",
                "message": "Inference took longer than the server timeout. Please try with standard mode or smaller image.",
            }),
            504,
        )

    @app.errorhandler(Exception)
    def handle_unhandled_exception(error):
        from werkzeug.exceptions import HTTPException
        code = 500
        msg = "An unexpected server error occurred."
        if isinstance(error, HTTPException):
            code = error.code or 500
            msg = error.description or msg
        logger.exception("Unhandled exception on %s %s: %s", request.method, request.path, error)
        if request.path.startswith("/api/"):
            return (
                jsonify({
                    "status": "error",
                    "error_code": "INTERNAL_SERVER_ERROR" if code == 500 else "HTTP_ERROR",
                    "message": msg,
                }),
                code,
            )
        return jsonify({"status": "error", "message": msg}), code

    # -------------------------------------------------------------------------
    # API Routes
    # -------------------------------------------------------------------------
    @app.route("/", methods=["GET"])
    def index():
        """Serves the main inspection dashboard and upload interface."""
        return render_template("index.html", csrf_token=get_or_create_csrf_token())

    # -------------------------------------------------------------------------
    # Authentication & Session Routes (Phase 4.6)
    # -------------------------------------------------------------------------
    @app.route("/api/auth/login", methods=["POST"])
    def api_auth_login():
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}
        username = payload.get("username")
        password = payload.get("password")

        if not username or not password:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_CREDENTIALS",
                "message": "Username and password are required.",
            }), 400

        is_auth, user, err = authenticate_user(str(username).strip(), str(password), db_path=db_path)
        if not is_auth or not user:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_CREDENTIALS",
                "message": err or "Invalid username or password.",
            }), 401

        # Prevent session fixation: clear pre-existing session state and assign fresh CSRF token
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session.permanent = True
        csrf_tok = secrets.token_hex(32)
        session["csrf_token"] = csrf_tok

        return jsonify({
            "status": "success",
            "message": f"Welcome back, {user['username']}.",
            "user": user,
            "csrf_token": csrf_tok,
        }), 200

    @app.route("/api/auth/register", methods=["POST"])
    def api_auth_register():
        """
        Public citizen registration endpoint.
        Registers a citizen account (role=ROLE_CITIZEN) using secure scrypt password hashing
        and auto-authenticates the user within the active session.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}
        username = payload.get("username")
        password = payload.get("password")
        email = payload.get("email")

        if not username or not password:
            return jsonify({
                "status": "error",
                "error_code": "MISSING_CREDENTIALS",
                "message": "Username and password are required.",
            }), 400

        try:
            user = create_user(
                username=username,
                password=password,
                role=ROLE_CITIZEN,
                email=email,
                is_active=1,
                db_path=db_path
            )
            # Prevent session fixation: clear pre-existing session state and assign fresh CSRF token
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session.permanent = True
            csrf_tok = secrets.token_hex(32)
            session["csrf_token"] = csrf_tok

            return jsonify({
                "status": "success",
                "message": f"Welcome to VisionGuard AI, {user['username']}. Your citizen account has been created.",
                "user": user,
                "csrf_token": csrf_tok,
            }), 201
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "REGISTRATION_FAILED",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Error registering citizen account: {e}")
            return jsonify({
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": f"Registration failed: {str(e)}",
            }), 500

    @app.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        session.clear()
        new_csrf = get_or_create_csrf_token()
        return jsonify({
            "status": "success",
            "message": "Logged out successfully.",
            "csrf_token": new_csrf,
        }), 200

    @app.route("/api/auth/status", methods=["GET"])
    def api_auth_status():
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        csrf_tok = get_or_create_csrf_token()
        admin_count = count_admin_users(db_path=db_path)
        requires_setup = (admin_count == 0)

        setup_token_expected = bool((os.environ.get("VISIONGUARD_SETUP_TOKEN") or "").strip())
        is_production_mode = (
            os.environ.get("VISIONGUARD_ENV", "").lower() == "production"
            or app.config.get("ENV") == "production"
        ) and not app.config.get("TESTING", False)

        user = get_current_user_record()
        return jsonify({
            "status": "success",
            "authenticated": user is not None,
            "requires_setup": requires_setup,
            "setup_token_required": setup_token_expected,
            "web_setup_enabled": not (is_production_mode and not setup_token_expected),
            "user": user,
            "csrf_token": csrf_tok,
        }), 200

    @app.route("/api/auth/me", methods=["GET"])
    @login_required
    def api_auth_me():
        user = get_current_user_record()
        return jsonify({
            "status": "success",
            "user": user,
        }), 200

    @app.route("/api/auth/setup-admin", methods=["POST"])
    def api_auth_setup_admin():
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        # Prevent claiming administrator account if an active administrator exists
        if count_admin_users(db_path=db_path) > 0:
            return jsonify({
                "status": "error",
                "error_code": "SETUP_FORBIDDEN",
                "message": "Initial administrator setup has already been completed.",
            }), 403

        payload = request.get_json(silent=True) or {}

        # Controlled server-side bootstrap protection: prevent public visitors from claiming root admin
        setup_token_expected = (os.environ.get("VISIONGUARD_SETUP_TOKEN") or "").strip()
        is_production_mode = (
            os.environ.get("VISIONGUARD_ENV", "").lower() == "production"
            or app.config.get("ENV") == "production"
        ) and not app.config.get("TESTING", False)

        if setup_token_expected:
            client_token = (payload.get("setup_token") or "").strip()
            if not client_token or not secrets.compare_digest(client_token, setup_token_expected):
                return jsonify({
                    "status": "error",
                    "error_code": "SETUP_TOKEN_INVALID",
                    "message": "Invalid or missing server-side administrator setup token.",
                }), 403
        elif is_production_mode:
            return jsonify({
                "status": "error",
                "error_code": "SETUP_TOKEN_REQUIRED",
                "message": (
                    "Public administrator setup is disabled in production. "
                    "Configure VISIONGUARD_ADMIN_USERNAME and VISIONGUARD_ADMIN_PASSWORD in environment variables "
                    "or configure VISIONGUARD_SETUP_TOKEN to authorize web-based setup."
                ),
            }), 403

        username = payload.get("username")
        password = payload.get("password")
        email = payload.get("email")

        try:
            admin_user = create_user(
                username=username,
                password=password,
                role=ROLE_ADMIN,
                email=email,
                is_active=1,
                db_path=db_path
            )
            # Prevent session fixation: clear pre-existing session state and assign fresh CSRF token
            session.clear()
            session["user_id"] = admin_user["id"]
            session["username"] = admin_user["username"]
            session["role"] = admin_user["role"]
            session.permanent = True
            csrf_tok = secrets.token_hex(32)
            session["csrf_token"] = csrf_tok

            return jsonify({
                "status": "success",
                "message": f"Administrator account '{admin_user['username']}' configured successfully.",
                "user": admin_user,
                "csrf_token": csrf_tok,
            }), 201
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "VALIDATION_FAILED",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to bootstrap administrator: {e}")
            return jsonify({
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": f"Failed to bootstrap administrator: {str(e)}",
            }), 500

    # -------------------------------------------------------------------------
    # User Management API Routes (Phase 4.6 — Admin Only)
    # -------------------------------------------------------------------------
    @app.route("/api/users", methods=["GET"])
    @roles_required(ROLE_ADMIN)
    def api_list_users():
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        users = list_users(db_path=db_path)
        return jsonify({
            "status": "success",
            "count": len(users),
            "users": users,
            "roles": [
                {"role": r, "display_name": ROLE_DISPLAY_NAMES.get(r, r)}
                for r in ALLOWED_ROLES
            ]
        }), 200

    @app.route("/api/users", methods=["POST"])
    @roles_required(ROLE_ADMIN)
    def api_create_user():
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}
        username = payload.get("username")
        password = payload.get("password")
        role = payload.get("role", ROLE_INSPECTOR)
        email = payload.get("email")
        is_active = 1 if payload.get("is_active", True) else 0

        try:
            user = create_user(
                username=username,
                password=password,
                role=role,
                email=email,
                is_active=is_active,
                db_path=db_path
            )
            return jsonify({
                "status": "success",
                "message": f"User '{user['username']}' created successfully.",
                "user": user,
            }), 201
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "USER_CREATION_FAILED",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Error creating user: {e}")
            return jsonify({
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": f"Failed to create user: {str(e)}",
            }), 500

    @app.route("/api/users/<int:target_user_id>", methods=["PATCH"])
    @roles_required(ROLE_ADMIN)
    def api_update_user_route(target_user_id: int):
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}

        # Self-modification safety guards for administrators
        current_admin_id = session.get("user_id")
        if target_user_id == current_admin_id:
            if "is_active" in payload and not payload["is_active"]:
                return jsonify({
                    "status": "error",
                    "error_code": "SELF_DEACTIVATION_DENIED",
                    "message": "Administrators cannot deactivate their own active account.",
                }), 400
            if "role" in payload and str(payload["role"]).lower() != ROLE_ADMIN:
                return jsonify({
                    "status": "error",
                    "error_code": "SELF_DEMOTION_DENIED",
                    "message": "Administrators cannot demote their own account role.",
                }), 400

        try:
            updated = update_user(target_user_id, payload, db_path=db_path)
            if not updated:
                return jsonify({
                    "status": "error",
                    "error_code": "USER_NOT_FOUND",
                    "message": f"User with ID {target_user_id} not found.",
                }), 404

            return jsonify({
                "status": "success",
                "message": f"User '{updated['username']}' updated successfully.",
                "user": updated,
            }), 200
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "UPDATE_FAILED",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Error updating user {target_user_id}: {e}")
            return jsonify({
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": f"Failed to update user: {str(e)}",
            }), 500

    # -------------------------------------------------------------------------
    # Maintenance Task Assignment & Work Queue API Routes (Phase 4.7)
    # -------------------------------------------------------------------------
    @app.route("/api/maintenance/staff", methods=["GET"])
    @roles_required(ROLE_ADMIN)
    def api_get_maintenance_staff():
        """Returns list of active Maintenance Staff users eligible for assignment."""
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        staff = list_active_maintenance_staff(db_path=db_path)
        return jsonify({
            "status": "success",
            "count": len(staff),
            "staff": staff,
        }), 200

    @app.route("/api/inspections/<int:inspection_id>/assign", methods=["POST"])
    @roles_required(ROLE_ADMIN)
    def api_assign_inspection_task(inspection_id: int):
        """
        Assigns or reassigns an inspection to an active Maintenance Staff user.
        Admins only.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}
        assigned_to_user_id = payload.get("assigned_to_user_id")
        instructions = payload.get("instructions")

        if not assigned_to_user_id:
            return jsonify({
                "status": "error",
                "error_code": "MISSING_ASSIGNEE",
                "message": "Field 'assigned_to_user_id' is required.",
            }), 400

        try:
            assigned_to_user_id = int(assigned_to_user_id)
        except (ValueError, TypeError):
            return jsonify({
                "status": "error",
                "error_code": "INVALID_ASSIGNEE_ID",
                "message": "Field 'assigned_to_user_id' must be an integer user ID.",
            }), 400

        curr_admin = get_current_user_record()
        admin_id = curr_admin["id"] if curr_admin else 1

        try:
            res = assign_inspection_task(
                inspection_id=inspection_id,
                assigned_to_user_id=assigned_to_user_id,
                assigned_by_user_id=admin_id,
                instructions=instructions,
                db_path=db_path,
            )
            return jsonify({
                "status": "success",
                "message": f"Task #{inspection_id} successfully assigned to {res['assigned_to']['username']}.",
                "assignment": res,
                "inspection": res["inspection"],
            }), 200
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "ASSIGNMENT_FAILED",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to assign task #{inspection_id}: {e}")
            return jsonify({
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": f"Task assignment error: {str(e)}",
            }), 500

    @app.route("/api/inspections/<int:inspection_id>/cancel-assignment", methods=["POST"])
    @roles_required(ROLE_ADMIN)
    def api_cancel_inspection_assignment(inspection_id: int):
        """
        Cancels an active task assignment for an inspection.
        Admins only.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}
        reason = payload.get("reason")

        curr_admin = get_current_user_record()
        admin_id = curr_admin["id"] if curr_admin else 1

        try:
            res = cancel_inspection_assignment(
                inspection_id=inspection_id,
                cancelled_by_user_id=admin_id,
                cancellation_reason=reason,
                db_path=db_path,
            )
            return jsonify({
                "status": "success",
                "message": res["message"],
                "inspection": res["inspection"],
            }), 200
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "CANCELLATION_FAILED",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to cancel assignment for #{inspection_id}: {e}")
            return jsonify({
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": f"Cancellation error: {str(e)}",
            }), 500

    @app.route("/api/maintenance/queue", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_MAINTENANCE)
    def api_get_maintenance_queue():
        """
        Returns tasks in the Maintenance Work Queue.
        - Maintenance staff: scoped strictly to tasks assigned to them.
        - Admin: can view all assigned tasks or filter by assigned_to_user_id.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        curr_user = get_current_user_record()

        target_user_id = None
        if curr_user and curr_user["role"] == ROLE_MAINTENANCE:
            target_user_id = curr_user["id"]
        elif curr_user and curr_user["role"] == ROLE_ADMIN:
            req_user_id = request.args.get("assigned_to_user_id")
            if req_user_id:
                try:
                    target_user_id = int(req_user_id)
                except (ValueError, TypeError):
                    target_user_id = None

        assign_status = request.args.get("status") or request.args.get("assignment_status")
        wf_status = request.args.get("workflow_status")
        urgency = request.args.get("urgency") or request.args.get("deadline")
        category = request.args.get("category")
        domain = request.args.get("domain") or request.args.get("inspection_type")
        city = request.args.get("city")
        area = request.args.get("area")
        search_query = request.args.get("q") or request.args.get("search")
        sort_by = request.args.get("sort_by") or request.args.get("sort")

        include_unassigned = False
        if curr_user and curr_user["role"] == ROLE_ADMIN:
            if request.args.get("include_unassigned") in ("1", "true", "yes") or assign_status in ("all", "any", "unassigned"):
                include_unassigned = True

        try:
            limit = min(500, max(1, int(request.args.get("limit", 100))))
            offset = max(0, int(request.args.get("offset", 0)))
        except (TypeError, ValueError):
            limit = 100
            offset = 0

        tasks = get_maintenance_work_queue(
            user_id=target_user_id,
            assignment_status=assign_status,
            workflow_status=wf_status,
            urgency=urgency,
            category=category,
            domain=domain,
            city=city,
            area=area,
            search_query=search_query,
            sort_by=sort_by,
            include_unassigned=include_unassigned,
            limit=limit,
            offset=offset,
            db_path=db_path,
        )

        # Compute telemetry counts for queue view
        total_count = len(tasks)
        assigned_cnt = sum(1 for t in tasks if t.get("assignment_status") == "assigned")
        in_prog_cnt = sum(1 for t in tasks if t.get("assignment_status") == "in_progress")
        overdue_cnt = sum(1 for t in tasks if t.get("maintenance_urgency") == "overdue")
        completed_cnt = sum(1 for t in tasks if t.get("assignment_status") == "completed" or t.get("status") == "Resolved")

        return jsonify({
            "status": "success",
            "count": total_count,
            "tasks": tasks,
            "counts": {
                "total": total_count,
                "assigned": assigned_cnt,
                "in_progress": in_prog_cnt,
                "overdue": overdue_cnt,
                "completed": completed_cnt,
            },
            "user_id": target_user_id,
            "disclaimer": (
                "Notice: Work queue assignments, status tracking, and notes reflect administrative "
                "task management and do not certify completed physical road engineering repairs."
            ),
        }), 200

    @app.route("/api/inspections/<int:inspection_id>/assignments", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE)
    def api_get_inspection_assignments(inspection_id: int):
        """
        Returns chronological task assignment history for an inspection.
        Maintenance staff can only access tasks assigned to them or unassigned.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        curr_user = get_current_user_record()

        record = get_inspection_by_id(inspection_id, db_path=db_path)
        if not record:
            return jsonify({
                "status": "error",
                "error_code": "INSPECTION_NOT_FOUND",
                "message": f"Inspection record #{inspection_id} not found.",
            }), 404

        if curr_user and curr_user["role"] == ROLE_MAINTENANCE:
            if record.get("assigned_to_user_id") is not None and record.get("assigned_to_user_id") != curr_user["id"]:
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_TASK_NOT_ASSIGNED",
                    "message": "Access denied: This inspection task is assigned to another team member.",
                }), 403

        history = get_inspection_assignment_history(inspection_id, db_path=db_path)
        return jsonify({
            "status": "success",
            "inspection_id": inspection_id,
            "count": len(history),
            "assignments": history,
        }), 200

    @app.route("/api/health", methods=["GET"])
    def api_health():
        """
        Telemetry and health check reporting database and AI model status.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        db_health = check_db_health(db_path)
        is_render_production = (
            os.environ.get("VISIONGUARD_ENV") == "production"
            or "/opt/render" in str(db_path)
        )
        if db_health.get("engine") == "sqlite" and is_render_production:
            db_health["ephemeral_warning"] = (
                "Running ephemeral SQLite in production container; data will reset on redeployment. "
                "Set DATABASE_URL to connect persistent Neon PostgreSQL."
            )
        storage_type = "r2" if isinstance(getattr(app, "storage_backend", None), CloudflareR2StorageBackend) else "local"
        return jsonify({
            "status": "healthy",
            "database": db_health,
            "storage": {
                "backend": storage_type,
                "ready": True,
            },
            "model": {
                "loaded": app.detector.is_loaded,
                "status_message": app.detector.status_message,
                "checkpoint_path": app.detector.model_path,
                "supported_classes": [CLASS_NAMES[i] for i in sorted(CLASS_NAMES.keys())],
            },
            "road_model": {
                "domain": "road",
                "loaded": app.detector.is_loaded,
                "status_message": app.detector.status_message,
                "checkpoint_path": app.detector.model_path,
                "supported_classes": [ROAD_CLASS_NAMES[i] for i in sorted(ROAD_CLASS_NAMES.keys())],
            },
            "home_model": {
                "domain": "home",
                "loaded": app.home_detector.is_loaded,
                "status_message": app.home_detector.status_message,
                "checkpoint_path": app.home_detector.model_path,
                "supported_classes": [HOME_CLASS_NAMES[i] for i in sorted(HOME_CLASS_NAMES.keys())],
            },
            "limits": {
                "max_file_size_mb": max_mb,
                "supported_extensions": sorted(list(SUPPORTED_EXTENSIONS)),
            },
        }), 200

    @app.route("/api/classes", methods=["GET"])
    def api_classes():
        """
        Returns supported defect classes and their descriptions for road or home domain.
        """
        domain = request.args.get("domain", "road").lower().strip()
        if domain not in ("road", "home"):
            return jsonify({
                "status": "error",
                "error_code": "INVALID_DOMAIN",
                "message": f"Domain '{domain}' is invalid. Allowed domains: ['road', 'home'].",
            }), 400

        if domain == "home":
            classes_data = []
            for cid, cname in sorted(HOME_CLASS_NAMES.items()):
                display_name = HOME_CLASS_DISPLAY_NAMES.get(cname, cname)
                classes_data.append({
                    "class_id": cid,
                    "class_name": cname,
                    "display_name": display_name,
                    "domain": "home",
                    "category": (
                        "crack" if "crack" in cname
                        else "water_damage" if "damp" in cname or "water" in cname
                        else "surface_defect" if "peeling" in cname
                        else "structural_loss"
                    ),
                })
            return jsonify({
                "status": "success",
                "domain": "home",
                "classes": classes_data,
            }), 200

        # Default / road domain
        classes_data = []
        for cid, cname in sorted(ROAD_CLASS_NAMES.items()):
            display_name = ROAD_CLASS_DISPLAY_NAMES.get(cname, cname)
            classes_data.append({
                "class_id": cid,
                "class_name": cname,
                "display_name": display_name,
                "domain": "road",
                "category": "crack" if "crack" in cname else "pothole",
            })
        return jsonify({
            "status": "success",
            "domain": "road",
            "classes": classes_data,
        }), 200

    @app.route("/api/reload-model", methods=["POST"])
    @roles_required(ROLE_ADMIN)
    def api_reload_model():
        """
        Re-attempts loading model checkpoints from disk.
        Supports 'domain' query/json param ('road', 'home', or 'all').
        """
        domain = request.args.get("domain")
        if not domain and request.is_json and isinstance(request.json, dict):
            domain = request.json.get("domain")
        domain = (domain or "road").lower().strip()

        if domain not in ("road", "home", "all"):
            return jsonify({
                "status": "error",
                "error_code": "INVALID_DOMAIN",
                "message": f"Domain '{domain}' is invalid. Allowed: ['road', 'home', 'all'].",
            }), 400

        if domain == "home":
            success = bool(app.home_detector.load_model())
            status_code = 200 if success else 503
            return jsonify({
                "status": "success" if success else "error",
                "domain": "home",
                "reloaded_domain": "home",
                "loaded": bool(success),
                "message": app.home_detector.status_message,
                "checkpoint_path": app.home_detector.model_path,
            }), status_code
        elif domain == "all":
            road_ok = bool(app.detector.load_model())
            home_ok = bool(app.home_detector.load_model())
            all_ok = road_ok and home_ok
            status_code = 200 if all_ok else 503
            return jsonify({
                "status": "success" if all_ok else "partial",
                "domain": "all",
                "reloaded_domain": "all",
                "road": {
                    "loaded": bool(road_ok),
                    "message": app.detector.status_message,
                    "checkpoint_path": app.detector.model_path,
                },
                "home": {
                    "loaded": bool(home_ok),
                    "message": app.home_detector.status_message,
                    "checkpoint_path": app.home_detector.model_path,
                },
            }), status_code
        else:
            success = bool(app.detector.load_model())
            status_code = 200 if success else 503
            return jsonify({
                "status": "success" if success else "error",
                "domain": "road",
                "reloaded_domain": "road",
                "loaded": bool(success),
                "message": app.detector.status_message,
                "checkpoint_path": app.detector.model_path,
            }), status_code

    @app.route("/api/inspect", methods=["POST"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_CITIZEN)
    def api_inspect():
        """
        Primary defect inspection endpoint.
        Accepts multipart/form-data image stream, validates format,
        runs genuine YOLOv8 defect detection, and renders visual overlay.
        Includes high-resolution safety clamping and timing telemetry.
        """
        t_req_start = time.perf_counter()

        acquired = INSPECTION_SEMAPHORE.acquire(blocking=True, timeout=20.0)
        if not acquired:
            return (
                jsonify({
                    "status": "error",
                    "error_code": "SERVER_OVERLOADED",
                    "message": "VisionGuard AI server is currently processing another inspection. Please try again in a few seconds.",
                }),
                503,
            )

        try:
            return _execute_inspection_internal(t_req_start)
        finally:
            INSPECTION_SEMAPHORE.release()
            gc.collect()

    def _execute_inspection_internal(t_req_start):
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

        raw_filename = file.filename
        safe_name = secure_filename(os.path.basename(raw_filename))
        filename = safe_name if safe_name else f"upload_{uuid.uuid4().hex[:8]}.jpg"
        raw_bytes = file.read()
        file_stream = io.BytesIO(raw_bytes)

        # 2. Validate image stream (format, size, integrity)
        t_val_start = time.perf_counter()
        is_valid, err_msg, metadata = validate_image_stream(file_stream, filename)
        t_val_ms = (time.perf_counter() - t_val_start) * 1000
        if not is_valid:
            return (
                jsonify({
                    "status": "error",
                    "error_code": "INVALID_IMAGE",
                    "message": err_msg or "Image validation failed.",
                }),
                400,
            )

        # 3. Resolve and validate inspection domain (road vs home)
        domain_raw = (
            request.form.get("domain")
            or request.form.get("inspection_type")
            or request.form.get("problem_type")
            or "road"
        )
        domain = str(domain_raw).lower().strip()
        if domain not in ("road", "home"):
            return (
                jsonify({
                    "status": "error",
                    "error_code": "INVALID_DOMAIN",
                    "message": f"Unsupported inspection domain '{domain}'. Allowed values: ['road', 'home'].",
                }),
                400,
            )

        active_detector = app.home_detector if domain == "home" else app.detector

        # 4. Verify model checkpoint readiness
        if not active_detector.is_loaded:
            setup_instructions = (
                "1. Download 'home_best.pt' from your Google Drive ('VisionGuard_Artifacts/home_best.pt') "
                "or Google Colab export.\n"
                f"2. Copy 'home_best.pt' to '{active_detector.model_path}'.\n"
                "3. Call 'POST /api/reload-model?domain=home' or restart the server."
            ) if domain == "home" else (
                "1. Download 'best.pt' from your Google Drive ('VisionGuard_Artifacts/best.pt') "
                "or Google Colab export.\n"
                f"2. Copy 'best.pt' to '{active_detector.model_path}'.\n"
                "3. Call 'POST /api/reload-model?domain=road' or restart the server."
            )
            return (
                jsonify({
                    "status": "error",
                    "error_code": "MODEL_WEIGHTS_MISSING",
                    "domain": domain,
                    "message": (
                        f"{'Home' if domain == 'home' else 'Road'} model weights checkpoint '{active_detector.model_path}' is not present on the server. "
                        "VisionGuard AI requires authentic model weights and does not fabricate detections."
                    ),
                    "setup_instructions": setup_instructions,
                    "metadata": metadata,
                }),
                503,
            )

        # 5. Decode with OpenCV
        t_dec_start = time.perf_counter()
        file_stream.seek(0)
        cv_img = load_image_as_opencv(file_stream)
        t_dec_ms = (time.perf_counter() - t_dec_start) * 1000
        if cv_img is None:
            return (
                jsonify({
                    "status": "error",
                    "error_code": "IMAGE_DECODE_FAILED",
                    "message": "OpenCV failed to decode image into an array. File may be corrupted.",
                }),
                400,
            )

        # Resolution safety guard: prevents massive memory spikes and Gunicorn timeout on Render Free
        t_prep_start = time.perf_counter()
        h, w = cv_img.shape[:2]
        max_dim = max(h, w)
        if max_dim > 1280:
            scale = 1280.0 / max_dim
            new_w = int(round(w * scale))
            new_h = int(round(h * scale))
            cv_img = cv2.resize(cv_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            logger.info("Resized high-res image from %dx%d to %dx%d for 512MB RAM budget", w, h, new_w, new_h)

        conf_param = request.form.get("confidence_threshold", "0.25")
        try:
            conf_thresh = float(conf_param)
            conf_thresh = max(0.05, min(0.95, conf_thresh))
        except ValueError:
            conf_thresh = 0.25

        inspection_mode = request.form.get("inspection_mode", "standard").lower().strip()
        if inspection_mode not in ["standard", "tiled", "sliced"]:
            inspection_mode = "standard"
        t_prep_ms = (time.perf_counter() - t_prep_start) * 1000

        # 6. Execute genuine detection (serialized under lock to prevent peak memory stacking)
        t_inf_start = time.perf_counter()
        try:
            with INFERENCE_LOCK:
                if inspection_mode in ["tiled", "sliced"] and hasattr(active_detector, "detect_sliced"):
                    detections = active_detector.detect_sliced(
                        cv_img,
                        conf_threshold=conf_thresh,
                        raise_if_unloaded=True,
                    )
                else:
                    detections = active_detector.detect(
                        cv_img,
                        conf_threshold=conf_thresh,
                        raise_if_unloaded=True,
                    )
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
        t_inf_ms = (time.perf_counter() - t_inf_start) * 1000

        # 7. Generate genuine visual overlay
        t_post_start = time.perf_counter()
        annotated_bgr = active_detector.draw_annotations(cv_img, detections)
        annotated_b64 = active_detector.encode_image_to_base64(annotated_bgr)
        t_post_ms = (time.perf_counter() - t_post_start) * 1000

        # 8. Persist images via configured storage backend
        t_stor_start = time.perf_counter()
        orig_filename = f"orig_{uuid.uuid4().hex[:8]}_{filename}"
        orig_key = f"uploads/{orig_filename}"
        try:
            orig_path = app.storage_backend.save(orig_key, raw_bytes, content_type="image/jpeg")
        except Exception as e:
            logger.warning(f"Failed to persist original image: {e}")
            orig_path = None

        saved_filename = f"annotated_{uuid.uuid4().hex[:8]}_{filename}"
        saved_key = f"processed/{saved_filename}"
        try:
            _, buffer = cv2.imencode(".jpg", annotated_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            saved_path = app.storage_backend.save(saved_key, buffer.tobytes(), content_type="image/jpeg")
        except Exception as e:
            logger.warning(f"Failed to persist annotated image: {e}")
            saved_path = None
        t_stor_ms = (time.perf_counter() - t_stor_start) * 1000

        t_total_ms = (time.perf_counter() - t_req_start) * 1000
        logger.info(
            "Inspection complete for '%s' in %.1fms [val=%.1fms, dec=%.1fms, prep=%.1fms, inf=%.1fms, post=%.1fms, stor=%.1fms] (domain=%s, mode=%s, detections=%d)",
            filename,
            t_total_ms,
            t_val_ms,
            t_dec_ms,
            t_prep_ms,
            t_inf_ms,
            t_post_ms,
            t_stor_ms,
            domain,
            inspection_mode,
            len(detections),
        )

        disclaimer = (
            "Notice: Detection confidence measures model statistical likelihood, "
            "not physical structural safety, load-bearing capacity, or damage severity."
        ) if domain == "home" else (
            "Notice: Detection confidence measures model statistical likelihood, "
            "not physical crack severity, cavity depth, or roadway structural safety."
        )

        return jsonify({
            "status": "success",
            "domain": domain,
            "inspection_type": domain,
            "filename": filename,
            "metadata": metadata,
            "model_info": active_detector.model_info,
            "inspection_mode": inspection_mode,
            "confidence_threshold": conf_thresh,
            "candidate_summary": getattr(active_detector, "last_inference_stats", {}),
            "detections": detections,
            "defect_count": len(detections),
            "annotated_image": annotated_b64,
            "original_file_path": orig_path,
            "processed_file_path": saved_path,
            "timings": {
                "validation_ms": round(t_val_ms, 1),
                "decode_ms": round(t_dec_ms, 1),
                "preprocessing_ms": round(t_prep_ms, 1),
                "inference_ms": round(t_inf_ms, 1),
                "postprocessing_ms": round(t_post_ms, 1),
                "storage_ms": round(t_stor_ms, 1),
                "total_ms": round(t_total_ms, 1),
            },
            "disclaimer": disclaimer,
            "safety_disclaimer": disclaimer,
        }), 200

    # -------------------------------------------------------------------------
    # Inspection Records API Routes
    # -------------------------------------------------------------------------
    @app.route("/api/dashboard/stats", methods=["GET"])
    @app.route("/api/dashboard/analytics", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE)
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
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN)
    def api_get_inspections():
        """
        Lists saved inspection records with optional filtering.
        Query params: status, category, q (search query), limit, offset, my_reports, all_civic.
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

        deadline_filter = request.args.get("deadline") or request.args.get("urgency")
        assigned_to_user_id = request.args.get("assigned_to_user_id")
        assigned_to_me = request.args.get("assigned_to_me")
        assignment_status_filter = request.args.get("assignment_status")

        curr_user = get_current_user_record()
        parsed_assigned_user_id = None
        if assigned_to_me and assigned_to_me.lower() in ["1", "true", "yes"] and curr_user:
            parsed_assigned_user_id = curr_user["id"]
        elif assigned_to_user_id:
            try:
                parsed_assigned_user_id = int(assigned_to_user_id)
            except (ValueError, TypeError):
                parsed_assigned_user_id = None

        # Filter by creator (e.g. for citizen "My Reports")
        my_reports = request.args.get("my_reports") or request.args.get("created_by_me")
        created_by_filter = None
        created_by_username_filter = None
        if my_reports and my_reports.lower() in ["1", "true", "yes"] and curr_user:
            created_by_filter = curr_user["id"]
            created_by_username_filter = curr_user.get("username")
        elif curr_user and curr_user.get("role") == ROLE_CITIZEN:
            # If citizen is exploring the Defect Map (has_coords=true or all_civic=true) without my_reports,
            # allow them to view all civic geotagged map records across the city.
            if has_coords or request.args.get("all_civic") in ["1", "true", "yes"]:
                created_by_filter = None
                created_by_username_filter = None
            else:
                # By default, citizens viewing their personal records list see only their own reports
                created_by_filter = curr_user["id"]
                created_by_username_filter = curr_user.get("username")
        elif request.args.get("created_by_user_id"):
            try:
                created_by_filter = int(request.args.get("created_by_user_id"))
            except (ValueError, TypeError):
                created_by_filter = None

        complaint_status_filter = request.args.get("complaint_status")
        sort_by = request.args.get("sort_by") or request.args.get("sort") or "newest"
        date_filter = request.args.get("date")
        start_date = request.args.get("start_date") or (date_filter.strip() if date_filter and date_filter.strip() else None)
        end_date = request.args.get("end_date") or (date_filter.strip() if date_filter and date_filter.strip() else None)

        try:
            limit = min(500, max(1, int(request.args.get("limit", 100))))
            offset = max(0, int(request.args.get("offset", 0)))
        except (TypeError, ValueError):
            limit = 100
            offset = 0

        domain_filter = request.args.get("domain") or request.args.get("inspection_type")

        inspections = get_inspections(
            status=status_filter if status_filter and status_filter.lower() != "all" else None,
            limit=limit,
            offset=offset,
            category=category_filter if category_filter and category_filter.lower() != "all" else None,
            search_query=search_query,
            has_coords=has_coords,
            deadline_filter=deadline_filter if deadline_filter and deadline_filter.lower() != "all" else None,
            start_date=start_date,
            end_date=end_date,
            assigned_to_user_id=parsed_assigned_user_id,
            assignment_status=assignment_status_filter,
            created_by_user_id=created_by_filter,
            created_by_username=created_by_username_filter,
            domain=domain_filter if domain_filter and domain_filter.lower() != "all" else None,
            complaint_status=complaint_status_filter,
            sort_by=sort_by,
            db_path=db_path
        )
        resp_data = {
            "status": "success",
            "count": len(inspections),
            "inspections": inspections,
        }
        if curr_user and curr_user.get("role") == ROLE_CITIZEN:
            resp_data["citizen_summary"] = get_citizen_dashboard_summary(curr_user["id"], username=curr_user.get("username"), db_path=db_path)

        return jsonify(resp_data), 200

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
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_CITIZEN)
    def api_save_inspection():
        """
        Saves a completed road or home inspection into the database.
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

        # Domain / Inspection Type
        domain_val = (payload.get("domain") or payload.get("inspection_type") or "road").strip().lower()
        if domain_val not in ("road", "home"):
            domain_val = "road"
        payload["inspection_type"] = domain_val

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

        # Validate Target Repair Date if supplied
        target_repair_date = payload.get("target_repair_date")
        if target_repair_date is not None and str(target_repair_date).strip() != "":
            is_valid_date, norm_date, date_err = validate_target_repair_date(target_repair_date)
            if not is_valid_date:
                return jsonify({
                    "status": "error",
                    "error_code": "INVALID_TARGET_REPAIR_DATE",
                    "message": date_err,
                }), 400
            payload["target_repair_date"] = norm_date
        # Sanitize image paths in payload to ensure they reside in authorized project data directory
        data_root = os.path.abspath(os.path.join(PROJECT_ROOT, "data"))
        project_root_abs = os.path.abspath(PROJECT_ROOT)
        for path_key in ("original_image_path", "annotated_image_path"):
            val = payload.get(path_key)
            if val and isinstance(val, str) and val.strip():
                abs_val = os.path.abspath(val.strip())
                if not abs_val.startswith(data_root) and not abs_val.startswith(project_root_abs):
                    payload[path_key] = None

        original_image_path = (payload.get("original_image_path") or "").strip()
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
            curr_user = get_current_user_record()
            if curr_user:
                payload["created_by_user_id"] = curr_user["id"]
                payload["created_by_username"] = curr_user["username"]
            t_db_start = time.perf_counter()
            record = save_inspection(payload, db_path=db_path)
            t_db_ms = (time.perf_counter() - t_db_start) * 1000
            logger.info("Inspection record saved (ID: %s) to database in %.1fms", record.get("id"), t_db_ms)
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
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN)
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

        curr_user = get_current_user_record()
        if curr_user and curr_user["role"] == ROLE_MAINTENANCE:
            assigned_id = record.get("assigned_to_user_id")
            if assigned_id is not None and int(assigned_id) != int(curr_user["id"]):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_TASK_NOT_ASSIGNED",
                    "message": "Access denied: This inspection task is assigned to another team member.",
                }), 403

        if curr_user and curr_user["role"] == ROLE_CITIZEN:
            created_by_id = record.get("created_by_user_id")
            created_by_name = record.get("created_by_username")
            u_id = curr_user.get("id")
            u_name = curr_user.get("username")
            id_match = (created_by_id is not None and u_id is not None and int(created_by_id) == int(u_id))
            name_match = (created_by_name and u_name and str(created_by_name).lower() == str(u_name).lower())
            if not (id_match or name_match):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_REPORT_ACCESS",
                    "message": "Access denied: Citizens may only view their own inspection records.",
                }), 403

            # Phase 5: Privacy Guardrail - Mask internal staff data and dispatch notes for citizens
            record["assignments"] = []
            record["assignment_instructions"] = ""
            record["assigned_to_user_id"] = None
            record["assigned_to_username"] = "Operations Team" if record.get("assigned_to_username") else None
            record["assigned_by_user_id"] = None
            record["assigned_by_username"] = None

            if "activity_log" in record:
                sanitized_log = []
                for entry in record.get("activity_log", []):
                    item = dict(entry)
                    item["user_id"] = None
                    item["username"] = "Operations Team"
                    if item.get("action_type") in ("assigned", "reassigned", "assignment_cancelled"):
                        item["notes"] = "Remediation crew dispatched for inspection and maintenance scheduling."
                    sanitized_log.append(item)
                record["activity_log"] = sanitized_log

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
    @roles_required(ROLE_ADMIN, ROLE_MAINTENANCE)
    def api_update_inspection_status(inspection_id: int):
        """
        Updates the status of an inspection record.
        Allowed initial states: Open, Under Review, Assigned, Repair in Progress, Resolved, Reopened.
        Also accepts optional location metadata updates.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        curr_user = get_current_user_record()
        existing_record = get_inspection_by_id(inspection_id, db_path=db_path)
        if not existing_record:
            return jsonify({
                "status": "error",
                "error_code": "INSPECTION_NOT_FOUND",
                "message": f"Inspection record #{inspection_id} not found.",
            }), 404

        if curr_user and curr_user["role"] == ROLE_MAINTENANCE:
            assigned_id = existing_record.get("assigned_to_user_id")
            if assigned_id is not None and int(assigned_id) != int(curr_user["id"]):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_TASK_NOT_ASSIGNED",
                    "message": "Access denied: You are only authorized to update tasks assigned directly to you.",
                }), 403

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

        # Phase 5 Server-side Lifecycle Validations
        notes_val = (payload.get("notes") or "").strip()
        if new_status == "Resolved" and not notes_val:
            return jsonify({
                "status": "error",
                "error_code": "MISSING_RESOLUTION_NOTES",
                "message": "A resolution note detailing repair actions and verification evidence is required before marking an inspection as Resolved.",
            }), 400

        if new_status == "Reopened" and not notes_val:
            return jsonify({
                "status": "error",
                "error_code": "MISSING_REOPEN_NOTES",
                "message": "Notes explaining the reason for reopening are required before marking an inspection as Reopened.",
            }), 400

        old_st = existing_record.get("status")
        if old_st == "Resolved" and new_status not in ["Resolved", "Reopened", "Under Review"]:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_STATUS_TRANSITION",
                "message": f"Cannot transition directly from 'Resolved' to '{new_status}'. The inspection must be marked as 'Reopened' first.",
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

        # Validate target_repair_date if supplied
        if "target_repair_date" in payload:
            tr_date = payload.get("target_repair_date")
            if tr_date is not None and str(tr_date).strip() != "":
                is_valid_date, norm_date, date_err = validate_target_repair_date(tr_date)
                if not is_valid_date:
                    return jsonify({
                        "status": "error",
                        "error_code": "INVALID_TARGET_REPAIR_DATE",
                        "message": date_err,
                    }), 400
                payload["target_repair_date"] = norm_date
            else:
                payload["target_repair_date"] = None

        try:
            curr_user = get_current_user_record()
            u_id = curr_user["id"] if curr_user else None
            u_name = curr_user["username"] if curr_user else None
            updated = update_inspection(inspection_id, payload, user_id=u_id, username=u_name, db_path=db_path)
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
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_STATUS_TRANSITION",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to update inspection #{inspection_id} status: {e}")
            return jsonify({
                "status": "error",
                "error_code": "UPDATE_FAILED",
                "message": f"Status update failed: {str(e)}",
            }), 500

    @app.route("/api/inspections/<int:inspection_id>", methods=["PATCH", "PUT"])
    @roles_required(ROLE_ADMIN, ROLE_MAINTENANCE)
    def api_update_inspection(inspection_id: int):
        """
        Updates location metadata, notes, and/or status for an existing inspection.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        curr_user = get_current_user_record()
        existing_record = get_inspection_by_id(inspection_id, db_path=db_path)
        if not existing_record:
            return jsonify({
                "status": "error",
                "error_code": "INSPECTION_NOT_FOUND",
                "message": f"Inspection record #{inspection_id} not found.",
            }), 404

        if curr_user and curr_user["role"] == ROLE_MAINTENANCE:
            assigned_id = existing_record.get("assigned_to_user_id")
            if assigned_id is not None and int(assigned_id) != int(curr_user["id"]):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_TASK_NOT_ASSIGNED",
                    "message": "Access denied: You are only authorized to update tasks assigned directly to you.",
                }), 403

        payload = request.get_json(silent=True) or {}

        if "status" in payload:
            status_val = payload["status"]
            if status_val not in ALLOWED_STATUSES:
                return jsonify({
                    "status": "error",
                    "error_code": "INVALID_STATUS",
                    "message": f"Status '{status_val}' is invalid. Allowed: {ALLOWED_STATUSES}",
                }), 400
            notes_val = (payload.get("notes") or payload.get("location_notes") or "").strip()
            if status_val == "Resolved" and not notes_val:
                return jsonify({
                    "status": "error",
                    "error_code": "MISSING_RESOLUTION_NOTES",
                    "message": "A resolution note detailing repair actions and verification evidence is required before marking an inspection as Resolved.",
                }), 400
            if status_val == "Reopened" and not notes_val:
                return jsonify({
                    "status": "error",
                    "error_code": "MISSING_REOPEN_NOTES",
                    "message": "Notes explaining the reason for reopening are required before marking an inspection as Reopened.",
                }), 400
            old_st = existing_record.get("status")
            if old_st == "Resolved" and status_val not in ["Resolved", "Reopened", "Under Review"]:
                return jsonify({
                    "status": "error",
                    "error_code": "INVALID_STATUS_TRANSITION",
                    "message": f"Cannot transition directly from 'Resolved' to '{status_val}'. The inspection must be marked as 'Reopened' first.",
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

        # Validate target_repair_date if supplied
        if "target_repair_date" in payload:
            tr_date = payload.get("target_repair_date")
            if tr_date is not None and str(tr_date).strip() != "":
                is_valid_date, norm_date, date_err = validate_target_repair_date(tr_date)
                if not is_valid_date:
                    return jsonify({
                        "status": "error",
                        "error_code": "INVALID_TARGET_REPAIR_DATE",
                        "message": date_err,
                    }), 400
                payload["target_repair_date"] = norm_date
            else:
                payload["target_repair_date"] = None

        try:
            curr_user = get_current_user_record()
            u_id = curr_user["id"] if curr_user else None
            u_name = curr_user["username"] if curr_user else None
            updated = update_inspection(inspection_id, payload, user_id=u_id, username=u_name, db_path=db_path)
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
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_UPDATE",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to update inspection #{inspection_id}: {e}")
            return jsonify({
                "status": "error",
                "error_code": "UPDATE_FAILED",
                "message": f"Inspection update failed: {str(e)}",
            }), 500

    @app.route("/api/inspections/<int:inspection_id>", methods=["DELETE"])
    @roles_required(ROLE_ADMIN)
    def api_delete_inspection(inspection_id: int):
        """
        Deletes an inspection record and its associated data. Admin only.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        success = delete_inspection(inspection_id, db_path=db_path)
        if not success:
            return jsonify({
                "status": "error",
                "error_code": "INSPECTION_NOT_FOUND",
                "message": f"Inspection record #{inspection_id} not found.",
            }), 404
        return jsonify({
            "status": "success",
            "message": f"Inspection record #{inspection_id} deleted successfully.",
        }), 200

    @app.route("/api/inspections/<int:inspection_id>/image/<img_type>", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN)
    def api_get_inspection_image(inspection_id: int, img_type: str):
        """
        Serves the original or annotated image file for a saved inspection.
        img_type: 'original' or 'annotated'.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        record = get_inspection_by_id(inspection_id, db_path=db_path)
        if not record:
            return jsonify({"status": "error", "message": f"Inspection #{inspection_id} not found."}), 404

        curr_user = get_current_user_record()
        if curr_user and curr_user["role"] == ROLE_CITIZEN:
            created_by = record.get("created_by_user_id")
            if created_by is None or int(created_by) != int(curr_user["id"]):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_REPORT_ACCESS",
                    "message": "Access denied: Citizens may only access images from their own inspection records.",
                }), 403

        if img_type == "original":
            target_path = record.get("original_image_path") or record.get("file_path")
        elif img_type == "annotated":
            target_path = record.get("annotated_image_path")
        else:
            return jsonify({"status": "error", "message": "Invalid image type. Use 'original' or 'annotated'."}), 400

        if not target_path:
            return jsonify({
                "status": "error",
                "error_code": "IMAGE_FILE_NOT_FOUND",
                "message": "Image record does not specify an image path.",
            }), 404

        # 1. Check if storage backend provides direct presigned URL (e.g. Cloudflare R2)
        url = app.storage_backend.get_url(target_path, expires_in=3600)
        if url:
            from flask import redirect
            return redirect(url)

        # 2. Try retrieving bytes from configured storage backend
        img_bytes = app.storage_backend.get_bytes(target_path)
        if img_bytes is not None:
            import io
            ext = os.path.splitext(target_path)[1].lower()
            mimetype = "image/png" if ext == ".png" else "image/jpeg"
            return send_file(io.BytesIO(img_bytes), mimetype=mimetype)

        # 3. Fallback to direct disk resolution with directory traversal prevention
        abs_target = os.path.abspath(target_path)
        data_root = os.path.abspath(os.path.join(PROJECT_ROOT, "data"))
        project_root_abs = os.path.abspath(PROJECT_ROOT)

        # Enforce that served file resides within the authorized project data directory
        if not abs_target.startswith(data_root) and not abs_target.startswith(project_root_abs):
            logger.warning(f"Prevented access to out-of-bounds file path: {target_path}")
            return jsonify({
                "status": "error",
                "error_code": "FORBIDDEN_FILE_ACCESS",
                "message": "Access denied: Image path is outside authorized data directory.",
            }), 403

        if not os.path.exists(abs_target):
            return jsonify({
                "status": "error",
                "error_code": "IMAGE_FILE_NOT_FOUND",
                "message": "Image file does not exist on disk.",
            }), 404

        return send_file(abs_target)

    @app.route("/api/inspections/<int:inspection_id>/activity", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN)
    def api_get_inspection_activity_route(inspection_id: int):
        """
        Retrieves chronological maintenance activity history for an inspection record.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        record = get_inspection_by_id(inspection_id, db_path=db_path)
        if not record:
            return jsonify({
                "status": "error",
                "error_code": "INSPECTION_NOT_FOUND",
                "message": f"Inspection record #{inspection_id} not found.",
            }), 404

        curr_user = get_current_user_record()
        if curr_user and curr_user["role"] == ROLE_CITIZEN:
            created_by = record.get("created_by_user_id")
            if created_by is None or int(created_by) != int(curr_user["id"]):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_REPORT_ACCESS",
                    "message": "Access denied: Citizens may only view activity history for their own inspection records.",
                }), 403

        activities = get_inspection_activity(inspection_id, db_path=db_path)

        # Phase 5: Privacy Guardrail - Mask internal staff data for citizens
        if curr_user and curr_user["role"] == ROLE_CITIZEN:
            sanitized_activities = []
            for act in activities:
                sa = dict(act)
                sa["user_id"] = None
                sa["username"] = "Operations Team"
                if sa.get("action_type") in ("assigned", "reassigned", "assignment_cancelled"):
                    sa["notes"] = "Remediation crew dispatched for inspection and maintenance scheduling."
                sanitized_activities.append(sa)
            activities = sanitized_activities

        return jsonify({
            "status": "success",
            "inspection_id": inspection_id,
            "count": len(activities),
            "activities": activities,
        }), 200

    # -------------------------------------------------------------------------
    # Report & Export Routes (Phase 4.5 & Phase 4.6 Authorization)
    # -------------------------------------------------------------------------
    @app.route("/api/reports/preview", methods=["GET"])
    @app.route("/api/reports/data", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR)
    def api_get_report_preview():
        """
        Generates and returns JSON report data according to validated filters.
        Used by the client-side report preview interface.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        is_valid, norm_filters, err_msg = validate_report_filters(request.args.to_dict())
        if not is_valid:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_REPORT_FILTERS",
                "message": err_msg or "Invalid report filters provided.",
            }), 400

        try:
            report_data = generate_report_data(norm_filters, db_path=db_path)
            return jsonify({
                "status": "success",
                "report": report_data,
            }), 200
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_REPORT_FILTERS",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to generate report preview: {e}")
            return jsonify({
                "status": "error",
                "error_code": "REPORT_GENERATION_FAILED",
                "message": f"Report generation failed: {str(e)}",
            }), 500

    @app.route("/api/reports/export/csv", methods=["GET"])
    @app.route("/api/reports/csv", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR)
    def api_export_report_csv():
        """
        Exports filtered inspection records as an Excel-compatible CSV (UTF-8 BOM).
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        is_valid, norm_filters, err_msg = validate_report_filters(request.args.to_dict())
        if not is_valid:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_REPORT_FILTERS",
                "message": err_msg or "Invalid report filters provided.",
            }), 400

        try:
            report_data = generate_report_data(norm_filters, db_path=db_path)
            csv_content = generate_report_csv(report_data)

            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"visionguard_report_{timestamp_str}.csv"

            byte_stream = io.BytesIO(csv_content.encode("utf-8"))
            return send_file(
                byte_stream,
                mimetype="text/csv",
                as_attachment=True,
                download_name=filename,
            )
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_REPORT_FILTERS",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to export CSV report: {e}")
            return jsonify({
                "status": "error",
                "error_code": "CSV_EXPORT_FAILED",
                "message": f"CSV export failed: {str(e)}",
            }), 500

    @app.route("/api/reports/export/pdf", methods=["GET"])
    @app.route("/api/reports/pdf", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR)
    def api_export_report_pdf():
        """
        Exports a professional, printable PDF inspection report.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        is_valid, norm_filters, err_msg = validate_report_filters(request.args.to_dict())
        if not is_valid:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_REPORT_FILTERS",
                "message": err_msg or "Invalid report filters provided.",
            }), 400

        try:
            report_data = generate_report_data(norm_filters, db_path=db_path)
            pdf_bytes = generate_report_pdf(report_data)

            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"visionguard_report_{timestamp_str}.pdf"

            byte_stream = io.BytesIO(pdf_bytes)
            return send_file(
                byte_stream,
                mimetype="application/pdf",
                as_attachment=True,
                download_name=filename,
            )
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "INVALID_REPORT_FILTERS",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to export PDF report: {e}")
            return jsonify({
                "status": "error",
                "error_code": "PDF_EXPORT_FAILED",
                "message": f"PDF export failed: {str(e)}",
            }), 500

    # -------------------------------------------------------------------------
    # Civic Complaint Assistance Routes
    # -------------------------------------------------------------------------
    @app.route("/api/inspections/<int:inspection_id>/complaint-draft", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN)
    def api_get_complaint_draft(inspection_id: int):
        """
        Retrieves the editable civic complaint draft for an inspection.
        Generates default draft from inspection telemetry if not already created.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        curr_user = get_current_user_record()
        if curr_user and curr_user["role"] == ROLE_CITIZEN:
            rec = get_inspection_by_id(inspection_id, db_path=db_path)
            if not rec:
                return jsonify({
                    "status": "error",
                    "error_code": "INSPECTION_NOT_FOUND",
                    "message": f"Inspection #{inspection_id} not found.",
                }), 404
            created_by = rec.get("created_by_user_id")
            if created_by is None or int(created_by) != int(curr_user["id"]):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_REPORT_ACCESS",
                    "message": "Access denied: Citizens may only access complaint drafts for their own inspections.",
                }), 403

        u_id = curr_user["id"] if curr_user else None
        u_name = curr_user["username"] if curr_user else None

        try:
            draft = get_or_create_complaint_draft(
                inspection_id=inspection_id,
                user_id=u_id,
                username=u_name,
                db_path=db_path
            )
            return jsonify({
                "status": "success",
                "draft": draft,
                "disclaimer": COMPLAINT_DISCLAIMER_TEXT,
            }), 200
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "INSPECTION_NOT_FOUND",
                "message": str(ve),
            }), 404
        except Exception as e:
            logger.exception(f"Failed to retrieve complaint draft for inspection #{inspection_id}: {e}")
            return jsonify({
                "status": "error",
                "error_code": "COMPLAINT_DRAFT_FAILED",
                "message": f"Could not load complaint draft: {str(e)}",
            }), 500

    @app.route("/api/inspections/<int:inspection_id>/complaint-draft", methods=["PUT", "PATCH"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_CITIZEN)
    def api_update_complaint_draft(inspection_id: int):
        """
        Updates an editable civic complaint draft.
        Enforces that status can only be 'draft' or 'exported' — never 'submitted'.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        payload = request.get_json(silent=True) or {}
        curr_user = get_current_user_record()
        if curr_user and curr_user["role"] == ROLE_CITIZEN:
            rec = get_inspection_by_id(inspection_id, db_path=db_path)
            if not rec:
                return jsonify({
                    "status": "error",
                    "error_code": "INSPECTION_NOT_FOUND",
                    "message": f"Inspection #{inspection_id} not found.",
                }), 404
            created_by = rec.get("created_by_user_id")
            if created_by is None or int(created_by) != int(curr_user["id"]):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_REPORT_ACCESS",
                    "message": "Access denied: Citizens may only edit complaint drafts for their own inspections.",
                }), 403

        u_id = curr_user["id"] if curr_user else None
        u_name = curr_user["username"] if curr_user else None

        try:
            updated = update_complaint_draft(
                inspection_id=inspection_id,
                updates=payload,
                user_id=u_id,
                username=u_name,
                db_path=db_path
            )
            return jsonify({
                "status": "success",
                "message": "Complaint draft saved successfully.",
                "draft": updated,
            }), 200
        except ValueError as ve:
            return jsonify({
                "status": "error",
                "error_code": "VALIDATION_FAILED",
                "message": str(ve),
            }), 400
        except Exception as e:
            logger.exception(f"Failed to update complaint draft for inspection #{inspection_id}: {e}")
            return jsonify({
                "status": "error",
                "error_code": "UPDATE_FAILED",
                "message": f"Failed to save complaint draft: {str(e)}",
            }), 500

    @app.route("/api/inspections/<int:inspection_id>/complaint-draft/export/txt", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN)
    def api_export_complaint_draft_txt(inspection_id: int):
        """
        Exports the complaint draft as a plain text document.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        curr_user = get_current_user_record()
        if curr_user and curr_user["role"] == ROLE_CITIZEN:
            rec = get_inspection_by_id(inspection_id, db_path=db_path)
            if not rec:
                return jsonify({
                    "status": "error",
                    "error_code": "INSPECTION_NOT_FOUND",
                    "message": f"Inspection #{inspection_id} not found.",
                }), 404
            created_by = rec.get("created_by_user_id")
            if created_by is None or int(created_by) != int(curr_user["id"]):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_REPORT_ACCESS",
                    "message": "Access denied: Citizens may only export complaint drafts for their own inspections.",
                }), 403

        try:
            draft = get_or_create_complaint_draft(inspection_id=inspection_id, db_path=db_path)
            # Mark status as exported only if not already ready_to_submit or submitted
            if draft.get("status") not in ("submitted", "ready_to_submit"):
                update_complaint_draft(inspection_id, {"status": "exported"}, db_path=db_path)

            filename = f"visionguard_complaint_draft_insp_{inspection_id}.txt"
            status_val = str(draft.get("status", "draft")).upper().replace("_", " ")
            complainant_val = draft.get("complainant_name") or "Not Specified"
            contact_val = draft.get("complainant_contact") or "Not Specified"
            location_val = draft.get("inspection_location") or "Not Specified"

            header_lines = [
                "VISIONGUARD AI — CIVIC COMPLAINT & GRIEVANCE RECORD",
                f"STATUS: {status_val}",
            ]
            if draft.get("status") == "submitted":
                header_lines.append(f"SUBMITTED VIA: {draft.get('submission_channel', 'Manual Submission')}")
                header_lines.append(f"OFFICIAL REFERENCE: {draft.get('submission_reference', 'Self-Reported')}")
                header_lines.append(f"SUBMISSION TIMESTAMP: {draft.get('submitted_at', '')}")

            header_lines.extend([
                f"COMPLAINANT: {complainant_val} (Contact: {contact_val})",
                f"CONFIRMED LOCATION: {location_val}",
                f"{'='*72}",
                f"TO: {draft.get('recipient_agency')}",
                f"SUBJECT: {draft.get('subject')}",
                f"{'='*72}\n",
                draft.get("complaint_body", ""),
            ])
            content = "\n".join(header_lines)
            byte_stream = io.BytesIO(content.encode("utf-8"))
            return send_file(
                byte_stream,
                mimetype="text/plain",
                as_attachment=True,
                download_name=filename,
            )
        except ValueError as ve:
            return jsonify({"status": "error", "message": str(ve)}), 404
        except Exception as e:
            logger.exception(f"Failed to export TXT complaint draft: {e}")
            return jsonify({"status": "error", "message": f"Export failed: {str(e)}"}), 500

    @app.route("/api/inspections/<int:inspection_id>/complaint-draft/export/pdf", methods=["GET"])
    @roles_required(ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN)
    def api_export_complaint_draft_pdf(inspection_id: int):
        """
        Exports the complaint draft as a printable PDF with legal draft disclaimer.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        curr_user = get_current_user_record()
        if curr_user and curr_user["role"] == ROLE_CITIZEN:
            rec = get_inspection_by_id(inspection_id, db_path=db_path)
            if not rec:
                return jsonify({
                    "status": "error",
                    "error_code": "INSPECTION_NOT_FOUND",
                    "message": f"Inspection #{inspection_id} not found.",
                }), 404
            created_by_id = rec.get("created_by_user_id")
            created_by_name = rec.get("created_by_username")
            u_id = curr_user.get("id")
            u_name = curr_user.get("username")
            id_match = (created_by_id is not None and u_id is not None and int(created_by_id) == int(u_id))
            name_match = (created_by_name and u_name and str(created_by_name).lower() == str(u_name).lower())
            if not (id_match or name_match):
                return jsonify({
                    "status": "error",
                    "error_code": "FORBIDDEN_REPORT_ACCESS",
                    "message": "Access denied: Citizens may only export complaint drafts for their own inspections.",
                }), 403

        try:
            pdf_bytes = export_complaint_draft_pdf(inspection_id=inspection_id, db_path=db_path)
            filename = f"visionguard_complaint_draft_insp_{inspection_id}.pdf"
            byte_stream = io.BytesIO(pdf_bytes)
            gc.collect()
            return send_file(
                byte_stream,
                mimetype="application/pdf",
                as_attachment=True,
                download_name=filename,
            )
        except ValueError as ve:
            return jsonify({"status": "error", "message": str(ve)}), 404
        except Exception as e:
            logger.exception(f"Failed to export PDF complaint draft: {e}")
            return jsonify({
                "status": "error",
                "error_code": "PDF_EXPORT_FAILED",
                "message": f"Failed to export complaint draft PDF: {str(e)}",
            }), 500

    @app.route("/api/citizen/summary", methods=["GET"])
    @roles_required(ROLE_CITIZEN)
    def api_get_citizen_summary():
        """
        Returns authentic summary metrics (total, open, under_review, resolved, submitted_complaints)
        for the authenticated citizen.
        """
        db_path = app.config.get("DATABASE_PATH", DEFAULT_DB_PATH)
        curr_user = get_current_user_record()
        if not curr_user:
            return jsonify({"status": "error", "message": "Authentication required."}), 401
        summary = get_citizen_dashboard_summary(curr_user["id"], username=curr_user.get("username"), db_path=db_path)
        return jsonify({
            "status": "success",
            "summary": summary
        }), 200

    return app


# Module-level application instance for WSGI servers / flask run
app = create_app()

if __name__ == "__main__":
    host = os.environ.get("VISIONGUARD_HOST", "127.0.0.1")
    port = int(os.environ.get("VISIONGUARD_PORT", os.environ.get("PORT", "5000")))
    debug_mode = (not app.config.get("PRODUCTION", False)) and (os.environ.get("VISIONGUARD_DEBUG", "0") == "1")
    app.run(host=host, port=port, debug=debug_mode)

