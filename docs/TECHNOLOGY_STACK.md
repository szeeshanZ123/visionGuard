# VisionGuard AI 2.0 — Technology Stack Specification

**Document Status:** Approved Technical Baseline  
**Project Phase:** Phase 6 — Production System & Multimodal Defect Detection Deployed  
**Architecture Status:** Fully Functional Production Architecture (81 Passing Automated Tests)  
**Version:** 2.0  

---

## 1. Overview of Technology Choices

VisionGuard AI 2.0 pairs a responsive, framework-free frontend with a modern Python multimodal computer-vision backend. The selection is guided by three engineering principles:
1. **Separation of Concerns:** Clear client-server decoupling via standard HTTP REST APIs.
2. **Student-Developer Accessibility & Maintainability:** Zero node_modules build overhead; all client assets run natively in standard modern web browsers.
3. **Domain Fitness & Production Reliability:** Leveraging Google's official Gen AI SDK for multimodal defect analysis, OpenCV for non-destructive visual annotations, and lightweight relational persistence.

---

## 2. Component Justification & Roles

### A. Frontend Layer

| Technology | Role | Justification & Appropriateness |
| :--- | :--- | :--- |
| **HTML5** | Semantic Page Structure | Provides standard, accessible markup for inspection forms, image dropzones, side-by-side comparison containers, and action modals without framework overhead. |
| **Tailwind CSS & Vanilla CSS3** | Responsive Styling & Layout | Delivers responsive grid and flexbox layouts, visual indicators, micro-interactions, and high-contrast color-coded severity badges. |
| **Vanilla JavaScript (ES6+)** | Client Interactivity & API Communication | Manages DOM events, client-side file reading (`FileReader`), asynchronous HTTP `fetch` requests, error handling, progress steppers, and dynamic result rendering without node dependencies. |
| **Leaflet.js & OpenStreetMap** | Geospatial Distress Mapping | Lightweight, mobile-friendly interactive mapping library plotting geocoded civic distress locations with urgency-coded marker pins and summary popups. |

*Explicit Decision:* Heavy single-page frameworks (React, Angular, Vue) are strictly excluded to avoid build-pipeline fragility, heavy dependencies, and unnecessary client bundling.

---

### B. Backend Layer

| Technology | Role | Justification & Appropriateness |
| :--- | :--- | :--- |
| **Python 3.10+ / 3.14** | Core Backend Language | Universal standard for scientific computing, computer vision, AI model orchestration, and backend REST automation. |
| **Flask (v3.1+)** | Web Server & REST API Framework | Minimalist WSGI micro-framework serving RESTful JSON endpoints, session management, and CSRF protection with clear, auditable routing. |
| **OpenCV (`opencv-python`)** | Image Preprocessing & Visualisation | High-performance C++ backend exposed to Python for array decoding, dimension checks, resolution safety clamping, and drawing genuine detection overlays. |
| **SQLite** | Local Relational Database | Zero-configuration, serverless, self-contained SQL database engine ideal for persisting inspection records and defect logs locally (`data/visionguard.db`). |
| **Neon PostgreSQL** | Cloud Relational Database | Serverless PostgreSQL backend for production deployments, supported seamlessly via `DATABASE_URL` with connection pooling and SSL encryption. |
| **ReportLab (v4.x)** | PDF Report Compilation | Robust Python library for programmatically generating clean, printable municipal complaint notices and audit reports. |
| **Waitress / Gunicorn** | Production WSGI Servers | Production-grade WSGI servers: Waitress for multi-threaded Windows execution, Gunicorn for Linux / Render cloud hosting. |

---

### C. Artificial Intelligence & Computer Vision

| Component | Responsibility | Guardrails & Requirements |
| :--- | :--- | :--- |
| **Google Gemini Multimodal Vision** | Primary Visual Defect Detection & Severity Analysis | Utilizes Google's official `google-genai` SDK (`gemini-3.1-flash-lite`) for multi-defect identification, normalized bounding box estimation, visual evidence extraction, and safety guidance across road and building domains. |
| **OpenCV Visual Annotation Engine** | Non-Destructive Image Overlays | Renders high-contrast bounding boxes, defect IDs (`[D001]`), labels, and color-coded severity pills directly onto a memory copy of the image, keeping original photograph untouched. |
| **Archived Research Weights** | Historical Baseline & Offline Benchmarking | Preserved local weights (`ai/models/best.pt`, `ai/models/home_best.pt`) kept in read-only isolation for historical ablation studies and future edge-model research; bypassed in active citizen detection. |

---

## 3. End-to-End Data Flow

The complete frontend-to-backend inspection lifecycle executes as follows:

```text
[ Browser (HTML5 / Vanilla JavaScript) ]
                        │
                        │  1. User selects image; JS generates client-side preview
                        │  2. JS sends multipart/form-data via HTTP POST
                        ▼
             [ Flask REST API (/api/inspect) ]
                        │
                        │  3. Server validates format, dimensions, file size (<15MB)
                        ▼
          [ Image Preprocessing Pipeline (OpenCV) ]
                        │
                        │  4. Decodes image into BGR array; checks resolution
                        │  5. Safely clamps oversized images (>1280px) to conserve memory
                        ▼
         [ Google Gemini Vision Engine (google-genai) ]
                        │
                        │  6. Generates structured JSON schema response
                        │  7. Returns defect list, severities, evidence, and normalized boxes
                        ▼
        [ Bounding Box Validation & OpenCV Annotation ]
                        │
                        │  8. Validates coordinates [0.0, 1.0]; converts to pixel bounds
                        │  9. Draws non-destructive bounding boxes, IDs, and severity pills
                        ▼
             [ Flask Structured JSON Response ]
                        │
                        │  10. Packages findings, base64 annotated image, and safety guidance
                        ▼
[ Browser Display (AI Inspection Report & Decision Pathways) ]
                        │
                        │  11. Displays severity badge, defect inventory, and interactive views
                        │  12. Citizen chooses Option A (Read Guidance) or Option B (Submit Complaint)
                        ▼
      [ Database Persistence & PDF Generation ]
                        │
                        │  13. Complaint saved to SQLite / PostgreSQL
                        │  14. ReportLab compiles formal municipal PDF on demand
                        │  15. Geocoded pin plotted on Leaflet.js interactive map
```

---

## 4. Architectural Guardrails & Compliance

1. **Active Engine Clarity:** Google Gemini Vision is the sole active defect detection engine for live citizen inspections. Legacy YOLO models are not active in production.
2. **Preliminary Assessment Notice:** Defect severity is a preliminary visual assessment based on optical evidence. The system makes no claim of structural engineering certification or ASTM regulatory compliance.
3. **Non-Destructive Storage:** Original photographic evidence is preserved verbatim. Visual annotations are generated as separate derivative assets.
4. **Secret Key Isolation:** `GEMINI_API_KEY` is strictly read from environment variables on the backend and is never exposed in client JavaScript or API responses.
