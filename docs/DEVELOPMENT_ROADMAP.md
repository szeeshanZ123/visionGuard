# VisionGuard AI --- Development Roadmap

**Document Status:** Approved Technical Baseline  
**Current Phase:** Phase 2 --- Dataset Research & Selection (Completed; Awaiting Phase 3 Approval)  
**Implementation State:** Planning & Research Only (Zero Weights or Datasets Downloaded)  
**Version:** 1.3  

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
│ Phase 3: Model Selection, Training or Fine-Tuning, and Evaluation      │  ◄ NEXT PHASE (AWAITING APPROVAL)
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

### Phase 1: Project Foundation, Folder Verification, and Documentation (Current Phase)
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
  - Evaluated dataset survey report covering candidate datasets (e.g. RDD2022, CRACK500, Pothole-600).
  - Verification of commercial and academic licensing terms.
  - Defined class mapping for supported defect categories: potholes and cracks (longitudinal, transverse, alligator).
  - Train, validation, and held-out test split protocol.
- **Exit Criteria:**
  - Dataset selected with documented provenance and permissive licensing.
  - Held-out test set isolated and sealed for unbiased evaluation.

---

### Phase 3: Model Selection, Training or Fine-Tuning, and Evaluation
- **Primary Goal:** Select suitable computer-vision architecture (object detection vs instance segmentation), train or fine-tune on chosen dataset, and measure baseline metrics.
- **Key Deliverables:**
  - Model selection record comparing candidate architectures (e.g. YOLOv8, Faster R-CNN, Mask R-CNN).
  - Trained model weights stored in `ai/models/`.
  - Comprehensive model evaluation report reporting precision, recall, mAP@0.5, and inference latency on the held-out test set.
  - Systematic analysis of false positives and false negatives under varied lighting and road conditions.
- **Exit Criteria:**
  - Model meets baseline acceptance metrics (mAP@0.5 >= 0.50, Precision >= 0.65, Recall >= 0.60).
  - Output format (bounding coordinates or segmentation masks) confirmed and documented.

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
