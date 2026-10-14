# VisionGuard AI --- Dataset and Model Research Plan

## Purpose

Choose a suitable computer-vision model and dataset for the defect classes we can realistically support (initially road potholes and cracks). Do not commit to a specific architecture before checking requirements, licensing, and empirical evidence.

## Research Checklist

### Dataset

- What defect classes are annotated (e.g. potholes, longitudinal cracks, alligator cracking)?
- Are labels bounding boxes, segmentation masks, image-level classifications, or another format?
- Is the dataset licence compatible with the project and intended demonstration?
- How many images and examples exist per class?
- Are images diverse in lighting, weather, camera angle, distance, and road type?
- Are there duplicates or possible train/test leakage?
- Is the dataset representative of the intended usage environment?

### Model

- Does the model perform classification, object detection, or segmentation?
- Does it support the output format needed by our Flask REST API and HTML/JS frontend?
- Do not claim or assume that every model supports bounding boxes or masks. Confirm the selected model's actual output format before designing UI overlays.
- What are its licence, model size, runtime requirements (e.g. PyTorch, ONNX, TFLite), and hardware needs?
- Is inference possible on the development machine and within Flask request-response limits?
- Can we clearly identify its source, provenance, and version?

### Evaluation

- Use a held-out test set that was not used to tune or train the model.
- For object detection, evaluate precision, recall, and mAP at defined IoU thresholds.
- Record inference time and hardware specifications.
- Inspect false positives and false negatives, not only a single aggregate score.
- Test challenging conditions such as low light, motion blur, cast shadows, and varied asphalt/concrete road surfaces.
- Document known limitations and avoid unsupported accuracy claims.

## Decision Record

Before implementation begins, document:
- Dataset name, source, licence, and intended defect classes.
- Model name, source, licence, output format (classification / boxes / masks), and runtime requirements.
- Evaluation protocol and baseline benchmark results.
- Reasons for selecting the approach and known operational risks.

## Guardrails

- **Confidence is not severity:** Model confidence represents probability, not physical distress severity.
- **Structural limits:** An image model cannot certify structural safety from a photograph alone.
- **Honest visualisation:** If the selected model does not return bounding boxes or segmentation masks, the application must not fabricate or simulate them.
- **LLM boundaries:** Gemini or another language model may be considered for optional explanations, but must never invent defect detections, bounding boxes, or confidence scores.
