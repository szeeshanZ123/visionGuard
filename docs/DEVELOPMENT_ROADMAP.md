# VisionGuard AI 2.0 — Development Roadmap

**Document Status:** Approved Technical Baseline  
**Current Phase:** Phase 6 — Gemini Multimodal Vision 2.0 & Production Hardening (Completed & Verified)  
**Implementation State:** Flask API, Gemini Multimodal Vision, OpenCV Overlays, Citizen Complaint Workflow, and Interactive Map Verified with 81 Passing Automated Tests  
**Version:** 2.0  

---

## 1. Phased Engineering Strategy Overview

VisionGuard AI has advanced across six completed implementation phases, transforming from an early research concept into an operational, multimodal civil inspection platform.

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Project Foundation, Baseline Standards & Documentation        │  [COMPLETED]
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 2: Domain Taxonomy & Defect Schema Research                      │  [COMPLETED]
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 3: Dataset Research, Colab Exploration & Checkpoint Archival     │  [COMPLETED]
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 4: Flask Backend, OpenCV Annotation & Dual-Persistence Setup     │  [COMPLETED]
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 5: Citizen UI, Leaflet Maps, and Civic Complaint Assistance      │  [COMPLETED]
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 6: Gemini Multimodal Vision 2.0 Integration & Full Verification  │  [COMPLETED]
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Completed Implementation Phases (Verified Baseline)

### Phase 1: Project Foundation & Technical Specifications [COMPLETED]
- **Deliverables:** Standardized engineering baseline, directory architecture, and strict security protocols.
- **Outcome:** Clean separation of concerns, repository guardrails, and environment variable configuration structure.

### Phase 2: Domain Taxonomy & Defect Schema Research [COMPLETED]
- **Deliverables:** Systematic defect taxonomy for **Road Distresses** (potholes, longitudinal cracks, transverse cracks, alligator cracking, surface raveling) and **Building Defects** (wall cracks, moisture damage, peeling paint, plaster damage, concrete spalling).
- **Outcome:** Structured classification schemas and standardized visual distress metrics.

### Phase 3: Dataset Research & Checkpoint Archival [COMPLETED]
- **Deliverables:** Exploration of open distress datasets (RDD2022, CRACK500) and experimental Colab training notebooks (`VisionGuard_Road_Candidate_Exp2_Training.ipynb`).
- **Outcome:** Checkpoints archived at `ai/models/best.pt` and `ai/models/home_best.pt` for offline historical research. Active production migrated to Google Gemini Multimodal Vision to eliminate 512MB RAM constraints and enable multi-object reasoning without heavy PyTorch dependencies.

### Phase 4: Flask Backend, Preprocessing & Non-Destructive Overlays [COMPLETED]
- **Deliverables:**
  - Robust Flask WSGI application (`app/server.py`, `wsgi.py`) with RESTful endpoints (`/api/inspect`, `/api/inspections`, `/api/auth/*`).
  - Preprocessing and validation pipeline in `ai/preprocessing/image_ops.py` (format verification, dimension checks, resolution safety clamping).
  - OpenCV visual annotation engine generating non-destructive bounding box overlays, defect IDs (`[D001]`), and severity pills.
  - Dual-database persistence supporting local SQLite (`data/visionguard.db`) and cloud Neon PostgreSQL (`DATABASE_URL`).

### Phase 5: Citizen Interface, Leaflet Map & Civic Complaints [COMPLETED]
- **Deliverables:**
  - Responsive, framework-free frontend in `frontend/create_home.html`, `frontend/landing.html`, `frontend/login.html`, and `frontend/map.html`.
  - Leaflet.js interactive defect mapping with OpenStreetMap tiles, filtering, and geocoded summary cards.
  - Civic Complaint Assistance module (`database/complaints.py`) supporting formal complaint draft registration, editing, and automated ReportLab PDF compilation.
  - Citizen report tracking with strict user data isolation.

### Phase 6: Gemini Multimodal Vision 2.0 & Full Platform Verification [COMPLETED]
- **Deliverables:**
  - Integration of official Google Gen AI SDK (`google-genai` v2.20+) in `ai/gemini_service.py`.
  - Configurable primary model (`gemini-3.1-flash-lite`) with automatic fallback rotation (`gemini-flash-latest`, `gemini-3.8-flash`, `gemini-2.5-flash`).
  - Strict JSON schema extraction ensuring normalized bounding boxes, itemized defect lists, visual evidence rationale, and citizen safety guidance.
  - Dual action pathways: Option A (Read Guidance) vs Option B (Submit Official Complaint).
  - **81 Automated Tests Passing (100%):** Comprehensive test suites covering authentication, CSRF security, multimodal inference, OpenCV overlays, database persistence, and PDF export.

---

## 3. Future Improvements & Ongoing Research Roadmap

The following initiatives represent planned enhancements and research extensions beyond the current submission baseline:

### 1. Offline Edge-Device Detection (Ongoing Research)
- **Objective:** Train and quantize dedicated lightweight models (e.g., YOLOv8n / INT8 ONNX) for deployment on low-power edge hardware (Raspberry Pi, mobile devices, in-vehicle dashcams) where internet connectivity is unavailable.
- **Status:** Experimental notebooks and baseline weights preserved in `ai/models/`; edge pipeline slated for post-submission research.

### 2. Temporal Fissure Progression Tracking
- **Objective:** Enable citizens and municipal inspectors to take repeat photographs of the same structural fissure over 3 to 12 months.
- **Capability:** Computer-vision image registration (homography alignment) to automatically calculate whether a crack is widening, stabilizing, or accelerating in degradation rate.

### 3. Automated Municipal GIS & Open311 Webhooks
- **Objective:** Bridge the civic complaint module directly into municipal grievance dispatch systems.
- **Capability:** Automated webhook delivery to city portals (Open311, civic CRM APIs) to eliminate manual grievance forwarding.

### 4. Drone Photogrammetry & Orthomosaic Slicing
- **Objective:** Ingest aerial drone imagery covering entire roadway corridors or multi-acre commercial roofs.
- **Capability:** Large-format tiled orthomosaic processing with stitched spatial defect mapping.

---

## 4. Engineering Standards & Assessment Clarification

- **Active AI Engine:** Google Gemini Multimodal Vision (`gemini-3.1-flash-lite`) is the active defect detection engine.
- **Preliminary Nature of Assessment:** Defect severity ratings (`Critical`, `High`, `Moderate`, `Low`) represent preliminary visual triage based on photographic evidence. VisionGuard AI makes no claim of engineering certification or ASTM regulatory compliance; all high-severity findings recommend on-site validation by certified civil engineers.
