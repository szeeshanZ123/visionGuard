# VisionGuard AI --- Feature Specification

**Document status:** Draft for planning and approval\
**Project phase:** Planning only --- no features implemented yet

## Product Principle

VisionGuard AI's primary feature is **computer-vision-based
infrastructure defect detection**. Reports, analytics, and complaint
management support that workflow.

The system must display genuine model outputs. It must not invent
classes, coordinates, confidence scores, or external
complaint-submission status. Model confidence is not the same as defect
severity.

## P0 --- Core Features

### P0.1 Image Upload and Validation

**Description:** Allow a user to upload an image of supported
infrastructure.

**Planned behaviour** - Accept only documented image formats. - Validate
file readability and size. - Show a clear message for invalid files. -
Display the uploaded image before analysis.

**Acceptance criteria** - A valid supported image can be selected and
displayed. - Unsupported, corrupted, and oversized files are handled
gracefully. - Invalid input is not passed to the model.

### P0.2 AI Defect Detection

**Description:** Run a suitable computer-vision model on a validated
image.

**Planned behaviour** - Use a model selected after dataset and runtime
research. - Begin with only the defect classes supported by the selected
model and dataset. - Return the model's real output, including classes
and localisation where available. - Handle inference errors and images
with no detections.

**Acceptance criteria** - Results originate from actual model
inference. - No-detection cases are represented honestly. - Model and
version information can be recorded. - Performance is evaluated on a
defined test set before accuracy claims are made.

### P0.3 Detection Visualisation

**Description:** Help users understand where the model found a potential
defect.

**Planned behaviour** - Draw bounding boxes, masks, or other overlays
only when supported by model output. - Show class labels and confidence
scores. - Allow the user to compare original and annotated images.

**Acceptance criteria** - Every visual overlay corresponds to the
model's actual coordinates or masks. - The interface clearly labels
results as model predictions. - Confidence is not described as severity
or proof of safety risk.

### P0.4 Inspection Result Summary

**Description:** Present a readable summary of one inspection.

**Planned behaviour** - Show the original image and annotated result. -
List detected classes and confidence scores. - Show a suitable
no-detection or error state. - Include model limitations where relevant.

**Acceptance criteria** - Displayed values match the inference output. -
The app does not claim that a photo alone certifies structural safety.

## P1 --- Important Features

### P1.1 Inspection History

**Description:** Save and review previous inspections.

**Planned behaviour** - Store timestamp, image reference, model details,
and detection results. - Provide a history list and inspection detail
view. - Support basic search or filtering. - Provide appropriate
deletion or retention behaviour.

**Acceptance criteria** - Saved records can be retrieved after an
application restart. - Stored values match the original inspection
output. - Missing images or records produce clear messages.

### P1.2 PDF Inspection Reports

**Description:** Generate a downloadable report for an inspection.

**Planned behaviour** - Include inspection ID and timestamp. - Include
the original or annotated image when available. - Include detection
classes, confidence scores, and supported localisation details. -
Include optional location metadata if supplied. - Include a disclaimer
about model limitations.

**Acceptance criteria** - The PDF opens successfully. - Report values
match the stored inspection. - The report does not invent severity,
measurements, or authority actions.

### P1.3 Basic Inspection Analytics

**Description:** Summarise saved inspections.

**Planned behaviour** - Show inspection totals and detected-class
counts. - Show trends only when sufficient dated records exist. -
Provide basic filters where useful.

**Acceptance criteria** - Dashboard numbers match the underlying
records. - Charts distinguish counts from model confidence and any
separately validated severity assessment.

## P2 --- Additional Features

### P2.1 Location Metadata

**Description:** Associate an inspection with a location when the user
supplies it or an approved location source provides it.

**Planned behaviour** - Make location optional. - Record the source of
the location when practical. - Allow correction or removal of inaccurate
location data.

**Acceptance criteria** - The app does not fabricate GPS coordinates or
infer an exact location from an image without a valid method. - Missing
location does not prevent image analysis.

### P2.2 Complaint Management

**Description:** Create and track an internal complaint linked to an
inspection.

**Planned behaviour** - Create a complaint from saved inspection
details. - Track statuses such as Submitted, Under Review, In Progress,
and Resolved. - Store status-change timestamps and relevant notes. -
Keep complaint status distinct from model output.

**Acceptance criteria** - A complaint links to the correct inspection. -
Status changes are saved and visible. - The application does not claim
an external authority received the complaint unless a real integration
confirms submission.

### P2.3 Authority Dashboard

**Description:** Provide authorised staff with a view for reviewing
complaints and updating progress.

**Planned behaviour** - Display complaint and inspection information. -
Filter by status and other available metadata. - Allow permitted status
updates. - Introduce authentication and role-based access where needed.

**Acceptance criteria** - Unauthorised users cannot access restricted
actions. - Status changes persist and have an auditable timestamp. - The
dashboard does not assign responsibility to an authority without
verified jurisdiction information.

### P2.4 Optional AI-Generated Explanations

**Description:** A language model such as Gemini may help turn verified
inspection data into readable text.

**Rules** - The language model may summarise existing model results. -
It must not create detections, coordinates, confidence scores,
measurements, or claims of verified severity. - Any third-party image or
data transfer must be disclosed and controlled.

**Acceptance criteria** - Explanations are based on actual stored
results. - Unavailable information is stated as unknown. - Users can
distinguish generated wording from model detections.

### P2.5 Future Video or Live-Camera Support

**Description:** Consider analysing video or live-camera input after
image-based detection is stable.

**Acceptance criteria** - This feature is not started until image
inference, evaluation, and resource requirements are understood. -
Performance and frame-processing limitations are documented.

## Feature Dependencies

1.  Image upload and validation must work before model inference.
2.  Model selection and baseline evaluation must happen before claiming
    reliable detection.
3.  Visualisation depends on the output format of the selected model.
4.  Inspection history should be in place before reports and analytics
    depend on persistent data.
5.  Complaint management depends on saved inspections.
6.  The authority dashboard depends on complaint tracking and
    appropriate access controls.
7.  Deployment follows end-to-end testing.

## Current Implementation Status

All features in this document are **planned, not implemented**. The
immediate task is to create and review project documentation only. No
application code, database, dataset, or model should be created during
the planning-only phase.
