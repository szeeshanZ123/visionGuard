# VisionGuard AI

AI-powered infrastructure defect inspection system focused on detecting cracks and potholes using computer vision.

---

## 1. Project Overview

**VisionGuard AI** is an engineering-focused computer vision platform designed to assist civil engineers, highway maintenance authorities, and public works inspectors in identifying, documenting, and tracking roadway distresses.

The platform targets the automated visual detection and localization of critical road surface defects—specifically **asphalt cracks** (longitudinal, transverse, alligator) and **potholes**—from standard photographic imagery.

> [!IMPORTANT]
> **Current Development Status: Phase 4 — Flask Backend & Computer-Vision Integration (Completed & Verified).**
> The Flask REST API (`/api/inspect`, `/api/health`, `/api/classes`), YOLOv8 defect detection service, OpenCV annotation engine, and HTML5/CSS3/Vanilla JS client are implemented and verified with 30 passing automated tests.


---

## 2. Problem Statement

Manual visual inspection of roadways and municipal infrastructure is:
- **Time-Consuming & Resource-Intensive:** Inspection teams must manually survey miles of roadway on foot or via slow-moving vehicles.
- **Subjective & Inconsistent:** Different inspectors record defect severity and extents differently based on visual estimates.
- **Difficult to Track Over Time:** Paper-based or ad-hoc photo logs lack centralized coordinates, standardized defect classification, and chronological comparisons.

VisionGuard AI solves this by introducing a repeatable, computer-vision-based workflow that validates image quality, executes authentic defect detection, visualizes distress localization, and organizes inspection records for structured maintenance scheduling.

---

## 3. Intended Users

- **Civil & Highway Engineers:** Conduct formal pavement condition surveys and evaluate localized surface distresses.
- **Municipal Maintenance Crews & Inspectors:** Upload roadway field images to rapidly log defect locations and generate work orders.
- **Supervisors & Public Works Directors:** Review inspection logs, track repair statuses, and audit historical deterioration trends.
- **Academic Evaluators & Project Reviewers:** Review model evaluation benchmarks, architectural modularity, and test coverage.

---

## 4. Planned Features

### Core Defect Detection (MVP)
- **Image Upload & Validation:** Client/server verification of image formats (JPG, PNG, WEBP), file size, and tensor readability.
- **Genuine AI Detection:** Inference using an evaluated computer-vision model for pothole and crack identification.
- **Visual Localisation:** OpenCV rendering of bounding boxes or segmentation masks derived strictly from actual model outputs.
- **Defect Metrics Estimation:** Technical estimation of defect attributes (e.g. bounding dimensions, aspect ratios, surface area approximation) where technically feasible and calibrated.

### Inspection Management & History
- **Inspection Records:** Local SQLite persistence storing timestamps, image paths, detected classes, confidence ratings, and defect measurements.
- **Historical Comparison:** Chronological inspection logs allowing engineers to compare distress progression across repeated surveys.
- **PDF Inspection Summaries:** Standardized, downloadable PDF inspection reports compiled via ReportLab.

### Analytical & Administrative Extensions (Later Phases)
- **Dashboard Metrics:** Summary cards and defect distribution charts rendered with Chart.js.
- **Civic Complaint Lifecycle:** Internal logging of citizen-reported distresses linked to verified inspection imagery.
- **Authority Review View:** Restricted status-management view for maintenance dispatch and repair tracking.

---

## 5. Technology Stack

### Frontend
- **HTML5:** Semantic document structure and accessible forms.
- **CSS3:** Custom responsive layout, styling, and animations (no Tailwind or CSS frameworks).
- **Vanilla JavaScript (ES6+):** User interaction, client-side image preview, asynchronous `fetch` requests, and dynamic DOM rendering.
- **Chart.js (Optional):** Lightweight client-side charting for inspection distribution summaries.
- *Strict Rule:* No single-page application (SPA) frameworks (React, Vue, Angular) and no Streamlit.

### Backend
- **Python:** Core programming language for data structures, CV algorithms, and service coordination.
- **Flask:** Lightweight WSGI web framework exposing RESTful HTTP endpoints and serving static assets.
- **OpenCV (`opencv-python`):** Image loading, color space transformation, preprocessing, and overlay annotation based strictly on real model coordinates.
- **PyTorch (or compatible runtime):** Conditional deep learning inference runtime, utilized only if required by the selected model.
- **SQLite:** Lightweight, serverless relational database for local persistence of inspection records.
- **ReportLab:** Engine for generating clean, auditable PDF inspection reports.

### AI & Modeling
- Real, trained or properly evaluated computer-vision model for object detection or instance segmentation (selected during Phase 2/3).
- *Strict Rule:* Gemini or other language models may only provide plain-language text summaries; they must **never** fabricate defect detections, bounding boxes, or confidence scores.

---

## 6. Planned Phases (6-Phase Development Roadmap)

1. **Phase 1: Project Foundation, Folder Verification, and Documentation (Current Phase)**
   Establish repository structure, verify directory placeholders, and complete comprehensive technical specifications.
2. **Phase 2: Dataset Research, Selection, Licensing Verification, and Data Preparation Plan**
   Evaluate public pavement distress datasets (e.g. RDD2022, CRACK500), audit licenses, and define train/val/test splits.
3. **Phase 3: Model Selection, Training or Fine-Tuning, and Evaluation**
   Select detection/segmentation architecture, establish held-out test sets, and document baseline mAP, precision, and recall.
4. **Phase 4: Flask Backend and Computer-Vision Integration**
   Build Flask REST API endpoints, image validation pipelines, OpenCV preprocessing, and real model inference routines.
5. **Phase 5: HTML/CSS/JavaScript Frontend Integration**
   Implement semantic HTML templates, responsive CSS, and vanilla JS API communication for upload and visualization.
6. **Phase 6: Inspection History, Testing, and Final Improvements**
   Integrate SQLite persistence, ReportLab PDF generation, Chart.js metrics, and comprehensive end-to-end testing.

---

## 7. Current Repository Structure

The current repository structure serves as the source of truth for the project foundation:

```text
visionGuard/
├── README.md                           # Master project overview & specifications
├── requirements.txt                    # Python package dependencies
├── .env.example                        # Environment variables template
├── .gitignore                          # Git exclusions for model weights, databases, uploads
├── docs/                               # Phase 1 technical planning documentation
│   ├── PRD.md                          # Product Requirements Document
│   ├── FEATURES.md                     # Feature specifications & MVP boundaries
│   ├── PROJECT_OVERVIEW.md             # High-level problem, solution, & user analysis
│   ├── TECHNOLOGY_STACK.md             # Technology choices, rationale, & data flow
│   ├── SYSTEM_ARCHITECTURE.md          # Component boundaries & communication protocols
│   ├── DEVELOPMENT_ROADMAP.md          # 6-phase engineering roadmap
│   ├── DATASET_AND_MODEL_RESEARCH.md   # Dataset checklist, licensing, & model selection plan
│   └── TESTING_STRATEGY.md             # Comprehensive testing & evaluation strategy
├── app/                                # Application package
│   ├── main.py                         # Application entry point
│   ├── components/                     # Presentation views & components
│   ├── pages/                          # Multi-page / modular views (.gitkeep)
│   └── services/                       # Business logic and coordination services
├── ai/                                 # Computer vision subsystem
│   ├── preprocessing/                  # Ingestion, validation, OpenCV routines
│   ├── detection/                      # Model inference engine interface
│   └── models/                         # Model weights and artifacts (.gitkeep)
├── database/                           # Persistence layer
│   └── db.py                           # SQLite schema and migration logic
├── data/                               # Storage directories
│   ├── uploads/                        # User-uploaded inspection imagery (.gitkeep)
│   ├── processed/                      # Preprocessed tensors (.gitkeep)
│   ├── datasets/                       # Research datasets (.gitkeep)
│   └── sample_road.jpg                 # Sample test asset
├── reports/                            # Generated inspection PDF exports (.gitkeep)
├── assets/                             # Static project assets (.gitkeep)
└── tests/                              # Automated test suite
```

---

## 8. Safety, Engineering, and Quality Guardrails

1. **A Photograph Alone Does Not Certify Structural Safety:** VisionGuard AI is an inspection-support tool; it does not replace qualified on-site civil engineering assessments.
2. **Confidence Is Not Severity:** Model confidence measures classification probability, not physical distress severity, depth, or safety risk.
3. **No Fabricated Predictions:** Never generate simulated, hardcoded, or mock bounding boxes. No-detection cases must be reported honestly.
4. **Empirical Evaluation:** Model accuracy claims must be backed by documented evaluation on a held-out test set with standard metrics (precision, recall, mAP, IoU).
5. **Privacy & Security:** Never commit real credentials, secret API keys, or private user images to version control.

---

## 9. Quick Start & Execution Guide

### 9.1 Model Checkpoint Setup (`best.pt`)
The YOLOv8 Nano model trained on the RDD2022 India dataset exports its checkpoint to Google Drive:
1. Download `best.pt` from your Google Drive folder (`VisionGuard_Artifacts/best.pt`).
2. Move the file into the project directory:
   ```bash
   # Target location:
   ai/models/best.pt
   ```
*(Note: If `best.pt` is not present, the Flask server still launches safely and the API informs the user via HTTP 503 with exact setup instructions).*

### 9.2 Launching the Flask Web Application & REST API
```bash
python app/server.py
```
Or with Flask CLI:
```bash
python -m flask --app app.server run --port 5000
```
Open your browser at `http://127.0.0.1:5000` to access the inspection interface.

### 9.3 Running Automated Tests
```bash
python -m pytest -v
```
All 30 unit, API, image preprocessing, and app tests will execute.