# VisionGuard AI --- Development Roadmap

**Document Status:** Approved Technical Baseline  
**Current Phase:** Phase 3.4 — YOLOv8 Nano Training & Evaluation (Training Notebook & Protocol Created; Awaiting Execution in Colab)  
**Implementation State:** Planning, Preparation & Training Notebooks Only (Zero Local Weights Downloaded)  
**Version:** 1.6  

---

## 1. Phased Implementation Strategy

VisionGuard AI follows a strict 6-phase engineering roadmap. Each phase must be formally reviewed and verified against its documented exit criteria before subsequent phases commence.

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Project Foundation, Folder Verification, and Documentation    │  [COMPLETED]
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 2: Dataset Research, Selection, Licensing, & Preparation Plan    │  [COMPLETED]
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 3: AI Model Environment, Dataset Prep, Training & Evaluation     │  [ACTIVE]
│   ├── Phase 3.1: Hardware & Environment Verification                   │  [COMPLETED]
│   ├── Phase 3.2: Dataset Preparation Specification                     │  [COMPLETED]
│   ├── Phase 3.3: Colab Dataset Acquisition & Validation (India RDD)    │  [COMPLETED]
│   └── Phase 3.4: YOLOv8 Training, Validation, and Evaluation           │  [ACTIVE / NOTEBOOK CREATED]
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 4: Flask Backend and Computer-Vision Integration                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 5: HTML/CSS/JavaScript Frontend Integration                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 6: Inspection History, Testing, and Final Improvements           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Detailed Phase Specifications

### Phase 1: Project Foundation, Folder Verification, and Documentation
- **Primary Goal:** Establish repository baseline, verify foundational folder structure, resolve documentation inconsistencies, and document all engineering specifications.
- **Key Deliverables:**
  - Standardized project documentation (`README.md`, `PRD.md`, `FEATURES.md`, `PROJECT_OVERVIEW.md`, `TECHNOLOGY_STACK.md`, `SYSTEM_ARCHITECTURE.md`, `DEVELOPMENT_ROADMAP.md`, `DATASET_AND_MODEL_RESEARCH.md`, `TESTING_STRATEGY.md`).
  - Verified folder layout with appropriate `.gitkeep` placeholders.
  - Explicit definition of project boundaries, technology stack, and guardrails.
- **Exit Criteria:**
  - All documentation files reviewed, consistent, and approved.
  - Strict confirmation that no application logic, backend server, database, or AI models were created.

---

### Phase 2: Dataset Research, Selection, Licensing Verification, and Data Preparation Plan
- **Primary Goal:** Investigate public road distress datasets, verify licensing rights, examine annotation quality, and formulate data preparation routines.
- **Key Deliverables:**
  - Evaluated dataset survey report covering candidate datasets (RDD2022, CRACK500, SDNET2018, Roboflow Pothole).
  - Verification of commercial and academic licensing terms (CC BY 4.0 / CC BY-SA 4.0).
  - Defined initial candidate class mapping for supported defect categories: longitudinal cracks (`D00`), transverse cracks (`D10`), alligator cracks (`D20`), and potholes (`D40`).
  - Train, validation, and held-out test split protocol.
- **Exit Criteria:**
  - Dataset selected with documented provenance and permissive licensing (RDD2022).
  - Model architecture selected (YOLOv8 Nano).

---

### Phase 3: AI Model Environment, Dataset Prep, Training & Evaluation

#### Phase 3.1: Hardware & Environment Verification [COMPLETED]
- **Deliverables:** `docs/PHASE_3_ENVIRONMENT_CHECK.md`. Verified RTX 3050 Laptop GPU (4.0 GB VRAM), AMD Ryzen 7 7435HS, 16 GB RAM, 107 GB free disk space. Python 3.14 baseline documented. Decision confirmed to run model training on Google Colab (T4 GPU, 15 GB VRAM).

#### Phase 3.2: Dataset Acquisition & Preparation Specification [COMPLETED]
- **Deliverables:** `docs/PHASE_3_DATASET_PREPARATION.md`. Verified official Figshare source (DOI 10.6084/m9.figshare.21431547.v1, ~13.26 GB archive), country subset options, sequence-aware block partitioning (preventing adjacent video frame leakage), 0-indexed YOLO class mapping (`D00`, `D10`, `D20`, `D40`), and automated validation checks.

#### Phase 3.3: Google Colab Dataset Preparation & Validation [COMPLETED]
- **Deliverables:** `VisionGuard_Phase_3_3_Dataset_Preparation.ipynb`. Successfully executed by user in Colab on RDD2022 India subset. Produced 7,706 total verified images: 5,356 train (69.5%), 1,150 val (14.9%), 1,200 test (15.6%). Total annotations: 6,831 instances (D00: 1,555, D10: 68, D20: 2,021, D40: 3,187). Backup archive saved to Google Drive.

#### Phase 3.4: YOLOv8 Nano Training, Fine-Tuning, and Evaluation [ACTIVE / NOTEBOOK CREATED]
- **Primary Goal:** Train YOLOv8n on prepared RDD2022 India dataset in Google Colab, export weights (`best.pt`), and measure metrics on held-out test split.
- **Deliverables:** `VisionGuard_Phase_3_4_YOLOv8_Training.ipynb` and `docs/PHASE_3_MODEL_TRAINING.md`.
- **Configuration:** YOLOv8 Nano (`yolov8n.pt`), `imgsz=640`, `batch=8`, `epochs=30`, `seed=42`, `patience=10`.
- **Current Status:** Training notebook and protocol ready for execution in Google Colab; awaiting training completion to obtain `best.pt`.
- **Exit Criteria:**
  - Model meets baseline acceptance metrics (mAP@0.5 >= 0.50, Precision >= 0.60, Recall >= 0.55).
  - Output format (bounding coordinates and class labels) confirmed and documented.
  - Held-out test set evaluated strictly after training and checkpoint selection are frozen.
  - Trained weights (`best.pt`) exported to Google Drive for local download to `ai/models/best.pt`.

---

### Phase 4: Flask Backend and Computer-Vision Integration
- **Primary Goal:** Implement Flask REST API endpoints and integrate the verified computer-vision inference pipeline.
- **Key Deliverables:**
  - Working Flask API endpoint (`POST /api/inspect`) accepting multipart image streams.
  - OpenCV image preprocessing and validation pipeline (format checks, resizing, normalization).
  - Model loader and inference execution service returning structured JSON.
  - OpenCV visual overlay engine rendering bounding boxes/masks based strictly on actual model outputs.
- **Exit Criteria:**
  - Endpoints handle valid, corrupted, and oversized files gracefully with standard HTTP status codes.
  - Inference returns real model coordinates without mock predictions.

---

### Phase 5: HTML/CSS/JavaScript Frontend Integration
- **Primary Goal:** Build the clean, framework-free web interface and integrate it with the Flask backend.
- **Key Deliverables:**
  - Semantic HTML5 templates for dashboard, upload, and results display.
  - Responsive vanilla CSS3 stylesheets (no CSS frameworks).
  - Vanilla JavaScript client managing image selection, preview, asynchronous `fetch` requests, and DOM updates.
  - Side-by-side original and annotated image comparison interface.
- **Exit Criteria:**
  - Complete user flow from file selection to detection visualization operates smoothly in standard desktop and tablet browsers.
  - Zero frontend framework dependencies introduced.

---

### Phase 6: Inspection History, Testing, and Final Improvements
- **Primary Goal:** Implement local persistence, downloadable PDF reporting, comprehensive test suites, and final documentation polish.
- **Key Deliverables:**
  - SQLite persistence layer logging inspection timestamps, image references, defect findings, and model versions.
  - Historical survey log allowing chronological comparison of defect progression.
  - Programmatic PDF inspection report generation via ReportLab.
  - Optional Chart.js dashboard metrics.
  - Complete automated unit, API, and workflow test suite.
- **Exit Criteria:**
  - Stored records persist reliably and match source inference data.
  - Generated PDF reports open cleanly and reflect stored records.
  - All automated tests pass with 100% success rate.

---

## 3. Phase Completion Rule

> [!CAUTION]
> Do not mark any phase complete merely because code or text was generated. Review each deliverable against its stated exit criteria, verify reproducibility, inspect output logs, and obtain explicit user approval before advancing to the next phase.
