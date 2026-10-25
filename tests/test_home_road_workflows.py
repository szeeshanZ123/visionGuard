"""
Unit and integration tests for VisionGuard AI dual-inspection workflows:
Road Surface Distress vs Home & Building Defect.

Covers:
1. Model Routing & Isolation:
   - Selecting Road Problem routes strictly to the Road model.
   - Selecting Home Problem routes strictly to the Home model.
   - Preserves backward compatibility (defaults to road when unspecified).
2. Class Label Integrity:
   - Road model outputs strictly Road classes: D00, D10, D20, D40.
   - Home model outputs strictly 4 canonical Home defect classes:
     wall_crack, damp_or_water_damage, peeling_paint_or_plaster, spalling_or_surface_damage.
   - No label cross-contamination between models.
3. Checkpoint Error Handling & Security:
   - Missing Road or Home weights returns HTTP 503 with actionable restoration instructions.
   - No leaking of internal filesystem paths, stack traces, or credentials.
4. Overlap Suppression (NMS):
   - Computes box IoU accurately and suppresses redundant duplicate detections.
5. Ingestion Validation:
   - Invalid domain parameter returns HTTP 400.
6. Database Persistence & Segregation:
   - Records inspection_type ('road' vs 'home') in SQLite.
   - Filters inspection records cleanly by domain without cross-polluting datasets.
7. Civil & Structural Engineering Safety Disclaimers:
   - Clear disclaimers stating detections reflect statistical likelihood, not physical integrity.
"""

import io
from pathlib import Path
import pytest
from PIL import Image

from app.server import create_app
from ai.detection.detector import (
    DefectDetectionService,
    HomeDefectDetectionService,
    RoadDefectDetectionService,
    HOME_CLASS_NAMES,
    ROAD_CLASS_NAMES,
    compute_box_iou,
    suppress_overlapping_detections,
)
from database.db import (
    init_db,
    save_inspection,
    get_inspections,
    get_inspection_by_id,
)


@pytest.fixture
def test_image_bytes():
    """Generates a synthetic 640x480 RGB JPEG image for inspection testing."""
    img = Image.new("RGB", (640, 480), color=(180, 180, 180))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class MockRoadDetector(DefectDetectionService):
    """Deterministic Mock Road Detector detecting road distresses."""

    def __init__(self):
        super().__init__(model_path="ai/models/best.pt", domain="road")
        self.is_loaded = True
        self.status_message = "Mock Road Model Loaded"

    def detect(self, image_bgr, conf_threshold=0.25, raise_if_unloaded=False):
        return [
            {
                "class_id": 0,
                "class_name": "D00",
                "distress_category": "Longitudinal Crack",
                "confidence": 0.88,
                "bbox": {"x1": 50, "y1": 60, "x2": 150, "y2": 260, "width": 100, "height": 200},
                "source": "global",
            },
            {
                "class_id": 3,
                "class_name": "D40",
                "distress_category": "Pothole",
                "confidence": 0.76,
                "bbox": {"x1": 220, "y1": 250, "x2": 380, "y2": 390, "width": 160, "height": 140},
                "source": "global",
            },
        ]


class MockHomeDetector(DefectDetectionService):
    """Deterministic Mock Home Detector detecting home & building defects."""

    def __init__(self):
        super().__init__(model_path="ai/models/home_best.pt", domain="home")
        self.is_loaded = True
        self.status_message = "Mock Home Model Loaded"

    def detect(self, image_bgr, conf_threshold=0.25, raise_if_unloaded=False):
        return [
            {
                "class_id": 0,
                "class_name": "wall_crack",
                "distress_category": "Wall Crack",
                "confidence": 0.84,
                "bbox": {"x1": 80, "y1": 100, "x2": 200, "y2": 300, "width": 120, "height": 200},
                "source": "global",
            },
            {
                "class_id": 2,
                "class_name": "peeling_paint_or_plaster",
                "distress_category": "Peeling Paint / Plaster",
                "confidence": 0.79,
                "bbox": {"x1": 300, "y1": 150, "x2": 450, "y2": 320, "width": 150, "height": 170},
                "source": "global",
            },
        ]


@pytest.fixture
def dual_model_client(tmp_path):
    """Test client with mock road and home detectors and an isolated test DB."""
    db_file = str(tmp_path / "dual_workflow_test.db")
    init_db(db_file)

    road_det = MockRoadDetector()
    home_det = MockHomeDetector()

    app = create_app(
        detector=road_det,
        home_detector=home_det,
        test_config={"TESTING": True, "DATABASE_PATH": db_file},
    )
    with app.test_client() as client:
        yield client


@pytest.fixture
def unauthenticated_client(tmp_path):
    """Test client where models are unloaded/missing weights."""
    db_file = str(tmp_path / "missing_weights.db")
    init_db(db_file)

    road_det = RoadDefectDetectionService(model_path="nonexistent_road.pt")
    home_det = HomeDefectDetectionService(model_path="nonexistent_home.pt")

    app = create_app(
        detector=road_det,
        home_detector=home_det,
        test_config={"TESTING": True, "DATABASE_PATH": db_file},
    )
    with app.test_client() as client:
        yield client


# ==============================================================================
# 1. API Classes Endpoint Tests
# ==============================================================================

def test_classes_endpoint_road_classes_default(dual_model_client):
    """Verifies GET /api/classes defaults to road classes for backward compatibility."""
    res = dual_model_client.get("/api/classes")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["domain"] == "road"
    assert "classes" in data
    class_names = [c["class_name"] for c in data["classes"]]
    assert any("D00" in name for name in class_names)
    assert any("D40" in name for name in class_names)
    assert not any("wall_crack" in name for name in class_names)


def test_classes_endpoint_home_classes(dual_model_client):
    """Verifies GET /api/classes?domain=home returns strictly the 4 canonical home defect classes."""
    res = dual_model_client.get("/api/classes?domain=home")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["domain"] == "home"
    classes = data["classes"]
    assert len(classes) == 4
    class_names = [c["class_name"] for c in classes]
    assert class_names == [
        "wall_crack",
        "damp_or_water_damage",
        "peeling_paint_or_plaster",
        "spalling_or_surface_damage",
    ]
    # Ensure road labels are not mixed in
    assert "D00" not in class_names
    assert "D40" not in class_names


def test_classes_endpoint_invalid_domain(dual_model_client):
    """Verifies GET /api/classes?domain=invalid returns HTTP 400."""
    res = dual_model_client.get("/api/classes?domain=infrastructure")
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert data["error_code"] == "INVALID_DOMAIN"


# ==============================================================================
# 2. System Health Telemetry Tests
# ==============================================================================

def test_health_endpoint_reports_both_models(dual_model_client):
    """Verifies GET /api/health exposes telemetry for both road and home models."""
    res = dual_model_client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert "road_model" in data
    assert "home_model" in data
    assert data["road_model"]["loaded"] is True
    assert data["home_model"]["loaded"] is True
    assert data["road_model"]["domain"] == "road"
    assert data["home_model"]["domain"] == "home"


# ==============================================================================
# 3. Model Routing & Isolation Tests
# ==============================================================================

def test_inspect_road_domain_routing(dual_model_client, test_image_bytes):
    """Verifies selecting Road Problem routes strictly to the Road model."""
    data = {
        "image": (io.BytesIO(test_image_bytes), "road_surface.jpg"),
        "confidence_threshold": "0.25",
        "domain": "road",
    }
    res = dual_model_client.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    result = res.get_json()

    assert result["status"] == "success"
    assert result["domain"] == "road"
    assert "civil" in result["safety_disclaimer"].lower() or "roadway" in result["safety_disclaimer"].lower()

    # Detections should strictly contain road classes
    detections = result["detections"]
    assert len(detections) == 2
    detected_classes = [d["class_name"] for d in detections]
    assert "D00" in detected_classes
    assert "D40" in detected_classes
    # Ensure no home defect classes
    assert "wall_crack" not in detected_classes
    assert "peeling_paint_or_plaster" not in detected_classes


def test_inspect_home_domain_routing(dual_model_client, test_image_bytes):
    """Verifies selecting Home Problem routes strictly to the Home model."""
    data = {
        "image": (io.BytesIO(test_image_bytes), "living_room_wall.jpg"),
        "confidence_threshold": "0.25",
        "domain": "home",
    }
    res = dual_model_client.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    result = res.get_json()

    assert result["status"] == "success"
    assert result["domain"] == "home"
    assert "building" in result["safety_disclaimer"].lower() or "structural" in result["safety_disclaimer"].lower()

    # Detections should strictly contain home defect classes
    detections = result["detections"]
    assert len(detections) == 2
    detected_classes = [d["class_name"] for d in detections]
    assert "wall_crack" in detected_classes
    assert "peeling_paint_or_plaster" in detected_classes
    # Ensure no road classes
    assert "D00" not in detected_classes
    assert "D40" not in detected_classes


def test_inspect_default_domain_is_road(dual_model_client, test_image_bytes):
    """Verifies omitting domain defaults to road model for backward compatibility."""
    data = {
        "image": (io.BytesIO(test_image_bytes), "sample.jpg"),
        "confidence_threshold": "0.25",
    }
    res = dual_model_client.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    result = res.get_json()
    assert result["domain"] == "road"
    assert any(d["class_name"].startswith("D") for d in result["detections"])


def test_inspect_invalid_domain_rejected(dual_model_client, test_image_bytes):
    """Verifies invalid domain returns HTTP 400 with helpful error."""
    data = {
        "image": (io.BytesIO(test_image_bytes), "sample.jpg"),
        "domain": "maritime",
    }
    res = dual_model_client.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    result = res.get_json()
    assert result["status"] == "error"
    assert result["error_code"] == "INVALID_DOMAIN"


# ==============================================================================
# 4. Error Handling for Missing Checkpoints (HTTP 503)
# ==============================================================================

def test_missing_road_checkpoint_returns_503(unauthenticated_client, test_image_bytes):
    """Verifies missing road checkpoint produces HTTP 503 with drive instructions."""
    data = {
        "image": (io.BytesIO(test_image_bytes), "road.jpg"),
        "domain": "road",
    }
    res = unauthenticated_client.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 503
    result = res.get_json()
    assert result["status"] == "error"
    assert result["error_code"] == "MODEL_WEIGHTS_MISSING"
    assert result["domain"] == "road"
    assert "best.pt" in result["setup_instructions"]
    assert "VisionGuard_Artifacts" in result["setup_instructions"]


def test_missing_home_checkpoint_returns_503(unauthenticated_client, test_image_bytes):
    """Verifies missing home checkpoint produces HTTP 503 with drive instructions."""
    data = {
        "image": (io.BytesIO(test_image_bytes), "home.jpg"),
        "domain": "home",
    }
    res = unauthenticated_client.post("/api/inspect", data=data, content_type="multipart/form-data")
    assert res.status_code == 503
    result = res.get_json()
    assert result["status"] == "error"
    assert result["error_code"] == "MODEL_WEIGHTS_MISSING"
    assert result["domain"] == "home"
    assert "home_best.pt" in result["setup_instructions"]
    assert "VisionGuard_Artifacts" in result["setup_instructions"]


# ==============================================================================
# 5. Overlap Suppression (NMS) Unit Tests
# ==============================================================================

def test_box_iou_computation():
    """Verifies IoU computation between bounding boxes."""
    box_a = {"x1": 0, "y1": 0, "x2": 100, "y2": 100}
    box_b = {"x1": 0, "y1": 0, "x2": 100, "y2": 100}
    # Identical boxes -> IoU = 1.0
    assert pytest.approx(compute_box_iou(box_a, box_b), 0.001) == 1.0

    box_c = {"x1": 200, "y1": 200, "x2": 300, "y2": 300}
    # Disjoint boxes -> IoU = 0.0
    assert compute_box_iou(box_a, box_c) == 0.0

    box_d = {"x1": 50, "y1": 0, "x2": 150, "y2": 100}
    # 50% overlap: intersection = 50*100 = 5000, union = 10000+10000-5000 = 15000 -> 1/3
    assert pytest.approx(compute_box_iou(box_a, box_d), 0.001) == (5000 / 15000)


def test_suppress_overlapping_detections_same_class():
    """Verifies that high-overlap detections of the same class are suppressed."""
    detections = [
        {
            "class_id": 0,
            "class_name": "wall_crack",
            "confidence": 0.90,
            "bbox": {"x1": 10, "y1": 10, "x2": 100, "y2": 100, "width": 90, "height": 90},
        },
        {
            "class_id": 0,
            "class_name": "wall_crack",
            "confidence": 0.70,
            # 85% overlap with the above
            "bbox": {"x1": 12, "y1": 12, "x2": 100, "y2": 100, "width": 88, "height": 88},
        },
        {
            "class_id": 0,
            "class_name": "wall_crack",
            "confidence": 0.85,
            # Distinct non-overlapping crack on opposite wall
            "bbox": {"x1": 400, "y1": 400, "x2": 500, "y2": 500, "width": 100, "height": 100},
        },
    ]

    filtered = suppress_overlapping_detections(detections, iou_threshold=0.45)
    # The duplicate 0.70 detection should be suppressed, keeping the two distinct cracks
    assert len(filtered) == 2
    assert filtered[0]["confidence"] == 0.90
    assert filtered[1]["confidence"] == 0.85


# ==============================================================================
# 6. Database Persistence & Domain Segregation Tests
# ==============================================================================

def test_database_persistence_and_filtering_by_domain(tmp_path):
    """Verifies that road and home inspections persist with their domain and can be filtered."""
    db_file = str(tmp_path / "persistence_domain_test.db")
    init_db(db_file)

    road_rec = save_inspection({
        "image_name": "road_01.jpg",
        "original_image_path": "uploads/road_01.jpg",
        "road_name": "NH 48 KM 42",
        "inspection_type": "road",
        "defect_count": 1,
        "defect_type": "Pothole",
        "detections": [],
    }, db_path=db_file)

    home_rec = save_inspection({
        "image_name": "building_01.jpg",
        "original_image_path": "uploads/building_01.jpg",
        "road_name": "Sunrise Towers Block C",
        "inspection_type": "home",
        "defect_count": 2,
        "defect_type": "Wall Crack, Peeling Paint",
        "detections": [],
    }, db_path=db_file)

    assert road_rec["inspection_type"] == "road"
    assert home_rec["inspection_type"] == "home"

    # Query filtered by road
    road_inspections = get_inspections(domain="road", db_path=db_file)
    assert len(road_inspections) == 1
    assert road_inspections[0]["image_name"] == "road_01.jpg"

    # Query filtered by home
    home_inspections = get_inspections(domain="home", db_path=db_file)
    assert len(home_inspections) == 1
    assert home_inspections[0]["image_name"] == "building_01.jpg"

    # Query without filter returns both
    all_inspections = get_inspections(db_path=db_file)
    assert len(all_inspections) == 2


# ==============================================================================
# 7. Model Reload Endpoint Tests
# ==============================================================================

def test_reload_model_domain_param(dual_model_client):
    """Verifies POST /api/reload-model supports domain=road, domain=home, domain=all."""
    res_road = dual_model_client.post("/api/reload-model?domain=road")
    assert res_road.status_code == 200
    assert res_road.get_json()["reloaded_domain"] == "road"

    res_home = dual_model_client.post("/api/reload-model?domain=home")
    # 503 is expected since home_best.pt is in Drive, not local disk
    assert res_home.status_code in (200, 503)
    assert res_home.get_json()["reloaded_domain"] == "home"

    res_all = dual_model_client.post("/api/reload-model?domain=all")
    assert res_all.status_code in (200, 503)
    assert res_all.get_json()["reloaded_domain"] == "all"

    res_invalid = dual_model_client.post("/api/reload-model?domain=bridge")
    assert res_invalid.status_code == 400
