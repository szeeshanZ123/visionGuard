# VisionGuard AI --- Project Overview

## Summary

VisionGuard AI is a proposed computer-vision web application that analyses infrastructure images for supported defects and helps users record inspections. The primary initial target is road infrastructure, with candidate defect classes such as potholes and cracks subject to dataset and model research.

The frontend is built with plain **HTML5, CSS3, and JavaScript** (with optional **Chart.js** for analytics), and the backend is built with **Python and Flask**.

## Problem

Manual defect documentation across road networks and civic infrastructure can be slow, inconsistent, and difficult to track. Engineering and public works teams need a structured, accessible way to review imagery, record potential findings, inspect localized defects, and keep inspection records organised.

## Proposed Solution

1. **User Interface**: The user accesses a clean web interface constructed with semantic HTML5, modern CSS3, and vanilla JavaScript.
2. **Image Ingestion**: The user uploads an infrastructure image, and JavaScript transmits the file to a Flask API endpoint via an HTTP POST request.
3. **Validation & Preprocessing**: Flask and OpenCV validate the image format, dimensions, readability, and prepare it for inference.
4. **AI Inference**: A selected computer-vision model evaluates the image and returns genuine detections.
5. **Structured Response**: Flask returns structured JSON with defect classes, confidence scores, and bounding boxes or segmentation masks when supported by the model.
6. **Visual Feedback**: The frontend presents the original image, detection metrics, and the OpenCV-annotated image.
7. **Storage & Supporting Modules**: In subsequent phases, Flask coordinates local SQLite persistence, inspection history, downloadable PDF reports, dashboard analytics, and internal complaint workflows.

Complaint tracking and authority review dashboards are secondary modules to be added only after the core inspection workflow is proven.

## Planned Frontend Views

The application plans the following user views (which may be consolidated into fewer screens to keep the interface simple):

- **Dashboard**: High-level metrics, recent inspection summaries, and system status.
- **AI Inspection / Image Upload**: File selection, capture guidelines, and image preview.
- **Detection Results**: Display of detected classes, confidence ratings, and annotated overlays.
- **Inspection History**: Tabular view of previous inspections with search and filtering.
- **Inspection Details**: Detailed breakdown of a specific inspection record.
- **Reports**: Configurable PDF report generation and download.
- **Complaint Management**: Internal submission and tracking of civic defect complaints.
- **Authority Dashboard**: Restricted interface for reviewing complaints and updating maintenance statuses.

## Main Users

- **Field inspectors and citizens**: Upload images and record inspections.
- **Reviewers or supervisors**: Review inspection records, verify findings, and export reports.
- **Authority staff**: In a later phase, review internal complaints and update repair statuses.
- **Project evaluators**: Review end-to-end workflow, model evaluation, and architectural modularity.

## Primary Objective

Build a working, evaluated image-based defect detection workflow using HTML/CSS/JS and Flask before adding secondary modules.

## Expected Outcomes

- Semantic HTML/CSS/JS image upload and client-side validation.
- Flask REST API for image validation and model inference coordination.
- Computer-vision inference for supported defect classes.
- Genuine visual localisation based on actual model coordinates or masks.
- Local SQLite inspection history and ReportLab PDF reports.
- Optional Chart.js analytics and complaint tracking.

## Limitations

The system is an inspection-support tool, not a certified structural engineering assessment. Confidence scores are model probabilities, not defect severity. Image-based predictions may contain false positives or false negatives and must be evaluated on representative held-out test data.
