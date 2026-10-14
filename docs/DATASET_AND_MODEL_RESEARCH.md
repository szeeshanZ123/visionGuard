# VisionGuard AI --- Dataset and Model Research Plan

## Purpose

Choose a suitable model and dataset for the defect classes we can
realistically support. Do not commit to a specific architecture before
checking requirements and evidence.

## Research checklist

### Dataset

-   What defect classes are annotated?
-   Are labels bounding boxes, masks, image-level labels, or another
    format?
-   Is the dataset licence compatible with the project and intended
    demonstration?
-   How many images and examples exist per class?
-   Are images diverse in lighting, weather, camera angle, distance, and
    road type?
-   Are there duplicates or possible train/test leakage?
-   Is the dataset representative of the intended usage environment?

### Model

-   Does the model perform classification, object detection, or
    segmentation?
-   Does it support the output format needed by our interface?
-   What are its licence, model size, runtime, and hardware
    requirements?
-   Is inference possible on the development machine and target
    deployment?
-   Can we identify its source and version?

### Evaluation

-   Use a held-out test set that was not used to tune the model.
-   For object detection, consider precision, recall, and mAP at defined
    IoU thresholds.
-   Record inference time and hardware.
-   Inspect false positives and false negatives, not only a single
    aggregate score.
-   Test difficult conditions such as low light, blur, shadows, and
    unusual road surfaces.
-   Document known limitations and avoid unsupported accuracy claims.

## Decision record

Before implementation, record: - Dataset name, source, licence, and
intended classes. - Model name, source, licence, output format, and
runtime requirements. - Evaluation protocol and baseline results. -
Reasons for choosing the approach and known risks.

## Guardrails

Model confidence is not defect severity. An image model cannot certify
structural safety from a photo alone. If the selected model does not
return boxes or masks, the project must not invent them.
