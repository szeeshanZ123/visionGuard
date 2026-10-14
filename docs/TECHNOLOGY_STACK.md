# VisionGuard AI --- Confirmed Technology Stack

**Status:** Confirmed. The frontend uses plain HTML5, CSS3, and JavaScript, and the backend uses Python with Flask.

## Confirmed Technology Summary

-------------------------------------------------------------------------------------------------------
Technology              Intended role                           Status & Notes
----------------------- --------------------------------------- ---------------------------------------
HTML5                   Semantic structure & page layout        Confirmed frontend core

CSS3                    Styling, responsive design, animations  Confirmed frontend styling

JavaScript (ES6+)       Interactivity, file upload, API fetch   Confirmed frontend client logic

Chart.js                Optional dashboard charts               Optional, for analytics phase

Python                  Main backend programming language       Confirmed backend core

Flask                   Web server, routing, REST API endpoints Confirmed backend framework

OpenCV                  Image processing & overlay rendering    Confirmed vision library

PyTorch / runtime       Deep-learning inference engine          Conditional; only if required by model

Pandas                  Tabular processing and data aggregation Confirmed utility

SQLite                  Local relational database storage       Confirmed local persistence

ReportLab               PDF report generation                   Confirmed for reporting phase

Gemini / LLM            Optional natural-language explanations  Optional; must not invent detections
-------------------------------------------------------------------------------------------------------

## Component Details

### Frontend Stack

- **HTML5:** Provides clean, accessible semantic markup for all pages and forms.
- **CSS3:** Delivers responsive styling, modern layout management (Flexbox/Grid), visual feedback, and clear presentation.
- **JavaScript (Vanilla ES6+):** Manages user interactions, client-side image file reading (`FileReader`), asynchronous HTTP communication with Flask endpoints using `fetch()`, DOM updates, and error handling.
- **Chart.js:** An optional lightweight charting library used only when visualizing inspection trends or class distributions on the dashboard.

*Explicit Decision:* Heavy single-page application (SPA) frameworks such as React, Next.js, and Vue are not used. They introduce unnecessary build complexity and tooling overhead for a student-developer project.

### Backend Stack

- **Python:** Chosen as the primary language due to its rich ecosystem for computer vision, machine learning, and data engineering.
- **Flask:** Serves as the web framework and microservices coordinator. It exposes standard RESTful HTTP endpoints (e.g. `/api/inspect`, `/api/history`, `/api/reports`) and renders HTML templates.
- **OpenCV (`opencv-python`):** Handles image loading, dimension inspection, color conversion, preprocessing, and drawing visual overlays (boxes or masks) derived strictly from genuine model outputs.
- **PyTorch (or ONNX / TensorFlow Lite):** A deep-learning inference runtime added only if the selected defect-detection model requires it. Model selection is deferred to Phase 2.
- **Pandas:** Utility library for structuring tabular inspection history and aggregating metrics.
- **SQLite:** Built-in lightweight relational database that requires no standalone daemon, ideal for local inspection logging and internal complaint tracking.
- **ReportLab:** Standard Python library for compiling inspection records and annotated imagery into downloadable PDF documents.

### AI Integration

- **Defect Detection Model:** A genuine computer-vision model tailored for supported infrastructure distress classes (such as potholes and road cracks). The exact model architecture, weights, and runtime are evaluated and chosen in Phase 2.
- **Generative AI (Gemini / LLM):** If used, limited strictly to formatting or providing plain-language summaries of verified inspection records. It must never fabricate predictions, confidence values, or bounding coordinates.

## Evaluated and Rejected Alternatives

1. **Streamlit (Rejected):**
   - *Initial consideration:* Streamlit was evaluated in early scoping for rapid prototyping.
   - *Reason for rejection:* Streamlit tightly couples the user interface with execution state and obscures client-server interactions. Transitioning to plain HTML5/CSS3/JavaScript with a Flask backend provides full control over the UI, clean separation of concerns via standard REST APIs, and a more realistic, extensible web architecture.

2. **React / Next.js / Vue (Rejected):**
   - *Reason for rejection:* Adding a Node.js build system, packaging pipelines, and heavy client-side dependencies creates unnecessary complexity for a student project. Plain HTML, CSS, and vanilla JavaScript achieve all required interactivity with zero client build steps.

## Selection Principles

1. Choose tools that maintain a clear separation between frontend presentation and backend intelligence.
2. Install dependencies only when the relevant phase begins (e.g., ReportLab only during the reporting phase).
3. Do not promise bounding boxes or masks if the chosen model only supports classification.
4. Keep the architecture lightweight, modular, and maintainable.
