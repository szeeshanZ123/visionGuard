# VisionGuard AI --- Technology Stack Specification

**Document Status:** Approved Technical Baseline  
**Project Phase:** Phase 1 --- Project Foundation & Documentation Only  
**Architecture Status:** Planned Architecture (Not a currently working implementation)  
**Version:** 1.2  

---

## 1. Overview of Technology Choices

VisionGuard AI pairs a lightweight, framework-free frontend with a modern Python computer-vision backend. The selection is guided by three engineering principles:
1. **Separation of Concerns:** Clear client-server decoupling via standard HTTP REST APIs.
2. **Student-Developer Accessibility:** Minimal external dependencies, standard toolchains, and zero client-side compilation steps.
3. **Domain Fitness:** Leveraging Python's premier ecosystem for computer vision and machine learning alongside standards-compliant web technologies.

---

## 2. Component Justification & Roles

### A. Frontend Layer

| Technology | Role | Justification & Appropriateness |
| :--- | :--- | :--- |
| **HTML5** | Semantic Page Structure | Provides standard, accessible markup for forms, file inputs, comparison containers, and modal dialogs without framework overhead. |
| **CSS3** | Responsive Styling & Layout | Delivers responsive grid and flexbox layouts, visual indicators, and micro-interactions with pure vanilla CSS. Avoids framework lock-in. |
| **Vanilla JavaScript (ES6+)** | Client Interactivity & API Communication | Manages DOM events, client-side file reading (`FileReader`), asynchronous HTTP `fetch` requests, error handling, and dynamic result rendering without node_modules overhead. |
| **Chart.js** *(Optional)* | Frontend Analytics | Lightweight canvas-based charting library selected only for rendering optional defect distribution summaries and historical trend lines. |

*Explicit Decision:* Frameworks such as React, Next.js, Vue, or Angular are **strictly excluded**. They add build toolchains, node dependencies, and unnecessary complexity. Streamlit is also excluded to preserve clean RESTful API separation.

---

### B. Backend Layer

| Technology | Role | Justification & Appropriateness |
| :--- | :--- | :--- |
| **Python 3.10+** | Core Backend Language | Universal standard for computer vision, scientific computing, deep learning inference, and backend automation. |
| **Flask** | Web Server & REST API Framework | Minimalist WSGI micro-framework that excels at serving RESTful JSON endpoints and static files with clear, readable routing. |
| **OpenCV (`opencv-python`)** | Image Preprocessing & Visualisation | High-performance C++ backend exposed to Python for array decoding, dimension checks, tensor resizing, and drawing genuine detection overlays. |
| **PyTorch** *(Conditional)* | Deep Learning Runtime | Industrial standard for executing convolutional neural networks and transformer-based vision models. Included only if the selected model requires it. |
| **SQLite** | Local Relational Database | Zero-configuration, serverless, self-contained SQL database engine ideal for persisting inspection records and defect logs locally. |
| **Pandas** | Tabular Data Handling | High-performance data manipulation library for aggregating historical inspection metrics and defect distributions. |
| **ReportLab** | PDF Report Compilation | Robust Python library for programmatically generating clean, printable inspection documentation and audit reports. |

---

### C. Artificial Intelligence & Computer Vision

| Component | Responsibility | Guardrails & Requirements |
| :--- | :--- | :--- |
| **Defect Detection Model** | Pothole & Crack Detection | A genuine object-detection (e.g. YOLO, Faster R-CNN) or instance segmentation (e.g. Mask R-CNN) model selected during Phase 2/3. |
| **Gemini / LLM** *(Optional)* | Natural-Language Explanations | May be considered for summarizing verified inspection numbers into plain-language text; **strictly prohibited** from fabricating defect predictions. |

---

## 3. End-to-End Data Flow

The planned frontend-to-backend lifecycle executes as follows:

```text
[ Browser (HTML5 / CSS3 / Vanilla JavaScript) ]
                        │
                        │  1. User selects image; JS generates client-side preview
                        │  2. JS sends multipart/form-data via HTTP POST
                        ▼
             [ Flask REST API (/api/inspect) ]
                        │
                        │  3. Server validates format, dimensions, file size
                        ▼
         [ Image Preprocessing Pipeline (OpenCV) ]
                        │
                        │  4. Decodes image into BGR array; checks tensor validity
                        │  5. Formats input tensor to model specifications
                        ▼
        [ Computer Vision Model Inference Engine ]
                        │
                        │  6. Runs authentic inference on tensor
                        │  7. Returns classes, confidence scores, coordinates/masks
                        ▼
       [ Visualisation & Overlay Engine (OpenCV) ]
                        │
                        │  8. Draws bounding boxes/masks strictly from real coordinates
                        ▼
         [ Flask JSON Response Construction ]
                        │
                        │  9. Packages structured JSON (detections, metrics, overlay ref)
                        ▼
[ Browser Display (HTML / CSS / DOM Update) ]
                        │
                        │  10. JS renders side-by-side images, metrics table, and details
                        ▼
  [ Database & Reporting (SQLite & ReportLab) ]
                        │
                        │  11. Inspection persisted to SQLite (later phase)
                        │  12. PDF inspection report compiled on demand (later phase)
```

> [!IMPORTANT]
> The workflow detailed above is the **planned target architecture**. In accordance with Phase 1 constraints, no Flask routes or active model pipelines are currently running.
