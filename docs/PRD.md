# VisionGuard AI --- Product Requirements Document (PRD)

**Document Status:** Approved Technical Baseline  
**Project Phase:** Phase 1 --- Project Foundation & Documentation Only  
**Version:** 1.2  

---

## 1. Problem Statement

Public roadway networks represent substantial capital assets requiring ongoing condition monitoring. Current manual inspection processes suffer from:
1. **High Latency & Costs:** Visual walk-through inspections of roadway segments are labor-intensive, hazardous to field personnel, and costly to scale.
2. **Subjectivity & Variability:** Inspectors evaluate pavement condition with varying degrees of precision; one inspector may categorize crack fatigue as severe while another marks it as moderate.
3. **Information Silos:** Defect photographs taken in the field are frequently archived in unindexed directories without standardized defect labels, bounding coordinates, or chronological persistence.

VisionGuard AI solves this by delivering an automated, objective, and reproducible computer-vision inspection system that detects asphalt cracks and potholes from field photography, visualizes distress locations accurately, and preserves inspection history for longitudinal comparison.

---

## 2. Target Users

- **Civil & Highway Field Inspectors:** Ingest surface photography captured during routine road patrols to quickly log defects.
- **Municipal Maintenance Supervisors:** Review documented defect instances, verify model findings, and plan asphalt patching or crack sealing crews.
- **Highway Asset Managers:** Track localized defect recurrence over time to evaluate pavement deterioration rates and optimize capital rehabilitation budgets.
- **System Evaluators & Auditors:** Audit technical performance metrics (precision, recall, mAP) against verified held-out datasets.

---

## 3. User Stories

### Story 1: Field Image Ingestion & Validation
> **As a** field inspector,  
> **I want to** upload road surface images in standard formats (JPG, PNG, WEBP) through a clean web interface,  
> **So that** I can verify that my photo meets resolution and quality requirements before triggering automated analysis.

### Story 2: Authentic Defect Detection & Localisation
> **As a** civil maintenance engineer,  
> **I want to** run a genuine computer-vision model on my uploaded image to detect potholes and cracks,  
> **So that** I receive accurate visual overlays (bounding boxes or masks) matching the defect's exact location without fabricated annotations.

### Story 3: Defect Dimension & Property Estimation
> **As a** maintenance planner,  
> **I want to** view estimated geometric defect properties (bounding width, height, aspect ratio, and estimated pixel extent),  
> **So that** I can gauge the relative scale of the distress for material estimation.

### Story 4: Inspection Persistence & History
> **As a** highway asset manager,  
> **I want to** save verified inspection findings into a local SQLite database,  
> **So that** I can review historical records for a specific roadway segment and observe whether distresses have widened over time.

### Story 5: Standardized PDF Reporting
> **As an** inspection supervisor,  
> **I want to** export a clean, downloadable PDF inspection summary containing the original image, annotated overlay, defect details, and engineering disclaimers,  
> **So that** I can append formal documentation to maintenance work orders.

---

## 4. MVP Scope

The Minimum Viable Product (MVP) focuses strictly on the core defect detection and inspection management workflow:

1. **Web Ingestion Interface:** Semantic HTML5, CSS3, and vanilla JavaScript form for image upload and client-side preview.
2. **Flask REST API:** Backend endpoints for image ingestion, format validation, and OpenCV preprocessing.
3. **Computer-Vision Defect Detection:** Authentic model inference identifying potholes and cracks.
4. **Overlay Visualisation:** OpenCV-rendered bounding boxes or segmentation masks derived exclusively from actual model coordinates.
5. **Local SQLite Persistence:** Saving inspection timestamp, image references, detected classes, confidence ratings, and bounding coordinates.
6. **PDF Report Export:** Basic single-page PDF inspection report generated via ReportLab.

---

## 5. Features Excluded from the MVP

To maintain high quality, strict focus, and student-developer feasibility, the following features are explicitly excluded from the MVP:

- **Live Video Stream Processing:** Ingestion and real-time inference on continuous drone or dashcam video streams.
- **Automated Severity / Safety Certification:** Automatic structural safety rating or engineering-grade structural adequacy certification from photos.
- **Direct Municipal ERP / Work-Order Dispatch Integration:** Automated API dispatch to third-party municipal work-order systems.
- **Complex Authentication & Multi-Tenancy:** Role-based access control, LDAP integration, or multi-tenant database partitioning.
- **Heavy Frontend Frameworks:** React, Next.js, Vue, or Streamlit wrappers.

---

## 6. Functional Requirements

| ID | Requirement Description | Priority |
| :--- | :--- | :--- |
| **FR-01** | Accept supported image formats (JPG, JPEG, PNG, WEBP) and reject invalid or corrupted files with clear JSON error messages. | P0 (MVP) |
| **FR-02** | Validate file size on client and server (enforcing a 15 MB maximum threshold). | P0 (MVP) |
| **FR-03** | Execute genuine computer-vision inference for supported defect classes (potholes, cracks) via a Flask API endpoint. | P0 (MVP) |
| **FR-04** | Return structured JSON containing detected class labels, confidence scores, and bounding coordinates or masks where supported by the model. | P0 (MVP) |
| **FR-05** | Render visual overlays (bounding boxes/masks) using OpenCV strictly derived from genuine model outputs; report zero detections honestly when no defects exist. | P0 (MVP) |
| **FR-06** | Estimate measurable geometric properties (bounding box dimensions, pixel extents, aspect ratio) where technically feasible. | P0 (MVP) |
| **FR-07** | Persist inspection records (timestamp, image path, defect findings, model metadata) in a local SQLite database. | P1 (Core) |
| **FR-08** | Provide a searchable inspection history view allowing users to review past survey records. | P1 (Core) |
| **FR-09** | Generate a downloadable PDF report matching stored inspection data via ReportLab. | P1 (Core) |
| **FR-10** | Summarize aggregate defect counts and distributions on a dashboard view (optional Chart.js charts). | P2 (Later) |
| **FR-11** | Allow internal tracking of citizen or inspector complaints linked to verified inspection IDs. | P2 (Later) |
| **FR-12** | Restricted authority review view for updating repair and maintenance dispatch statuses. | P2 (Later) |

---

## 7. Non-Functional Requirements

- **Usability:** Clean, responsive HTML5/CSS3/JavaScript interface usable on desktop and tablet browsers without external dependencies.
- **Decoupled Architecture:** Strict separation between frontend presentation (HTML/CSS/JS), backend routing/services (Flask), vision inference (OpenCV/PyTorch), and persistence (SQLite).
- **Inference Latency:** Target inference latency under 2.5 seconds per standard 1080p image on commodity CPU hardware.
- **Traceability:** Inspection records must store the model name and version used for inference.
- **Data Integrity:** Database operations must be transactional, ensuring no partial or corrupted inspection records are written.
- **Security & Privacy:** Uploaded images must be stored securely with sanitized filenames; no API secrets or private data committed to version control.

---

## 8. Success Criteria

1. **Input Robustness:** The Flask backend successfully accepts valid images and returns HTTP 400 with descriptive error messages for invalid, corrupted, or oversized files.
2. **Inference Authenticity:** 100% of rendered bounding boxes and reported confidence scores originate directly from real model inference. No mock or hardcoded detections exist.
3. **Model Benchmark Performance:** The selected model achieves baseline target metrics (mAP@0.5 >= 0.50, Precision >= 0.65, Recall >= 0.60) on a representative held-out pavement test set.
4. **Persistence Reliability:** Saved inspection records persist across server restarts, and retrieved database records match raw inference output exactly.
5. **Clean Code & Verification:** Full test coverage across image validation, API endpoints, and database operations.

---

## 9. Limitations & Assumptions

### Limitations
- **Structural Safety Boundary:** A photograph alone **cannot determine or certify the structural safety** of a roadway, sub-base, or bridge deck. Sub-surface voids, moisture content, and asphalt thickness cannot be deduced from surface photography.
- **Confidence vs. Severity:** Model confidence is a statistical probability of detection, **not an indicator of defect severity or structural danger**. A shallow hairline crack may have a 95% model confidence score, while a dangerous pothole in poor lighting may score 65%.
- **Environmental Sensitivity:** Detection accuracy is influenced by road lighting, cast shadows, moisture/puddles, and optical perspective.

### Assumptions
- Captured images are oriented at approximately 45 degrees or top-down overhead relative to the roadway surface.
- The development and deployment environment provides standard Python 3.10+ execution capabilities.
- The prototype operates in a single-tenant local environment prior to multi-user municipal rollouts.
