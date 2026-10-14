# VisionGuard AI --- Feature Specification

**Document status:** Draft for planning and approval\
**Project phase:** Planning only --- no features implemented yet\
**Version:** 1.1

## Product Principle

VisionGuard AI's primary feature is **computer-vision-based infrastructure defect detection**. Reports, analytics, and complaint management support that workflow.

The architecture separates a plain **HTML5, CSS3, and JavaScript** frontend from a **Python and Flask** backend. The system must display genuine model outputs. It must not invent classes, coordinates, confidence scores, or external complaint-submission status. Model confidence is not the same as defect severity.

## Planned Frontend Views

The application plans the following user views (which are planned views, not implemented pages, and may later be combined or reorganised to keep the application simpler):

1. **Dashboard**: High-level system overview, recent inspection counts, and system status.
2. **AI Inspection / Image Upload**: File selection, capture guidelines, client-side preview, and upload trigger.
3. **Detection Results**: Side-by-side original and annotated images, detected distress classes, and confidence ratings.
4. **Inspection History**: Tabular view of previous inspections with search and filtering.
5. **Inspection Details**: Detailed view of an individual inspection with metadata and coordinates.
6. **Reports**: Configurable PDF report generation and download.
7. **Complaint Management**: Internal submission and lifecycle tracking for civic defect complaints.
8. **Authority Dashboard**: Restricted interface for reviewing complaints and updating maintenance/repair statuses.

---

## P0 --- Core Features

### P0.1 Image Upload and Validation

**Description:** Allow a user to upload an image of supported infrastructure via the web interface.

**Planned behaviour**
- User selects an image through a standard HTML file input.
- JavaScript previews the image on the client side and sends it to a Flask API endpoint via an HTTP POST request (`multipart/form-data`).
- Flask validates file format (JPG, PNG, WEBP), file size (enforcing max size), and readability.
- Flask returns JSON containing validation status or descriptive error messages.
- The interface displays a clear message if the file is invalid.

**Acceptance criteria**
- A valid supported image can be selected, previewed, and uploaded.
- Unsupported, corrupted, and oversized files are rejected with clear user messages.
- Invalid input is not passed to the model.

### P0.2 AI Defect Detection

**Description:** Run a suitable computer-vision model on a validated image.

**Planned behaviour**
- Flask passes the validated image array to the AI inference component.
- Begin with only the defect classes supported by the selected model and dataset (e.g. potholes, road cracks).
- Return the model's genuine output, including classes, confidence, and localisation coordinates or masks where available.
- Handle inference errors and images with no detections gracefully without crashes.

**Acceptance criteria**
- Results originate from actual model inference.
- No-detection cases are represented honestly in the returned JSON.
- Model and version information can be recorded for traceability.
- Performance is evaluated on a defined test set before accuracy claims are made.

### P0.3 Detection Visualisation

**Description:** Help users understand where the model found a potential defect.

**Planned behaviour**
- OpenCV draws bounding boxes, masks, or overlays on the backend strictly using coordinates returned by the model.
- Flask sends structured JSON and the annotated image to the client.
- JavaScript displays the annotated overlay and side-by-side comparison with the original image.
- Class labels and confidence scores are clearly rendered.

**Acceptance criteria**
- Every visual overlay corresponds to the model's actual coordinates or masks.
- The interface clearly labels results as model predictions.
- Confidence is not described as severity or proof of safety risk.
- Do not promise bounding boxes or masks if the selected model only outputs classification.

### P0.4 Inspection Result Summary

**Description:** Present a readable summary of one inspection.

**Planned behaviour**
- Show the original image and annotated result side by side.
- List detected classes and confidence scores in structured tables/cards.
- Show a suitable no-detection or error state.
- Include model limitations and engineering disclaimers.

**Acceptance criteria**
- Displayed values match the inference output.
- The app does not claim that a photo alone certifies structural safety.

---

## P1 --- Important Features

### P1.1 Inspection History

**Description:** Save and review previous inspections.

**Planned behaviour**
- Store timestamp, image reference, model details, and detection results in SQLite via Flask.
- Provide a history list and inspection detail view.
- Support basic search or filtering by date or defect class.
- Provide appropriate deletion or retention behaviour.

**Acceptance criteria**
- Saved records can be retrieved after an application restart.
- Stored values match the original inspection output.
- Missing images or records produce clear messages.

### P1.2 PDF Inspection Reports

**Description:** Generate a downloadable report for an inspection.

**Planned behaviour**
- Flask uses ReportLab to generate a standardized PDF document.
- Include inspection ID, timestamp, original/annotated imagery, detection details, and disclaimers.
- Download triggered directly from the web browser.

**Acceptance criteria**
- The PDF opens successfully in standard viewers.
- Report values match the stored inspection.
- The report does not invent severity, measurements, or authority actions.

### P1.3 Basic Inspection Analytics

**Description:** Summarise saved inspections.

**Planned behaviour**
- Flask provides aggregated inspection counts and class distributions via a JSON endpoint.
- JavaScript renders dashboard summary cards and optional charts using Chart.js.
- Show trends only when sufficient dated records exist.

**Acceptance criteria**
- Dashboard numbers match the underlying SQLite records.
- Charts distinguish counts from model confidence and any separately validated severity assessment.

---

## P2 --- Additional Features

### P2.1 Location Metadata

**Description:** Associate an inspection with a location when the user supplies it.

**Planned behaviour**
- Make location optional (manual text or coordinate input).
- Record the source of the location when practical.
- Allow correction or removal of inaccurate location data.

**Acceptance criteria**
- The app does not fabricate GPS coordinates or infer an exact location from an image without a valid method.
- Missing location does not prevent image analysis.

### P2.2 Complaint Management

**Description:** Create and track an internal complaint linked to an inspection.

**Planned behaviour**
- Create a complaint from saved inspection details.
- Track statuses: Submitted, Under Review, In Progress, Resolved.
- Store status-change timestamps and relevant notes.
- Keep complaint status distinct from model output.

**Acceptance criteria**
- A complaint links to the correct inspection.
- Status changes are saved and visible in the interface.
- The application does not claim an external authority received the complaint unless a real integration confirms submission.

### P2.3 Authority Dashboard

**Description:** Provide authorised staff with a view for reviewing complaints and updating progress.

**Planned behaviour**
- Display complaint and inspection information.
- Filter by status and other available metadata.
- Allow permitted status updates.
- Introduce authentication and role-based access before production deployment.

**Acceptance criteria**
- Unauthorised users cannot access restricted actions.
- Status changes persist and have an auditable timestamp.
- The dashboard does not assign responsibility to an authority without verified jurisdiction information.

### P2.4 Optional AI-Generated Explanations

**Description:** A language model such as Gemini may help turn verified inspection data into readable text.

**Rules**
- The language model may summarise existing model results.
- It must not create detections, coordinates, confidence scores, measurements, or claims of verified severity.
- Any third-party image or data transfer must be disclosed and controlled.

**Acceptance criteria**
- Explanations are based on actual stored results.
- Unavailable information is stated as unknown.
- Users can distinguish generated wording from model detections.

### P2.5 Future Video or Live-Camera Support

**Description:** Consider analysing video or live-camera input after image-based detection is stable.

**Acceptance criteria**
- This feature is not started until image inference, evaluation, and resource requirements are understood.
- Performance and frame-processing limitations are documented.

---

## Feature Dependencies

1. HTML/JS image upload and Flask validation must work before model inference.
2. Model selection and baseline evaluation must happen before claiming reliable detection.
3. Visualisation depends on the output format of the selected model.
4. Inspection history should be in place before reports and analytics depend on persistent data.
5. Complaint management depends on saved inspections.
6. The authority dashboard depends on complaint tracking and appropriate access controls.
7. Deployment follows end-to-end testing.

## Current Implementation Status

All features in this document are **planned, not implemented**. The immediate task is to review and confirm project documentation. No application code, database, dataset, or model should be created during the planning-only phase.
