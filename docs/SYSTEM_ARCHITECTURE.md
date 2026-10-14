# VisionGuard AI --- High-Level System Architecture

## Architecture Overview

VisionGuard AI follows a client-server architecture. The presentation tier is built with plain **HTML5, CSS3, and JavaScript** (with optional **Chart.js** for dashboard summaries). The backend service tier is powered by **Python and Flask**, coordinating image processing (OpenCV), model inference, and local persistence (SQLite).

## Intended Application Workflow

The end-to-end inspection lifecycle operates across the following defined steps:

```text
[ Browser (HTML5 / CSS3 / JS) ]
              │
    (1) User opens web app & selects infrastructure image
    (2) Client previews file & captures user inputs
    (3) JS transmits multipart image payload via HTTP POST
              │
              ▼
[ Flask Application (Python) ]
              │
    (4) Validates image: format, file size, dimensions, readability
              │
              ▼
[ Preprocessing & Inference (OpenCV / PyTorch) ]
              │
    (5) OpenCV formats tensor to model specifications
    (6) Selected computer-vision model executes genuine inference
    (7) Model returns detected classes, confidence, and coordinates/masks (if supported)
              │
              ▼
[ Visualisation Pipeline (OpenCV) ]
              │
    (8) OpenCV draws overlays on image strictly matching returned model coordinates
              │
              ▼
[ Flask API Response ]
              │
    (9) Returns structured JSON + annotated image reference
              │
              ▼
[ Browser Display (JS DOM Update) ]
              │
    (10) JavaScript renders side-by-side images, metrics, and detected distresses
              │
              ▼
[ Subsequent Operations (Flask Backend) ]
              │
    (11) Persists inspection to SQLite database
    (12) Generates downloadable PDF reports (ReportLab)
    (13) Updates dashboard metrics (Chart.js) & manages complaints
```

### Detailed Workflow Steps

1. **User Access:** The user opens the web application built with HTML, CSS, and JavaScript.
2. **Image Selection:** The user uploads an infrastructure image through the browser interface.
3. **HTTP API Request:** JavaScript sends the image to a Flask API endpoint (`/api/inspect`) using an asynchronous HTTP POST request (`multipart/form-data`).
4. **Server Validation:** Flask validates the image format, byte size, readability, and dimensions, rejecting corrupt or unsupported files with descriptive JSON messages.
5. **AI Inference:** Flask routes the valid image to the computer-vision inference component, which executes the genuine defect detection model.
6. **Structured Results:** The model returns genuine detections. Flask packages the supported detection classes, confidence scores, and bounding boxes or segmentation masks when available from the model.
7. **Visual Feedback:** OpenCV or an appropriate image-processing component renders the annotated overlay on the image using the actual model outputs, and JavaScript displays the results and annotated image in the browser.
8. **Supporting Services:** In later phases, Flask coordinates database persistence in SQLite, inspection history retrieval, PDF report generation via ReportLab, dashboard analytics, and internal complaint tracking.

*Note on localization:* Do not claim that every model supports bounding boxes or masks. The system must verify the selected model's output format before designing UI overlays.

---

## Planned Frontend Views

The web frontend provides the following planned views (which may be consolidated into fewer screens to keep the application simpler):

- **Dashboard:** Overview of recent inspections, distress counts, and operational health.
- **AI Inspection / Image Upload:** File selection, capture guidelines, client preview, and upload trigger.
- **Detection Results:** Visual breakdown of detections, confidence scores, and side-by-side original/annotated views.
- **Inspection History:** Searchable table of past inspections with class and date filters.
- **Inspection Details:** Granular metadata, technical properties, and distress coordinates for a single inspection.
- **Reports:** Report generation parameters and one-click PDF downloads.
- **Complaint Management:** Logging civic complaints linked to verified inspection findings.
- **Authority Dashboard:** Role-restricted interface for municipal reviewers to inspect complaints and update resolution statuses.

---

## Proposed Target Folder Structure

The proposed target directory layout for future implementation:

```text
VisionGuard-AI/
├── app/                                # Flask application package
│   ├── templates/                      # HTML5 templates (Dashboard, Upload, Results, etc.)
│   ├── static/                         # Static assets delivered to browser
│   │   ├── css/                        # CSS stylesheets
│   │   ├── js/                         # JavaScript client scripts
│   │   └── images/                     # Static UI assets and icons
│   ├── routes/                         # Flask blueprints and REST API endpoints
│   └── services/                       # Business logic (inspection, report generation)
├── ai/                                 # Computer vision subsystem
│   ├── models/                         # Model weights and artifacts
│   ├── detection/                      # Inference engine and class mapping
│   └── preprocessing/                  # Input validation and OpenCV routines
├── database/                           # SQLite database connection and queries
├── data/                               # Storage directories
│   ├── uploads/                        # User-uploaded inspection imagery
│   ├── processed/                      # Preprocessed tensors and annotations
│   └── datasets/                       # Model research and evaluation sets
├── reports/                            # Generated inspection PDF documents
├── tests/                              # Automated test suite
└── docs/                               # Project documentation
```

> **Important:** This is a proposed target structure. Do not automatically create, move, rename, or delete folders during documentation updates. Any physical restructuring will be handled separately.

---

## Architectural Guardrails

- **Client-Server Decoupling:** Keep frontend presentation in HTML/CSS/JS and model inference strictly on the Flask backend.
- **No Mock Predictions:** Never fabricate detections, confidence values, or bounding coordinates.
- **Distinguish Confidence and Severity:** Confidence is a model probability score, not physical defect severity or structural safety.
- **Model Traceability:** Store model name and version alongside saved inspections.
- **Lightweight Dependencies:** Avoid heavy JavaScript frameworks (React/Vue) or unnecessary Python dependencies.
