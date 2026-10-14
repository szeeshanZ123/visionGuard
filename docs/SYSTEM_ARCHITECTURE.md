# VisionGuard AI --- High-Level System Architecture

## Proposed data flow

1.  **User interface** --- User selects an infrastructure image.
2.  **Input validation** --- Check format, size, readability, and image
    dimensions.
3.  **Preprocessing** --- Prepare the image according to the selected
    model's requirements.
4.  **Detection service** --- Run the actual computer-vision model.
5.  **Structured results** --- Return the model's class labels,
    confidence values, and supported coordinates or masks.
6.  **Visualisation** --- Render overlays that correspond to the model
    outputs.
7.  **Inspection storage** --- Save inspection metadata and results when
    history is implemented.
8.  **Report generation** --- Create a report from saved, verified
    inspection data.
9.  **Optional modules** --- Analytics, complaint tracking, and
    authority review.

## Design rules

-   Keep model inference separate from UI code.
-   Never fabricate predictions to make a demo look complete.
-   Treat confidence and severity as different concepts.
-   Store model name/version where practical for traceability.
-   Do not promise bounding boxes if the chosen model only supports
    classification.
-   A language model may summarise verified results but must not create
    detections.
-   Keep the architecture lightweight until model selection and
    deployment needs are known.

## Conceptual component boundaries

-   `app/`: interface and user workflow.
-   `ai/`: preprocessing, model integration, and inference.
-   `database/`: persistence logic added during the storage phase.
-   `reports/`: generated report output.
-   `tests/`: application and model evaluation tests.
