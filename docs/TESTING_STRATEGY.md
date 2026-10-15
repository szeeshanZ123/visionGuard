# VisionGuard AI --- Testing and Evaluation Strategy

**Document Status:** Approved Technical Baseline  
**Project Phase:** Phase 1 --- Project Foundation & Documentation Only  
**Testing Status:** Test Strategy & Test Cases Planned (No Tests Executed in Phase 1)  
**Version:** 1.2  

---

## 1. Quality Assurance Philosophy

VisionGuard AI requires rigorous verification across all layers of the stack: web client, backend REST API, image preprocessing, model inference, persistence, and reporting.

> [!IMPORTANT]
> In strict accordance with Phase 1 constraints, **no new tests are written or executed during Phase 1**. This document defines the comprehensive test strategy, test suites, and acceptance criteria to be executed during Phase 4, Phase 5, and Phase 6.

---

## 2. Test Suites & Future Test Cases

```text
┌────────────────────────────────────────────────────────┐
│           End-to-End Workflow Tests (Phase 6)          │
│   Full user journey: Upload -> Detection -> Report     │
├───────────────────────────┬────────────────────────────┤
│   Frontend Client Tests   │      Flask API Tests       │
│  Validation & DOM (Ph 5)  │  Payload & Status (Ph 4)   │
├───────────────────────────┴────────────────────────────┤
│           Vision & Model Evaluation (Phase 3/4)        │
│   mAP, Precision, Recall, OpenCV Overlay Alignment     │
├────────────────────────────────────────────────────────┤
│          Unit & Persistence Tests (Phase 4/6)          │
│    Image Ops, Format Checks, SQLite CRUD Operations    │
└────────────────────────────────────────────────────────┘
```

---

### Suite 1: Input Validation & Image Preprocessing Tests (Target: Phase 4)

| Test ID | Test Scenario | Input Data | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-INP-01** | Valid standard JPEG image | High-resolution road JPEG (1920x1080) | Image passes validation; OpenCV loads array with shape `(1080, 1920, 3)`. |
| **TC-INP-02** | Valid standard PNG image | Road surface PNG image | Image passes validation; color channels correctly decoded. |
| **TC-INP-03** | Unsupported file format | PDF or text document renamed as `.jpg` | Rejected with HTTP 400 and clear error message (`Unsupported file extension`). |
| **TC-INP-04** | Corrupted image stream | Byte stream containing invalid header bytes | Rejected with HTTP 400 and notice of file corruption; no unhandled server crash. |
| **TC-INP-05** | Oversized file payload | Image exceeding 15 MB threshold | Rejected with HTTP 413 or 400; upload halted before exhausting server memory. |
| **TC-INP-06** | Empty / zero-byte payload | 0-byte file stream | Rejected with HTTP 400 (`Uploaded file is empty`). |

---

### Suite 2: Flask API & Backend Route Tests (Target: Phase 4)

| Test ID | Test Scenario | HTTP Method & Route | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-API-01** | Health check endpoint | `GET /api/health` | Returns HTTP 200 OK with system status JSON (`{"status": "Healthy"}`). |
| **TC-API-02** | Valid inspection request | `POST /api/inspect` | Returns HTTP 200 OK with structured JSON containing defect list and overlay reference. |
| **TC-API-03** | Missing file field in form | `POST /api/inspect` without `image` | Returns HTTP 400 Bad Request with descriptive JSON error payload. |
| **TC-API-04** | Inspection history query | `GET /api/history` | Returns HTTP 200 OK with array of serialized past inspection records. |
| **TC-API-05** | Report download request | `GET /api/reports/<id>` | Returns HTTP 200 OK with `application/pdf` binary stream and valid headers. |

---

### Suite 3: Computer-Vision Model Evaluation Protocol (Target: Phase 3)

The AI model will be evaluated against an isolated, held-out pavement test set:

- **Benchmark Metrics:** Compute Precision, Recall, and mAP@0.5 across defect categories (Pothole, Longitudinal Crack, Transverse Crack, Alligator Crack).
- **No-Detection Baseline:** Evaluate images of clean, unblemished pavement; verify the model produces zero detections without raising exceptions.
- **Negative Condition Robustness:** Assess detection accuracy under challenging conditions:
  - Deep tree shadows across roadway.
  - Wet asphalt with standing rainwater reflections.
  - Low-light dusk photography.
  - Low-contrast hairline cracking.
- **Inference Latency Profiling:** Measure mean and 95th percentile inference time across 100 test runs on CPU and GPU hardware.

---

### Suite 4: Visualisation & Overlay Accuracy Tests (Target: Phase 4 & 5)

| Test ID | Test Scenario | Verification Procedure | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-VIS-01** | Bounding box spatial accuracy | Compare raw model coordinates `[x1, y1, x2, y2]` against OpenCV drawn rectangle | Rectangle coordinates match raw model output with zero pixel offset. |
| **TC-VIS-02** | Defect label fidelity | Inspect rendered label text above bounding box | Label matches detected class name and confidence percentage. |
| **TC-VIS-03** | Honest zero-detection rendering | Test image with zero detected distresses | Original image displayed cleanly without any synthetic or fabricated bounding boxes. |
| **TC-VIS-04** | Multi-defect overlay | Image with both potholes and multiple cracks | Distinct bounding boxes drawn for each defect instance with legible non-overlapping labels. |

---

### Suite 5: Frontend Client & DOM Integration Tests (Target: Phase 5)

| Test ID | Test Scenario | Trigger Action | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-FE-01** | Client image preview | Select image via `<input type="file">` | JavaScript `FileReader` renders preview thumbnail before upload. |
| **TC-FE-02** | Upload progress & loading state | Click "Analyze Image" button | UI shows active loading spinner and disables submit button to prevent double-clicks. |
| **TC-FE-03** | Result presentation | Ingest valid API JSON response | Dynamic DOM updates render side-by-side comparison and tabular metrics. |
| **TC-FE-04** | Network error handling | Simulate server timeout / network loss | User-friendly alert displayed without breaking the interface layout. |

---

### Suite 6: Persistence & Reporting Tests (Target: Phase 6)

| Test ID | Test Scenario | Verification Procedure | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-DAT-01** | Record insertion | Insert inspection record into SQLite | Record written with auto-generated ID, timestamp, and correct defect attributes. |
| **TC-DAT-02** | Persistence across restart | Restart Flask application process | All previous inspection records remain retrievable via `SELECT` queries. |
| **TC-DAT-03** | PDF report compilation | Request PDF generation for an inspection record | ReportLab generates valid PDF containing correct metadata, imagery, and disclaimers. |
| **TC-DAT-04** | PDF document validity | Open generated PDF using standard PDF parser | File structure is valid, pages render without truncation, and text is readable. |

---

### Suite 7: End-to-End Workflow Verification (Target: Phase 6)

The complete user journey will be audited:
1. Engineer opens browser at application URL.
2. Selects a field road photo and triggers analysis.
3. JavaScript submits photo to Flask REST endpoint.
4. Flask validates, OpenCV formats tensor, and CV model detects defects.
5. Flask responds with JSON; JavaScript renders annotated view and defect metrics.
6. Record is saved to SQLite.
7. Engineer clicks "Export PDF Report" and successfully downloads a matching inspection document.

---

## 3. Exit Criteria for Phase 1

- Test strategy and test cases formally defined and cross-referenced with functional requirements.
- Strict confirmation that no tests were executed or implemented prematurely during Phase 1.
