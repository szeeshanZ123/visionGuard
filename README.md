# VisionGuard AI

AI-powered infrastructure defect detection and reporting --- project workspace.

## Project Focus

The primary goal is computer-vision-based detection of supported infrastructure defects from images (such as potholes and road cracks). Reports, analytics, and complaint management are supporting modules.

## Documentation

- `docs/PRD.md` --- product requirements and guardrails
- `docs/FEATURES.md` --- feature priorities and acceptance criteria
- `docs/PROJECT_OVERVIEW.md` --- problem, solution, target users, and boundaries
- `docs/TECHNOLOGY_STACK.md` --- proposed technologies and rationale
- `docs/SYSTEM_ARCHITECTURE.md` --- high-level data flow and subsystem boundaries
- `docs/DEVELOPMENT_ROADMAP.md` --- 13-phase implementation roadmap
- `docs/DATASET_AND_MODEL_RESEARCH.md` --- model and dataset selection checklist
- `docs/TESTING_STRATEGY.md` --- testing and evaluation plan

## Repository Structure

The project structure directly follows the starter template specification:

```text
VisionGuard-AI/
├── README.md                           # Documentation, setup & run guide
├── requirements.txt                    # Project dependencies
├── .gitignore                          # Git exclusions for models, DBs, uploads
├── .env.example                        # Environment variables template
├── docs/                               # Core planning & architecture docs
│   ├── PRD.md
│   ├── FEATURES.md
│   ├── PROJECT_OVERVIEW.md
│   ├── TECHNOLOGY_STACK.md
│   ├── SYSTEM_ARCHITECTURE.md
│   ├── DEVELOPMENT_ROADMAP.md
│   ├── DATASET_AND_MODEL_RESEARCH.md
│   └── TESTING_STRATEGY.md
├── app/                                # Streamlit application layer
│   ├── main.py                         # Application entry point
│   ├── components/                     # UI components (landing, upload)
│   ├── pages/                          # Multi-page views
│   └── services/                       # Orchestration services
├── ai/                                 # Computer vision & neural net subsystem
│   ├── preprocessing/                  # Ingestion, validation, tensor formatting
│   ├── detection/                      # Authentic model inference service
│   └── models/                         # Model weights and artifacts
├── database/                           # Persistence and schema management
│   ├── db.py                           # SQLite connection and migration logic
├── data/                               # Data storage
│   ├── uploads/                        # User-uploaded inspection imagery
│   ├── processed/                      # Preprocessed tensors and annotations
│   ├── datasets/                       # Research and evaluation sets
│   └── sample_road.jpg                 # Sample image for testing
├── reports/                            # Generated inspection PDF exports
├── assets/                             # Static visual assets
└── tests/                              # Automated test suite
    ├── test_app_structure.py           # Starter compliance & import tests
    ├── test_db.py                      # Database schema and health tests
    ├── test_image_ops.py               # Preprocessing validation tests
    └── test_streamlit_app.py           # Streamlit AppTest integration tests
```

## Safety and Quality Principles

- **Authentic AI inference**: Do not fabricate model predictions or mock bounding boxes.
- **Confidence vs. severity**: Confidence is not defect severity.
- **Engineering limits**: A photograph alone does not certify structural safety.
- **Data hygiene**: Check model/dataset licences and evaluate performance on a held-out test set.
- **Security**: Never commit real credentials or private user images.

## Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Tests
```bash
python -m pytest -v
```

### 3. Launch Streamlit Application
```bash
streamlit run app.py
```
*(or `streamlit run app/main.py`)*