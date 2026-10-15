# VisionGuard AI --- System Architecture Specification

**Document Status:** Approved Technical Baseline  
**Project Phase:** Phase 1 --- Project Foundation & Documentation Only  
**Implementation State:** Planned Architecture (Not Implemented)  
**Version:** 1.2  

---

## 1. Architectural Philosophy

VisionGuard AI adopts a modular, decoupled client-server architecture. The system establishes distinct operational boundaries between presentation, backend routing, image preprocessing, artificial intelligence inference, persistence, and reporting.

```text
┌────────────────────────────────────────────────────────┐
│               Frontend Presentation Tier               │
│          HTML5  •  CSS3  •  Vanilla JavaScript         │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP REST (JSON / Multipart)
┌───────────────────────────▼────────────────────────────┐
│                  Backend Service Tier                  │
│                     Flask (Python)                     │
└─────┬─────────────────────┬──────────────────────┬─────┘
      │                     │                      │
      ▼                     ▼                      ▼
┌──────────────┐     ┌──────────────┐       ┌─────────────┐
│  Vision & AI │     │ Persistence  │       │  Reporting  │
│  OpenCV & CV │     │    SQLite    │       │  ReportLab  │
│    Model     │     │              │       │             │
└──────────────┘     └──────────────┘       └─────────────┘
```

---

## 2. Planned System Components & Responsibilities

### Component 1: Frontend Presentation Client
- **Technologies:** Semantic HTML5, Vanilla CSS3, Modern ES6+ JavaScript.
- **Responsibilities:**
  - Render user-facing views (Dashboard, Image Upload, Detection Results, Inspection History).
  - Handle client-side file selection, format validation, and immediate preview via `FileReader`.
  - Transmit asynchronous HTTP requests (`fetch`) with multipart image payloads.
  - Dynamically update the DOM to display side-by-side original and annotated images, detected distress metrics, and property estimates.
  - Optionally render defect distribution charts using Chart.js.

### Component 2: Backend API & Service Layer
- **Technologies:** Python 3.10+, Flask.
- **Responsibilities:**
  - Expose versioned REST API endpoints (e.g. `POST /api/inspect`, `GET /api/history`, `POST /api/reports`).
  - Enforce server-side file format verification (JPG, PNG, WEBP), file size checks (<= 15 MB), and stream validation.
  - Orchestrate data flow between image preprocessing, AI inference, and database layers.
  - Package structured JSON responses containing detected classes, confidence ratings, bounding box coordinates, and defect measurements.

### Component 3: Vision Preprocessing & Overlay Engine
- **Technologies:** OpenCV (`opencv-python`), NumPy.
- **Responsibilities:**
  - Decode incoming byte streams into BGR NumPy arrays.
  - Inspect image dimensionality, channel count, and color space integrity.
  - Format, normalize, and resize tensors according to the selected model's input requirements.
  - Render visual overlays (bounding boxes, polygons, or masks) and defect labels strictly derived from verified model coordinates.

### Component 4: AI Defect Detection Engine
- **Technologies:** Selected Computer-Vision Model (e.g. YOLO, Mask R-CNN), PyTorch (conditional).
- **Responsibilities:**
  - Ingest preprocessed tensors and execute authentic neural network inference.
  - Detect road surface defects specifically categorized as **potholes** and **cracks** (longitudinal, transverse, alligator).
  - Produce raw output tensors containing class IDs, confidence scores, and bounding box coordinates `[x1, y1, x2, y2]` or segmentation masks.
  - Return clean empty lists when no defects are detected (no synthetic detections).

### Component 5: Persistence Layer
- **Technologies:** SQLite, Python standard `sqlite3`.
- **Responsibilities:**
  - Store inspection metadata (inspection ID, timestamp, image file paths, model version).
  - Store individual defect records (defect type, confidence score, bounding coordinates, estimated dimensions).
  - Provide query interfaces for retrieving historical surveys and filtering by distress type or date.

### Component 6: Document Reporting Engine
- **Technologies:** ReportLab.
- **Responsibilities:**
  - Retrieve stored inspection data and compiled imagery from disk/database.
  - Programmatically assemble professional PDF summaries including side-by-side imagery, tabular defect details, and structural engineering disclaimers.
  - Serve downloadable PDF streams to the client browser.

---

## 3. Inter-Component Communication Protocols

| Source Component | Target Component | Protocol / Medium | Payload Description |
| :--- | :--- | :--- | :--- |
| **Frontend Client** | **Flask API** | HTTP POST (`multipart/form-data`) | Raw image binary stream and optional metadata parameters. |
| **Flask API** | **Frontend Client** | HTTP 200 OK (`application/json`) | Structured detection results (classes, confidence, coordinates, dimensions). |
| **Flask API** | **Vision Engine** | In-Memory MemoryView / NumPy Array | Decoded image bytes passed directly to OpenCV routines. |
| **Vision Engine** | **AI Model Engine** | PyTorch / NumPy Tensor | Standardized, normalized input tensor formatted to model resolution. |
| **AI Model Engine** | **Vision Engine** | Python Dictionaries / Tensors | Raw detection vectors containing bounding coordinates, scores, and labels. |
| **Flask API** | **SQLite Database** | Python DB-API 2.0 (SQL Queries) | Parameterized SQL statements for inserting and retrieving inspection records. |
| **Flask API** | **ReportLab Engine** | Internal Python Function Calls | Dict of inspection records and file paths used to compile PDF documents. |

---

## 4. Current Repository Structure Verification

The current repository layout establishes clean foundation boundaries for these components:

```text
visionGuard/
├── app/                                # Application package
│   ├── main.py                         # Application entry point
│   ├── components/                     # Presentation views & components
│   ├── pages/                          # Multi-page views (.gitkeep)
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
├── tests/                              # Automated test suite
└── docs/                               # Phase 1 documentation
```

*Note:* In Phase 4 and Phase 5, the web templates and static assets (CSS/JS) will be placed inside `app/` in alignment with standard Flask application conventions.

---

## 5. Architectural Guardrails

1. **No Application Logic Implemented in Phase 1:** All components described above represent future technical designs.
2. **Decoupled Responsibilities:** Model inference is strictly isolated from presentation logic; web routes do not contain neural network layers directly.
3. **Deterministic Visualisation:** The visual overlay engine renders bounding boxes exclusively from genuine model coordinates.
4. **Safety Disclaimers Enforced:** The reporting and display engines must clearly present model confidence as a statistical score, not an indicator of physical structural stability.
