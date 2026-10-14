# VisionGuard AI

AI-powered infrastructure defect detection and reporting --- project workspace.

## Project Focus

The primary goal of VisionGuard AI is computer-vision-based detection of supported infrastructure defects from images (such as road potholes and cracks). Inspection history, reports, analytics, and complaint management are supporting modules.

## Confirmed Technology Stack

- **Frontend**: Plain HTML5, CSS3, and JavaScript.
  - Semantic HTML5 for page structure.
  - Vanilla CSS3 for responsive layout and styling.
  - Vanilla JavaScript for user interaction, image previews, asynchronous API requests (`fetch`), and rendering detection results.
  - **Chart.js** (optional) for dashboard summaries and analytics when required.
  - *No heavy frontend frameworks (React, Next.js, Vue) or Streamlit.*
- **Backend**: Python with **Flask**.
  - Flask web server handling routing, API endpoints, and application logic.
  - **OpenCV** for image preprocessing, validation, and detection overlay rendering.
  - **SQLite** for lightweight local persistence of inspection records.
  - **PyTorch** (or another compatible runtime): only if required by the selected computer-vision model.
  - **Pandas**: for tabular processing and analytics where needed.
  - **ReportLab**: for generating downloadable PDF inspection reports.
- **AI Core**:
  - Genuine computer-vision model for supported infrastructure defect classes.
  - Model selection is determined during the dataset and model research phase.
  - Gemini may be considered for optional plain-language explanations, but must not invent detections, coordinates, or confidence scores.

## Application Architecture & Workflow

The core inspection workflow operates as follows:

1. **User opens web application**: Built with HTML5, CSS3, and JavaScript.
2. **User uploads image**: User selects an infrastructure photo via the web interface.
3. **HTTP API Request**: JavaScript sends the image to a Flask API endpoint via an asynchronous HTTP POST request (`multipart/form-data`).
4. **Flask Ingestion & Validation**: Flask validates the image (format, dimensions, size, integrity) and passes it to the preprocessing and AI inference services.
5. **Model Inference**: The selected computer-vision model runs inference and returns genuine detection data.
6. **Structured JSON Response**: Flask returns structured JSON containing detected defect classes, confidence scores, and bounding coordinates or segmentation masks when supported.
7. **Client-side Visualisation**: JavaScript updates the DOM to display detection metrics, summary data, and the OpenCV-annotated image.
8. **Subsequent Capabilities**: In later phases, Flask coordinates database persistence, inspection history retrieval, PDF report downloads, dashboard analytics, and complaint tracking.

## Planned Frontend Views

The user interface will provide the following planned views (which may be consolidated or organized into streamlined views to keep the application simple):

- **Dashboard**: High-level system overview, recent inspections, and key metrics.
- **AI Inspection / Image Upload**: File selection, capture guidelines, and image preview.
- **Detection Results**: Side-by-side original and annotated images, detected distress classes, and confidence ratings.
- **Inspection History**: Searchable and filterable log of past inspections.
- **Inspection Details**: In-depth inspection record with metadata and defect coordinates.
- **Reports**: Configurable and downloadable PDF inspection documentation.
- **Complaint Management**: Internal tracking of civic complaints linked to verified inspections.
- **Authority Dashboard**: Restricted interface for reviewing complaints and updating maintenance/repair statuses.

## Proposed Target Structure

The proposed target directory layout for the Flask + HTML/CSS/JS architecture:

```text
VisionGuard-AI/
├── README.md                           # Project documentation & overview
├── requirements.txt                    # Backend dependencies
├── .env.example                        # Environment variable templates
├── .gitignore                          # Git exclusions for weights, DBs, and uploads
├── docs/                               # Core planning & architecture documentation
│   ├── PRD.md
│   ├── FEATURES.md
│   ├── PROJECT_OVERVIEW.md
│   ├── TECHNOLOGY_STACK.md
│   ├── SYSTEM_ARCHITECTURE.md
│   ├── DEVELOPMENT_ROADMAP.md
│   ├── DATASET_AND_MODEL_RESEARCH.md
│   └── TESTING_STRATEGY.md
├── app/                                # Flask application package
│   ├── templates/                      # HTML5 templates (Dashboard, Upload, Results, etc.)
│   ├── static/                         # Static web assets
│   │   ├── css/                        # Custom CSS stylesheets
│   │   ├── js/                         # Frontend JavaScript modules
│   │   └── images/                     # Static UI assets and icons
│   ├── routes/                         # Flask route blueprints & REST API endpoints
│   └── services/                       # Business logic and coordination services
├── ai/                                 # Computer vision subsystem
│   ├── preprocessing/                  # Input validation, OpenCV decoding, tensor prep
│   ├── detection/                      # Genuine model inference engine
│   └── models/                         # Model weights and artifacts
├── database/                           # Persistence layer
│   └── db.py                           # SQLite schema and query logic
├── data/                               # Data storage
│   ├── uploads/                        # User-uploaded inspection imagery
│   ├── processed/                      # Preprocessed tensors and annotations
│   ├── datasets/                       # Model research and evaluation sets
│   └── sample_road.jpg                 # Sample test asset
├── reports/                            # Generated PDF inspection summaries
├── assets/                             # Repository project assets
└── tests/                              # Automated test suite
```

> **Note**: This is a proposed target structure for future phases. Physical restructuring from any prior layout will be conducted deliberately during the environment and architecture setup phases.

## Safety and Quality Principles

- **Authentic AI inference**: Do not fabricate model predictions or mock bounding boxes.
- **Confidence vs. severity**: Confidence is not defect severity.
- **Engineering limits**: A photograph alone does not certify structural safety.
- **Data hygiene**: Check model/dataset licences and evaluate performance on a held-out test set.
- **Student-developer scope**: Keep architecture modular, lightweight, and maintainable without unnecessary dependencies.
- **Security**: Never commit real credentials or private user images.

## Documentation Index

- [`docs/PRD.md`](docs/PRD.md) --- Product Requirements Document
- [`docs/FEATURES.md`](docs/FEATURES.md) --- Feature specifications and acceptance criteria
- [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) --- Problem, solution, target users, and boundaries
- [`docs/TECHNOLOGY_STACK.md`](docs/TECHNOLOGY_STACK.md) --- Confirmed technology stack and selection rationale
- [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) --- Data flow, Flask API endpoints, and component boundaries
- [`docs/DEVELOPMENT_ROADMAP.md`](docs/DEVELOPMENT_ROADMAP.md) --- 13-phase engineering progression
- [`docs/DATASET_AND_MODEL_RESEARCH.md`](docs/DATASET_AND_MODEL_RESEARCH.md) --- Model and dataset selection checklist
- [`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md) --- Test suite, API testing, and model evaluation plan