# VisionGuard AI --- Feature Specification

**Document Status:** Approved Technical Baseline  
**Project Phase:** Phase 1 --- Project Foundation & Documentation Only  
**Implementation State:** Planned Only --- No Features Implemented Yet  
**Version:** 1.2  

---

## 1. Feature Classification Overview

VisionGuard AI organizes planned capabilities into three distinct tiers:
1. **MVP Features:** Essential functionality required to validate image-based defect detection and inspection recording.
2. **Later-Phase Features:** Key operational enhancements planned for subsequent engineering phases (history comparisons, reporting, analytics).
3. **Optional Features:** Value-add extensions to be pursued only if primary milestones are completed and resources permit.

> [!NOTE]
> All features documented below are **planned for future phases**. No application logic, working model, or UI pages are implemented in Phase 1.

---

## 2. MVP Features (Phase 4 & Phase 5)

### MVP-1: Web Image Ingestion & Client Preview
- **Target Phase:** Phase 5 (Frontend Integration)
- **Description:** An HTML5 file upload interface styled with responsive CSS and managed by vanilla JavaScript.
- **Planned Behavior:**
  - Users drag-and-drop or select road photos (JPG, PNG, WEBP up to 15 MB).
  - JavaScript provides an instant client-side preview via `FileReader`.
  - Asynchronous transmission via `fetch()` using `multipart/form-data` to the Flask `/api/inspect` endpoint.
- **Acceptance Criteria:**
  - Supported files are previewed and transmitted cleanly.
  - Unsupported file formats or oversized files are rejected with clear client notices.

### MVP-2: Server-Side Validation & OpenCV Preprocessing
- **Target Phase:** Phase 4 (Flask Backend & CV Integration)
- **Description:** Flask API validation and OpenCV image processing pipeline.
- **Planned Behavior:**
  - Server verifies file byte integrity, decoding ability, and dimensions.
  - OpenCV loads image into BGR NumPy arrays, validates color channels, and prepares model-specific input tensors.
  - Returns structured HTTP 400 JSON errors for unreadable or corrupted files.
- **Acceptance Criteria:**
  - Corrupt or invalid images cannot reach the AI model pipeline.
  - Valid images are converted into proper tensors with zero data loss.

### MVP-3: Genuine AI Defect Detection (Cracks & Potholes)
- **Target Phase:** Phase 4 (Flask Backend & CV Integration)
- **Description:** Execution of a trained or properly evaluated computer-vision model for road distress detection.
- **Planned Behavior:**
  - Ingests preprocessed image tensors and executes genuine forward inference.
  - Identifies supported defect classes: **Potholes**, **Longitudinal Cracks**, **Transverse Cracks**, and **Alligator Cracking**.
  - Returns genuine bounding box coordinates `[x1, y1, x2, y2]` or segmentation masks, class labels, and statistical confidence values.
  - Reports zero detections honestly when no distress is detected.
- **Acceptance Criteria:**
  - 100% of detections come from actual model outputs.
  - No synthetic, simulated, or hardcoded predictions are ever produced.

### MVP-4: Detection Overlay Visualisation
- **Target Phase:** Phase 4 (Backend) & Phase 5 (Frontend)
- **Description:** Visual representation of defect spatial locations.
- **Planned Behavior:**
  - OpenCV renders bounding boxes or segmentation masks on the image strictly derived from model coordinates.
  - Class name and confidence percentage are labeled cleanly above each defect bounding box.
  - JavaScript displays the annotated image alongside the raw input for easy side-by-side comparison.
- **Acceptance Criteria:**
  - Overlays align perfectly with defect locations in pixel coordinates.
  - If the model only supports classification, bounding boxes are not promised or drawn.

### MVP-5: Measurable Defect Property Estimation
- **Target Phase:** Phase 4 (Backend)
- **Description:** Technical extraction of geometric properties from detection outputs where feasible.
- **Planned Behavior:**
  - Computes bounding width, height, aspect ratio, and pixel area of detected distresses.
  - Where ground-plane or camera calibration parameters are supplied, calculates approximate real-world surface dimensions.
- **Acceptance Criteria:**
  - Clearly identifies pixel measurements versus calibrated real-world estimates.
  - Does not present geometric estimates as structural severity ratings.

---

## 3. Later-Phase Features (Phase 6)

### LATER-1: Local Inspection Persistence (SQLite)
- **Target Phase:** Phase 6 (Inspection History & Testing)
- **Description:** Relational persistence of inspection findings.
- **Planned Behavior:**
  - Automatically records inspection timestamp, image reference, detected defect types, confidence scores, and bounding coordinates into a local SQLite database (`data/visionguard.db`).
  - Enables auditability and historical tracking across road survey campaigns.
- **Acceptance Criteria:**
  - Records survive application and server restarts.
  - Schema supports relational linking between images and multiple defect findings.

### LATER-2: Inspection History & Chronological Comparison
- **Target Phase:** Phase 6 (Inspection History & Testing)
- **Description:** Tabular log and comparison interface for past surveys.
- **Planned Behavior:**
  - Displays a filterable table of past inspections with date, road name/location, and detected defect counts.
  - Allows engineers to compare historical surveys of the same road segment to track crack propagation or pothole enlargement over time.
- **Acceptance Criteria:**
  - Users can filter records by defect class or date range.
  - Detailed view presents original and annotated images from historical records.

### LATER-3: Standardized PDF Inspection Reporting
- **Target Phase:** Phase 6 (Inspection History & Testing)
- **Description:** Exporting comprehensive inspection summaries.
- **Planned Behavior:**
  - Flask compiles inspection metadata, side-by-side imagery, defect tables, and engineering disclaimers into a standardized PDF using ReportLab.
  - Downloadable directly from the web interface.
- **Acceptance Criteria:**
  - PDF files are valid, formatted cleanly, and accurately reflect database values.
  - Includes mandatory engineering disclaimers.

---

## 4. Optional Features (Beyond Phase 6)

### OPT-1: Dashboard Metrics & Charts (Chart.js)
- **Description:** Visual aggregation of municipal inspection trends.
- **Planned Behavior:**
  - Renders defect distribution bar charts and monthly survey volume lines via Chart.js from Flask JSON aggregation endpoints.
- **Prerequisite:** Sufficient volume of populated historical survey data.

### OPT-2: Civic Complaint Management Workflow
- **Description:** Internal tracking of citizen-reported road complaints linked to inspection records.
- **Planned Behavior:**
  - Allows logging civic complaints with status tracking (`Submitted`, `Under Review`, `Repaired`).
- **Prerequisite:** Core inspection and persistence workflows fully operational and verified.

### OPT-3: Restricted Authority Review View
- **Description:** Role-restricted review interface for public works supervisors.
- **Planned Behavior:**
  - Authenticated view allowing supervisors to update repair dispatch statuses.
- **Prerequisite:** Implementation of user authentication and authorization.

### OPT-4: Optional AI-Generated Explanations (Gemini / LLM)
- **Description:** Plain-language summary text generated from verified inspection data.
- **Planned Behavior:**
  - Summarizes verified detection counts and metrics into accessible text for non-technical stakeholders.
- **Strict Guardrail:** LLM must strictly format existing data; it is prohibited from creating detections, bounding boxes, or severity claims.

---

## 5. Summary Matrix

| Feature | Category | Target Phase | Primary Technology |
| :--- | :--- | :--- | :--- |
| **Image Ingestion & Preview** | MVP | Phase 5 | HTML5, CSS3, Vanilla JS |
| **Server Validation & Preprocessing** | MVP | Phase 4 | Python, Flask, OpenCV |
| **Genuine Defect Detection** | MVP | Phase 4 | Python, PyTorch / CV Model |
| **Detection Visualisation** | MVP | Phase 4 / 5 | OpenCV, HTML5 Canvas / IMG |
| **Defect Property Estimation** | MVP | Phase 4 | Python, OpenCV |
| **SQLite Persistence** | Later Phase | Phase 6 | SQLite, Python |
| **Inspection History & Comparison** | Later Phase | Phase 6 | HTML/JS, Flask, SQLite |
| **PDF Report Generation** | Later Phase | Phase 6 | Python, ReportLab |
| **Dashboard Charts** | Optional | Post-Phase 6 | Chart.js, Flask API |
| **Civic Complaint Management** | Optional | Post-Phase 6 | Flask, SQLite, HTML/JS |
| **Authority Review View** | Optional | Post-Phase 6 | Flask, HTML/JS, Auth |
| **AI Text Summaries (Gemini)** | Optional | Post-Phase 6 | Python, Google GenAI SDK |
