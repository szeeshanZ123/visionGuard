# VisionGuard AI --- Product Requirements Document (PRD)

**Document status:** Draft for planning and approval\
**Project phase:** Planning only --- implementation has not started\
**Version:** 1.1

## 1. Project Overview

VisionGuard AI is a proposed computer-vision web application for identifying supported infrastructure defects from images and helping users document inspections and follow up on reported issues.

The first target domain is road infrastructure. Candidate defect classes include potholes and road cracks, but the final classes will depend on the availability, licensing, quality, and evaluation results of suitable datasets and models.

The primary product capability is genuine AI-based defect detection. Inspection records, PDF reports, analytics, and complaint management are supporting capabilities.

The confirmed implementation stack pairs a lightweight, accessible frontend (**HTML5, CSS3, and JavaScript**) with a robust backend (**Python and Flask**).

## 2. Problem Statement

Infrastructure defects can be difficult and time-consuming to document consistently through manual inspection alone. Public works and inspection teams need a structured, accessible web tool to review images, record findings, and keep inspection information organised.

VisionGuard AI aims to assist this workflow by analysing images with a suitable computer-vision model and presenting its outputs in a clear, reviewable format. It is an inspection-support tool, not a replacement for qualified engineering assessment.

## 3. Proposed Solution

The application workflow is designed as follows:

1. **Web Interface**: The user opens the web application built with plain HTML5, CSS3, and JavaScript.
2. **Image Ingestion**: The user uploads an infrastructure image.
3. **HTTP Request**: JavaScript transmits the image to a Flask API endpoint using an asynchronous HTTP POST request (`multipart/form-data`).
4. **Validation & Preprocessing**: Flask validates the image (format, dimensions, file size, integrity) and passes it to the image-processing (OpenCV) and AI inference components.
5. **Model Inference**: The selected computer-vision model returns genuine detection results.
6. **Structured Response**: Flask returns structured JSON containing the supported detection classes, confidence scores, and bounding coordinates or segmentation masks when available from the model.
7. **Visualisation**: JavaScript displays the detection metrics, summary data, and the OpenCV-annotated image.
8. **Supporting Modules**: In later phases, Flask coordinates database persistence (SQLite), inspection history, PDF report generation (ReportLab), dashboard analytics (optional Chart.js), and internal complaint management.

Gemini or another language model may be considered for optional explanations or report wording. It must not invent detections, coordinates, or confidence scores. Detection values must originate strictly from the actual computer-vision model.

## 4. Objectives

1. Build a usable image-based infrastructure inspection workflow using standard web technologies (HTML, CSS, JS, and Flask).
2. Integrate and evaluate a suitable defect-detection model.
3. Visualise genuine model outputs clearly without simulated predictions.
4. Persist inspection records and retrieve them reliably via Flask and SQLite.
5. Generate downloadable reports that accurately reflect saved results.
6. Add complaint tracking and authority review only after the core inspection workflow works.
7. Document performance, limitations, privacy considerations, and setup instructions.

## 5. Target Users

- **Inspectors or field users:** Upload images and record inspections.
- **Reviewers or supervisors:** Review inspection results and reports.
- **Authority staff:** In a later phase, review internal complaints and update statuses.
- **Project demonstrators or evaluators:** Review the workflow, model evaluation, and limitations.

The first prototype uses a single-user workflow. Authentication and role-based access should be added when required by the chosen deployment and complaint workflow.

## 6. Scope and Priorities

### In scope for the core version

- Image upload and client/server validation.
- Flask API endpoint for image processing and inference.
- Computer-vision inference using a selected model.
- Genuine class labels, confidence scores, and supported localisation outputs.
- Annotated image visualisation (OpenCV overlays based on real coordinates).
- Saving and retrieving inspection records in SQLite.
- Downloadable PDF inspection reports.

### Later or optional scope

- Dashboard analytics and charts (Chart.js).
- Optional location metadata.
- Internal complaint creation and status tracking.
- Authority dashboard and role-based access control.
- Video or live-camera analysis.
- Additional defect classes or infrastructure types.

### Out of scope unless separately validated

- Certifying structural safety from a photograph.
- Automatically determining engineering-grade defect severity from confidence scores.
- Guaranteeing that an external authority has received a complaint without a real, verified submission integration.
- Claiming support for defect classes that have not been tested.

## 7. Planned Frontend Views

The user interface will provide the following planned views (these are planned views, not implemented pages, and may later be combined or reorganised if that keeps the application simpler):

1. **Dashboard**: High-level system overview, recent inspection metrics, and quick actions.
2. **AI Inspection / Image Upload**: File uploader, image preview, guidelines, and ingestion status.
3. **Detection Results**: Side-by-side display of original and annotated images, detected distress classes, and confidence ratings.
4. **Inspection History**: Searchable and filterable log of past inspections.
5. **Inspection Details**: Detailed view of an individual inspection with metadata and coordinates.
6. **Reports**: Configurable PDF report generation and download.
7. **Complaint Management**: Internal submission and lifecycle tracking for civic defect complaints.
8. **Authority Dashboard**: Restricted interface for reviewing complaints and updating maintenance/repair statuses.

## 8. Functional Requirements

-------------------------------------------------------------------------
ID      Requirement                                             Priority
------- ------------------------------------------------------- ---------
FR-01   Accept supported image formats and reject invalid or    P0
        unsupported files with a clear message.                 

FR-02   Run the selected computer-vision model on a valid       P0
        image via a Flask API endpoint.                         

FR-03   Show genuine detections, including class, confidence,   P0
        and localisation when supported by the model.           

FR-04   Handle images with no detections without fabricating    P0
        results.                                                

FR-05   Display an annotated image whose overlays match actual  P0
        model outputs.                                          

FR-06   Save and retrieve inspection metadata and detection     P1
        results using SQLite.                                   

FR-07   Generate a downloadable PDF report based on saved       P1
        inspection data using ReportLab.                        

FR-08   Filter or search inspection history.                    P1

FR-09   Summarise inspection records with basic charts (using   P2
        Chart.js) and counts.                                   

FR-10   Allow a user to create an internal complaint linked     P2
        to an inspection.                                       

FR-11   Allow authorised users to review complaints and update  P2
        their statuses.                                         

FR-12   Record location metadata when it is provided and        P2
        appropriate.                                            
-------------------------------------------------------------------------

## 9. Non-Functional Requirements

- **Usability:** Keep the workflow understandable for a student developer and first-time user using clean HTML, CSS, and JS.
- **Reliability:** Invalid files, missing model files, and inference failures should produce clear JSON error messages.
- **Maintainability:** Separate frontend presentation, Flask routing/services, model inference, image processing, persistence, and reporting responsibilities.
- **Performance:** Record inference time and avoid unnecessary image copies or repeated model loading.
- **Privacy:** Explain how uploaded images are stored and provide a way to remove local records when appropriate.
- **Security:** Never commit API keys, credentials, private images, or environment files to version control.
- **Traceability:** Store model and version information with inspection results when feasible.
- **Honesty:** Clearly label model-generated results and known limitations; do not imply that predictions are guaranteed to be correct.

## 10. Confirmed Technology Stack

The technology stack has been confirmed to use standard web technologies for full control and simplicity:

-----------------------------------------------------------------------------------------------------------------
Technology              Role                                    Status
----------------------- --------------------------------------- -------------------------------------------------
HTML5, CSS3, JavaScript Web frontend presentation & interaction Confirmed core frontend

Chart.js                Optional dashboard charts               Optional, for analytics phase

Python                  Backend programming language            Confirmed core backend

Flask                   Web framework, routing, REST API        Confirmed core backend

OpenCV                  Image processing & overlay rendering    Confirmed vision library

PyTorch / compatible    Deep learning model runtime             Conditional, only if required by selected model

Pandas                  Tabular processing and data aggregation Confirmed utility

SQLite                  Local relational database               Confirmed local storage

ReportLab               PDF report generation                   Confirmed for reporting phase

Gemini / LLM            Optional natural-language summaries     Optional; must not invent detections
-----------------------------------------------------------------------------------------------------------------

### Technology Decisions & Exclusions

- **Frontend choice:** Plain HTML5, CSS3, and JavaScript were chosen to provide full architectural flexibility, transparent HTTP communication with Flask, and clean DOM manipulation without framework overhead.
- **Streamlit evaluation:** Streamlit was initially evaluated as a rapid prototyping alternative, but was rejected in favor of Flask + HTML/CSS/JS to establish a standard client-server separation and customizable UI.
- **SPA frameworks:** React, Next.js, and Vue were explicitly excluded to avoid unnecessary build toolchains and dependencies for a student developer project.

## 11. High-Level Architecture

### Data Flow

```text
[Browser: HTML/CSS/JS]
       │
       │  1. HTTP POST (multipart image upload)
       ▼
[Flask Route: /api/inspect]
       │
       │  2. Format, dimension & integrity checks
       ▼
[Preprocessing: OpenCV]
       │
       │  3. Model-specific tensor preparation
       ▼
[AI Model Inference Engine]
       │
       │  4. Genuine detection classes, confidence, coordinates
       ▼
[Overlay Generator: OpenCV]
       │
       │  5. Annotated visual output
       ▼
[Flask Response]
       │
       │  6. Structured JSON + annotated image reference
       ▼
[Browser: HTML/CSS/JS] ── Displays results, metrics & overlay
       │
       │  7. (Later) Save inspection, request PDF, view history
       ▼
[Flask Database & Services] ── SQLite & ReportLab
```

### Proposed Target Folder Structure

```text
VisionGuard-AI/
├── app/
│   ├── templates/                      # HTML5 templates (Dashboard, Upload, Results, etc.)
│   ├── static/                         # Static assets
│   │   ├── css/                        # CSS stylesheets
│   │   ├── js/                         # JavaScript client files
│   │   └── images/                     # Static assets and icons
│   ├── routes/                         # Flask blueprints and API endpoints
│   └── services/                       # Application services (inspection, reports)
├── ai/
│   ├── models/                         # Model weights and artifacts
│   ├── detection/                      # Inference engine
│   └── preprocessing/                  # Ingestion, validation, OpenCV routines
├── database/                           # SQLite database connection and queries
├── data/                               # Uploads, processed images, datasets
├── reports/                            # Generated inspection PDF documents
├── tests/                              # Automated test suite
└── docs/                               # Project documentation
```

> **Note on structure:** This is a proposed target structure. Do not automatically create, move, rename, or delete folders during documentation updates. Any physical restructuring will be considered separately.

## 12. Dataset and Model Requirements

Before selecting a model:

1. Identify datasets relevant to the intended defect classes (road potholes, cracks) and image conditions.
2. Check licensing, permitted use, dataset provenance, labels, and annotation format.
3. Review class balance, image resolution, duplicate images, and label quality.
4. Compare suitable pretrained models and their runtime requirements.
5. Verify whether the model supports classification, object detection, or segmentation. Do not promise bounding boxes if the model does not produce them.
6. Establish a representative held-out test set and a reproducible evaluation procedure.
7. Document known limitations and conditions where the model may fail.

Evaluate appropriate metrics such as precision, recall, and mAP for object detection, plus inference time. Model confidence is not defect severity.

## 13. Data and Persistence

Potential inspection fields in SQLite include:

- Inspection ID (primary key).
- Timestamp.
- Original image path or managed image reference.
- Model name and version.
- Detection class.
- Confidence score.
- Bounding box or other localisation output, if supported.
- Processing duration.
- Optional location metadata.
- Report path, if generated.

Complaint records may later include a complaint ID, linked inspection ID, description, status, timestamps, and authorised reviewer information.

## 14. Security and Privacy

- Keep secrets in local environment variables or a secrets manager.
- Commit `.env.example`, never real `.env` files.
- Validate uploads on the Flask backend and enforce maximum file-size limits.
- Restrict access to uploaded images and reports when the app is deployed.
- Avoid committing datasets, private images, generated databases, or model weights.
- Add authentication and role-based access before exposing authority workflows publicly.
- Do not send images to third-party services unless the user understands and accepts that data flow.

## 15. Limitations and Risks

- A model may miss defects or incorrectly label ordinary road features (e.g. shadows, oil stains).
- Performance may vary with lighting, weather, camera angle, distance, resolution, and road surface.
- A dataset may not represent the locations where the application is used.
- Bounding boxes indicate image regions, not physical measurements.
- Confidence scores do not establish severity or structural safety.
- Complaint routing requires verified jurisdiction data.

## 16. Success Metrics

- The Flask API accepts valid images and rejects invalid inputs with descriptive JSON errors.
- Every displayed detection corresponds to an actual model output.
- Precision, recall, and mAP are measured on a held-out test set.
- Inference time and hardware requirements are recorded.
- Inspection records can be saved and retrieved from SQLite without data mismatch.
- Generated ReportLab PDF reports match stored inspection results.
- End-to-end client-server workflows pass documented tests.

## 17. Testing Strategy

- **Input tests:** Valid, unsupported, corrupted, and oversized images tested against Flask endpoints.
- **Inference tests:** Known test images, no-detection cases, and model-load failures.
- **Visualisation tests:** Verify that displayed overlays match returned coordinates.
- **Persistence tests:** Save, retrieve, filter, and delete inspection records.
- **Report tests:** Confirm that generated reports contain correct stored values.
- **Workflow tests:** Test the complete inspection process from HTML/JS upload to Flask API response and report.
- **Model evaluation:** Use a held-out set and document false positives and false negatives.
- **Security checks:** Check secrets, upload validation, and access control.

## 18. Current Status and Next Action

**Current status: Planning only.** The technology stack has been clarified to HTML/CSS/JS frontend with Flask backend. No application code, model, dataset, or database has been implemented as part of this plan.

The immediate next step is to review the updated project documentation. After approval, research suitable datasets and models before committing to an implementation design.
