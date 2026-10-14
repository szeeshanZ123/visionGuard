# VisionGuard AI --- Testing Strategy

## 1. Input Validation & API Tests

- **Supported image formats:** Verify Flask `/api/inspect` accepts valid JPG, JPEG, PNG, BMP, and WEBP uploads.
- **Unsupported file types:** Verify non-image files (e.g. PDFs, text files) return descriptive HTTP 400 JSON errors.
- **Corrupted files:** Ensure corrupt or truncated byte streams are trapped gracefully without server crashes.
- **Oversized files:** Enforce maximum file size limits (e.g. 15 MB) and verify proper rejection.
- **Empty or missing payloads:** Ensure missing multipart form fields return clear error messages.

## 2. Model Integration & Inference Tests

- **Model loading:** Verify model initialization handles missing weights or runtime errors gracefully.
- **Structured output:** Verify inference outputs standard Python dictionaries/tensors containing class names, confidence floats, and coordinates/masks when supported.
- **No-detection cases:** Confirm images without defects return an empty detection list honestly rather than raising errors or inventing detections.
- **API fidelity:** Confirm Flask JSON responses match raw model outputs exactly.

## 3. Model Evaluation Protocol

- **Held-out test set:** Evaluate the selected defect model against an isolated test set not seen during training.
- **Metrics:** Calculate precision, recall, and mAP at defined IoU thresholds for bounding box detection.
- **Error analysis:** Systematically record and categorize false positives (e.g. dark shadows misclassified as potholes) and false negatives.
- **Inference benchmarks:** Record execution latency per image and hardware environment (CPU vs GPU).
- **Environmental robustness:** Evaluate across diverse road conditions, wet/dry asphalt, overcast/bright sunlight, and camera angles.

## 4. Visualisation Tests

- **Overlay accuracy:** Verify OpenCV-drawn bounding boxes or masks align with the returned model coordinates.
- **Label fidelity:** Verify rendered text labels correspond to the detected classes and confidence scores.
- **Comparison:** Ensure the HTML/JS frontend allows comparing original and annotated images.
- **No fabricated overlays:** Confirm that images with zero detections do not produce artificial bounding boxes.

## 5. Storage and Report Tests

- **Database operations:** Test SQLite create, read, filter, and delete operations for inspection logs.
- **Persistence across restarts:** Confirm saved inspection records survive Flask server restarts.
- **Report accuracy:** Confirm generated ReportLab PDF reports match stored inspection results and contain appropriate limitation disclaimers.
- **Missing assets:** Ensure missing image files or database read failures generate clear, user-facing error notices.

## 6. End-to-End Workflow Tests

- Verify the full client-server pipeline:
  1. HTML5/JS image selection and upload via `fetch()`.
  2. Flask API ingestion, validation, and OpenCV tensor formatting.
  3. AI model inference execution.
  4. Structured JSON response and OpenCV overlay transmission.
  5. JavaScript UI rendering of metrics, summary cards, and annotated imagery.
  6. Saving records to SQLite and downloading generated ReportLab PDF reports.

## 7. Security and Privacy Checks

- **Secret management:** Confirm no API keys, credentials, or production passwords exist in code or git history.
- **Upload safety:** Ensure uploaded files are sanitized and saved outside public web server roots or with randomized filenames.
- **Restricted access:** Verify authority dashboard and complaint status updating endpoints require appropriate authorization before exposure.

## Exit Criteria

Critical defects are resolved or documented, end-to-end client-server tests pass, and model limitations are stated transparently.
