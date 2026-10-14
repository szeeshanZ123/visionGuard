# VisionGuard AI --- Project Overview

## Summary

VisionGuard AI is a proposed computer-vision application that analyses
infrastructure images for supported defects and helps users record
inspections. The first target is road infrastructure, with candidate
classes such as potholes and cracks subject to dataset and model
research.

## Problem

Manual defect documentation can be slow and inconsistent. Teams need a
clear way to review images, record potential findings, and keep
inspection records organised.

## Proposed solution

A user uploads an image, a selected computer-vision model returns
detections, and the app displays genuine model outputs with supported
visual localisation. Users can later save records and generate reports.
Complaint tracking is a secondary feature.

## Main users

-   Field inspectors and citizens documenting potential defects.
-   Reviewers or supervisors checking inspection records.
-   Authority staff reviewing internal complaints in a later phase.
-   Project evaluators reviewing the workflow and model evaluation.

## Primary objective

Build a working, evaluated image-based defect detection workflow before
adding secondary modules.

## Expected outcomes

-   Image upload and validation.
-   Model inference for selected defect classes.
-   Annotated output based on actual model coordinates or masks.
-   Inspection history and PDF reports.
-   Optional analytics and complaint tracking.

## Limitations

The system is an inspection-support tool, not a certified engineering
assessment. Confidence scores are not defect severity. Image-based
predictions may be wrong and must be evaluated on representative data.
