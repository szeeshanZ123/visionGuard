# VisionGuard AI --- Testing Strategy

## 1. Input validation tests

-   Supported image formats.
-   Unsupported file types.
-   Corrupted or unreadable files.
-   Oversized files and unusual image dimensions.
-   Empty or missing uploads.

## 2. Model integration tests

-   Model loads correctly.
-   Known test images produce structured output.
-   No-detection cases are handled honestly.
-   Missing model files and inference errors show clear messages.
-   Displayed classes, confidence scores, and coordinates match actual
    model outputs.

## 3. Model evaluation

-   Define a held-out test set.
-   Use appropriate metrics such as precision, recall, and mAP for
    object detection.
-   Record false positives and false negatives.
-   Record inference time and hardware.
-   Review performance across different image conditions.
-   Avoid accuracy claims without a documented evaluation protocol.

## 4. Visualisation tests

-   Boxes or masks align with the returned coordinates.
-   Labels correspond to the correct detections.
-   Original and annotated images can be distinguished.
-   Images with no detections do not show fabricated overlays.

## 5. Storage and report tests

-   Create, retrieve, search, and delete inspection records as designed.
-   Confirm data persists after restart.
-   Confirm reports match stored inspection data.
-   Handle missing images or report-generation errors.

## 6. Workflow tests

Test the complete flow from upload through inference, visualisation,
saving, and report download.

## 7. Security and privacy checks

-   No secrets are committed.
-   Uploads are validated.
-   Stored images and reports are not publicly exposed unintentionally.
-   Authentication and role checks are tested before authority functions
    are exposed.

## Exit criteria

Critical bugs are resolved or explicitly documented, results are
reproducible, and model limitations are stated honestly.
