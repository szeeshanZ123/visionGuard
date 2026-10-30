"""
VisionGuard AI 2.0 — Google Gemini Multimodal Vision Service.

Provides structured, multimodal infrastructure and building defect detection,
preliminary severity analysis, safety guidance, and coordinate normalization.

Architecture: "VisionGuard Multimodal AI — Powered by Google Gemini Vision"
"""

import os
import re
import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("visionguard.gemini")

# Official Google Gen AI SDK
try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    APIError = Exception
    GENAI_AVAILABLE = False

# Default configurable image-capable model eligible for Google AI Studio free tier
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
FALLBACK_GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-2.5-flash",
]
FALLBACK_GEMINI_MODEL = "gemini-flash-latest"

# Standard distress categories
ROAD_DEFECT_TYPES = {
    "pothole": "Pothole",
    "longitudinal_crack": "Longitudinal Crack",
    "transverse_crack": "Transverse Crack",
    "alligator_crack": "Alligator Cracking",
    "surface_deterioration": "Surface Deterioration",
    "rutting": "Road Rutting / Depression",
    "raveling": "Asphalt Raveling",
    "other_road_damage": "Road Surface Damage",
}

BUILDING_DEFECT_TYPES = {
    "wall_crack": "Wall Structural Crack",
    "dampness_water_damage": "Dampness & Water Infiltration",
    "peeling_paint": "Peeling / Blistered Paint",
    "plaster_damage": "Plaster Spalling / Detachment",
    "surface_spalling": "Concrete / Surface Spalling",
    "efflorescence": "Efflorescence / Salt Leaching",
    "other_building_defect": "Surface / Structural Distress",
}

VALID_SEVERITIES = {"low", "moderate", "high", "critical", "uncertain"}


class GeminiInspectionService:
    """
    Multimodal defect inspection service powered by Google Gemini Vision.
    Analyzes road and building photographs, normalizes candidate defect bounding
    boxes, and generates structured inspection reports.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self._explicit_key = api_key
        self._model_name = (model_name or "").strip()
        self._client: Optional[Any] = None
        self._cached_client_key: Optional[str] = None

    @property
    def api_key(self) -> Optional[str]:
        raw = (
            self._explicit_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GOOGLE_GENAI_API_KEY")
            or os.environ.get("GEMINI_KEY")
        )
        if raw is not None:
            cleaned = str(raw).strip().strip("'\"").strip()
            if len(cleaned) > 5:
                return cleaned
        return None

    @property
    def model_name(self) -> str:
        # Dynamically read GEMINI_MODEL from container environment
        env_model = os.environ.get("GEMINI_MODEL", "").strip().strip("'\"").strip()
        return env_model or self._model_name or DEFAULT_GEMINI_MODEL

    def is_configured(self) -> bool:
        """Returns True if the Google Gen AI SDK is installed and an API key is available."""
        return bool(GENAI_AVAILABLE and self.api_key)

    def get_configuration_diagnostics(self) -> Dict[str, Any]:
        """
        Returns safe environment and SDK diagnostics without exposing any secret keys.
        """
        key = self.api_key
        key_present = bool(key is not None)
        masked_preview = (
            f"{key[:6]}...{key[-2:]}" if key_present and len(key) > 8 else None
        )
        env_source = "none"
        if self._explicit_key:
            env_source = "explicit_parameter"
        elif os.environ.get("GEMINI_API_KEY"):
            env_source = "GEMINI_API_KEY"
        elif os.environ.get("GOOGLE_API_KEY"):
            env_source = "GOOGLE_API_KEY"
        elif os.environ.get("GOOGLE_GENAI_API_KEY"):
            env_source = "GOOGLE_GENAI_API_KEY"
        elif os.environ.get("GEMINI_KEY"):
            env_source = "GEMINI_KEY"

        return {
            "sdk_installed": GENAI_AVAILABLE,
            "api_key_configured": key_present,
            "environment_source": env_source,
            "key_masked": masked_preview,
            "configured_model": self.model_name,
            "fallback_models": FALLBACK_GEMINI_MODELS,
        }

    def get_client(self) -> Any:
        """Initializes or returns the thread-safe genai.Client instance."""
        if not GENAI_AVAILABLE:
            raise RuntimeError("The 'google-genai' SDK is not installed in the environment.")
        key = self.api_key
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Please set the GEMINI_API_KEY environment variable "
                "in your deployment environment (e.g. Render Dashboard -> Environment Variables) or .env file."
            )
        if self._client is None or self._cached_client_key != key:
            self._client = genai.Client(api_key=key)
            self._cached_client_key = key
        return self._client

    def _build_prompt(self, domain: str) -> str:
        """Constructs domain-specific system instruction and schema prompt."""
        is_road = (domain == "road")
        target_entity = "roadway surface, street, asphalt, or pavement" if is_road else "building facade, interior/exterior wall, ceiling, or structural element"
        classes_desc = (
            "Road distress types: pothole, longitudinal_crack, transverse_crack, alligator_crack, "
            "surface_deterioration, rutting, raveling, other_road_damage."
            if is_road else
            "Building defect types: wall_crack, dampness_water_damage, peeling_paint, plaster_damage, "
            "surface_spalling, efflorescence, other_building_defect."
        )

        return f"""You are VisionGuard AI, an expert multimodal civil infrastructure defect inspector.
Analyze this photograph of a {target_entity} carefully and identify visible structural and surface defects.

Primary distress types to identify:
{classes_desc}

INSPECTION RULES:
1. Examine the image thoroughly for any and all visible defects (multiple defects can exist in one image).
2. For each detected defect, provide its localized bounding box in NORMALIZED coordinates:
   - x1: Left edge (0.0 to 1.0)
   - y1: Top edge (0.0 to 1.0)
   - x2: Right edge (0.0 to 1.0)
   - y2: Bottom edge (0.0 to 1.0)
   Ensure 0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0.
   If a defect is clearly visible but exact spatial boundaries cannot be localized, omit bounding_box or set it to null.
3. Assign a preliminary severity rating: "low", "moderate", "high", "critical", or "uncertain".
4. If the photograph shows an undamaged, clean surface with NO visible defects, return an empty defects list and status="none_detected".
5. If the photograph is too blurry, dark, corrupt, or irrelevant to infrastructure/buildings, set status="unclear_image" with an explanatory summary.
6. Do NOT fabricate defects, costs, or structural engineering certifications.
7. Return ONLY valid JSON adhering exactly to the following JSON schema:

{{
  "status": "identified" | "none_detected" | "unclear_image",
  "domain": "{domain}",
  "defects": [
    {{
      "id": "D001",
      "type": "pothole | longitudinal_crack | transverse_crack | alligator_crack | surface_deterioration | wall_crack | dampness_water_damage | peeling_paint | plaster_damage | surface_spalling | other",
      "title": "Short descriptive title (e.g. Deep Pothole)",
      "description": "Clear description of observed damage",
      "bounding_box": {{
        "x1": 0.15,
        "y1": 0.25,
        "x2": 0.45,
        "y2": 0.65
      }},
      "severity": "low | moderate | high | critical | uncertain",
      "evidence": "Specific visual evidence (e.g. Broken asphalt edges with visible void cavity)",
      "recommended_action": "Recommended maintenance or remediation step",
      "maintenance_priority": "Immediate Emergency | High Priority (48h) | Scheduled Maintenance (14d) | Routine Monitoring",
      "safety_guidance": "Safety warning and precaution for citizens / pedestrians / drivers",
      "why_problem": "Why this defect is hazardous or leads to further deterioration",
      "inspection_points": "Key points for on-site municipal or engineering team to verify"
    }}
  ],
  "summary": "Overall visual summary of inspection findings",
  "preliminary_severity": "low | moderate | high | critical | uncertain",
  "requires_human_review": true,
  "safety_precautions": [
    "General caution or precautionary recommendation"
  ]
}}"""

    def analyze_image(
        self,
        image_bytes: bytes,
        domain: str = "road",
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Executes Gemini Vision multimodal analysis on the uploaded image.
        Returns validated, structured inspection and defect detection results.
        """
        domain_norm = "home" if str(domain).lower().strip() in ("home", "building") else "road"
        t0 = time.perf_counter()

        # Check configuration
        if not self.is_configured():
            return {
                "status": "error",
                "error_code": "GEMINI_NOT_CONFIGURED",
                "message": (
                    "Google Gemini Vision API key is not configured on the server. "
                    "Please set the GEMINI_API_KEY environment variable in your .env file "
                    "or cloud deployment environment."
                ),
                "setup_guide": "Get a free API key at https://aistudio.google.com/ and configure GEMINI_API_KEY.",
            }

        # Support file path string or raw bytes
        if isinstance(image_bytes, str):
            with open(image_bytes, "rb") as f:
                image_bytes = f.read()

        client = self.get_client()
        prompt_text = self._build_prompt(domain_norm)

        part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        )

        model_to_use = self._model_name
        response_text = ""

        try:
            # Execute Gemini Vision call
            t_call = time.perf_counter()
            response = client.models.generate_content(
                model=model_to_use,
                contents=[part, prompt_text],
                config=config,
            )
            gemini_duration_ms = (time.perf_counter() - t_call) * 1000
            response_text = response.text or ""
            logger.info("Gemini Vision (%s) response received in %.1fms (%d chars)", model_to_use, gemini_duration_ms, len(response_text))

        except Exception as exc:
            err_str = str(exc)
            logger.warning("Gemini Vision call failed with model %s: %s", model_to_use, err_str)

            # Check for quota exhaustion / rate limits
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str.upper() or "quota" in err_str.lower():
                return {
                    "status": "error",
                    "error_code": "QUOTA_EXHAUSTED",
                    "message": (
                        "Google Gemini Vision free-tier rate limit reached. "
                        "Please wait a few seconds and try again, or check your quota in Google AI Studio."
                    ),
                    "details": err_str,
                }
            # Check for invalid API key
            if "API_KEY_INVALID" in err_str or "401" in err_str or "permission" in err_str.lower():
                return {
                    "status": "error",
                    "error_code": "INVALID_API_KEY",
                    "message": "The configured GEMINI_API_KEY was rejected by Google AI Studio. Please verify your API key.",
                    "details": err_str,
                }

            # Check for model not found / deprecated / high demand -> try candidate fallback models
            last_err = err_str
            for alt_model in FALLBACK_GEMINI_MODELS:
                if alt_model == model_to_use:
                    continue
                try:
                    logger.info("Retrying Gemini Vision call with fallback model %s...", alt_model)
                    response = client.models.generate_content(
                        model=alt_model,
                        contents=[part, prompt_text],
                        config=config,
                    )
                    response_text = response.text or ""
                    model_to_use = alt_model
                    logger.info("Fallback model %s succeeded (%d chars)", alt_model, len(response_text))
                    break
                except Exception as fb_exc:
                    last_err = str(fb_exc)
                    logger.warning("Fallback model %s failed: %s", alt_model, last_err[:120])
                    continue

            if not response_text:
                return {
                    "status": "error",
                    "error_code": "GEMINI_API_ERROR",
                    "message": f"Gemini Vision API request failed: {last_err}",
                    "details": last_err,
                }

        # Parse JSON response
        parsed = self._clean_and_parse_json(response_text)
        if not parsed:
            logger.error("Failed to parse JSON response from Gemini Vision: %s", response_text[:300])
            return {
                "status": "error",
                "error_code": "INVALID_RESPONSE_FORMAT",
                "message": "VisionGuard AI received an unparseable response from Gemini Vision. Please retry.",
                "raw_preview": response_text[:200],
            }

        # Normalize and validate parsed defect detections
        validated_result = self._validate_and_normalize_result(parsed, domain_norm)
        validated_result["provider"] = "google_gemini"
        validated_result["model_used"] = model_to_use
        validated_result["analysis_duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        return validated_result

    def _clean_and_parse_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Safely extracts and parses JSON even if markdown code fences are present."""
        if not raw_text or not raw_text.strip():
            return None

        text = raw_text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: locate outermost { and }
            m = re.search(r"(\{.*\})", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
        return None

    def _validate_and_normalize_result(self, data: Dict[str, Any], domain: str) -> Dict[str, Any]:
        """
        Validates structure, enforces normalized bounding box coordinates [0, 1],
        and prepares unified defect list and report summary.
        """
        raw_status = str(data.get("status", "identified")).lower().strip()
        if raw_status not in ("identified", "none_detected", "unclear_image"):
            raw_status = "identified"

        raw_defects = data.get("defects", [])
        if not isinstance(raw_defects, list):
            raw_defects = []

        validated_defects = []
        for idx, item in enumerate(raw_defects, start=1):
            if not isinstance(item, dict):
                continue

            defect_id = str(item.get("id") or f"D{idx:03d}").strip().upper()
            raw_type = str(item.get("type") or "defect").strip().lower().replace(" ", "_")
            
            # Map friendly title
            type_lookup = ROAD_DEFECT_TYPES if domain == "road" else BUILDING_DEFECT_TYPES
            title = str(item.get("title") or type_lookup.get(raw_type) or raw_type.replace("_", " ").title()).strip()

            raw_severity = str(item.get("severity") or "moderate").strip().lower()
            severity = raw_severity if raw_severity in VALID_SEVERITIES else "moderate"

            # Validate bounding box coordinates
            box, box_valid = self._normalize_bounding_box(item.get("bounding_box"))

            description = str(item.get("description") or f"Identified {title.lower()} on surface.").strip()
            evidence = str(item.get("evidence") or "Surface distress detected via Gemini Vision.").strip()
            action = str(item.get("recommended_action") or "Schedule visual verification.").strip()
            priority = str(item.get("maintenance_priority") or "Scheduled Maintenance (14d)").strip()
            safety = str(item.get("safety_guidance") or "Exercise caution around visible distress.").strip()
            why_problem = str(item.get("why_problem") or "Distress may deteriorate under weather and mechanical stress.").strip()
            inspection_points = str(item.get("inspection_points") or "Inspect depth, perimeter extension, and subgrade/wall adhesion.").strip()

            # Backwards-compatible detection entry for existing downstream modules
            conf_val = 0.88 if severity in ("critical", "high") else (0.78 if severity == "moderate" else 0.68)
            det_entry = {
                "id": defect_id,
                "defect_id": defect_id,
                "type": raw_type,
                "title": title,
                "label": title,
                "class_name": raw_type,
                "display_name": f"{defect_id}: {title}",
                "description": description,
                "severity": severity,
                "confidence": conf_val,
                "evidence": evidence,
                "recommended_action": action,
                "maintenance_priority": priority,
                "safety_guidance": safety,
                "why_problem": why_problem,
                "inspection_points": inspection_points,
                "bounding_box": box if box_valid else None,
                "box_2d": box if box_valid else None,
                "has_bounding_box": box_valid,
                "localization_uncertain": not box_valid,
            }

            # Add pixel box placeholder (filled downstream once image dimensions are known)
            if box_valid:
                det_entry["normalized_box"] = box

            validated_defects.append(det_entry)

        # Re-check status if no defects were found
        if not validated_defects and raw_status == "identified":
            raw_status = "none_detected"

        overall_severity = str(data.get("preliminary_severity") or "uncertain").strip().lower()
        if overall_severity not in VALID_SEVERITIES:
            if validated_defects:
                severities = [d["severity"] for d in validated_defects]
                if "critical" in severities:
                    overall_severity = "critical"
                elif "high" in severities:
                    overall_severity = "high"
                elif "moderate" in severities:
                    overall_severity = "moderate"
                else:
                    overall_severity = "low"
            else:
                overall_severity = "low" if raw_status == "none_detected" else "uncertain"

        summary = str(data.get("summary") or "").strip()
        if not summary:
            if raw_status == "none_detected":
                summary = "Preliminary inspection identified no visible structural or roadway defects. Surface appears intact."
            elif raw_status == "unclear_image":
                summary = "The provided photograph is unclear or lacks sufficient resolution for definitive defect assessment."
            else:
                summary = f"Visual inspection identified {len(validated_defects)} candidate defect(s) requiring maintenance review."

        precautions = data.get("safety_precautions")
        if not isinstance(precautions, list) or not precautions:
            precautions = [
                "Preliminary visual assessment only — not a certified structural engineering report.",
                "Maintain safe distance from deteriorated surfaces or pavement depressions.",
                "Report severe road cave-ins or wall cracks immediately to municipal emergency services."
            ]

        return {
            "status": "success",
            "inspection_status": raw_status,
            "domain": domain,
            "defects": validated_defects,
            "defect_count": len(validated_defects),
            "summary": summary,
            "preliminary_severity": overall_severity,
            "requires_human_review": True,
            "safety_precautions": precautions,
            "disclaimer": (
                "VisionGuard Multimodal AI — Preliminary visual assessment generated by Google Gemini Vision. "
                "This assessment does not constitute a certified structural engineering inspection or municipal warranty."
            ),
        }

    def _normalize_bounding_box(self, raw_box: Any) -> Tuple[Optional[Dict[str, float]], bool]:
        """
        Validates and normalizes coordinates into {"x1": float, "y1": float, "x2": float, "y2": float}
        with strict [0.0, 1.0] range checks and positive dimensions.
        """
        if not raw_box:
            return None, False

        x1 = y1 = x2 = y2 = None

        # Format 1: dict with x1, y1, x2, y2
        if isinstance(raw_box, dict):
            if all(k in raw_box for k in ("x1", "y1", "x2", "y2")):
                try:
                    x1 = float(raw_box["x1"])
                    y1 = float(raw_box["y1"])
                    x2 = float(raw_box["x2"])
                    y2 = float(raw_box["y2"])
                except (ValueError, TypeError):
                    return None, False
            # Format 2: box_2d [ymin, xmin, ymax, xmax] (Google standard)
            elif "box_2d" in raw_box and isinstance(raw_box["box_2d"], (list, tuple)) and len(raw_box["box_2d"]) == 4:
                try:
                    ymin, xmin, ymax, xmax = [float(v) for v in raw_box["box_2d"]]
                    # If returned in 0-1000 range (standard Gemini bounding box format)
                    if any(v > 1.0 for v in (ymin, xmin, ymax, xmax)):
                        ymin, xmin, ymax, xmax = ymin / 1000.0, xmin / 1000.0, ymax / 1000.0, xmax / 1000.0
                    x1, y1, x2, y2 = xmin, ymin, xmax, ymax
                except (ValueError, TypeError):
                    return None, False

        # Format 3: list [x1, y1, x2, y2]
        elif isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
            try:
                vals = [float(v) for v in raw_box]
                if any(v > 1.0 for v in vals):
                    vals = [v / 1000.0 for v in vals]
                x1, y1, x2, y2 = vals[0], vals[1], vals[2], vals[3]
            except (ValueError, TypeError):
                return None, False

        if None in (x1, y1, x2, y2):
            return None, False

        # Ensure order (x1 < x2, y1 < y2)
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        # Clamp strictly to [0.0, 1.0]
        x1 = max(0.0, min(1.0, x1))
        y1 = max(0.0, min(1.0, y1))
        x2 = max(0.0, min(1.0, x2))
        y2 = max(0.0, min(1.0, y2))

        # Degenerate box check (must have positive area > 0.005 on both dimensions)
        if (x2 - x1) < 0.005 or (y2 - y1) < 0.005:
            return None, False

        return {
            "x1": round(x1, 4),
            "y1": round(y1, 4),
            "x2": round(x2, 4),
            "y2": round(y2, 4),
        }, True

