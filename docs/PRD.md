# VisionGuard AI --- Product Requirements Document (PRD)

**Document status:** Draft for planning and approval\
**Project phase:** Planning only --- implementation has not started\
**Version:** 1.0

## 1. Project Overview

VisionGuard AI is a proposed computer-vision application for identifying
supported infrastructure defects from images and helping users document
inspections and follow up on reported issues.

The first target domain is road infrastructure. Candidate defect classes
include potholes and road cracks, but the final classes will depend on
the availability, licensing, quality, and evaluation results of suitable
datasets and models.

The primary product capability is genuine AI-based defect detection.
Inspection records, PDF reports, analytics, and complaint management are
supporting capabilities.

## 2. Problem Statement

Infrastructure defects can be difficult and time-consuming to document
consistently through manual inspection alone. Teams may need a
structured way to review images, record findings, and keep inspection
information organised.

VisionGuard AI aims to assist this workflow by analysing images with a
suitable computer-vision model and presenting its outputs in a clear,
reviewable format. It is an inspection-support tool, not a replacement
for qualified engineering assessment.

## 3. Proposed Solution

A user will upload an infrastructure image. The application will
validate the image and pass it to a selected computer-vision model. If
the model returns detections, the application will display the detected
class, confidence score, and bounding box or other localisation output
supported by that model.

Users will be able to save inspection details, review prior inspections,
and generate a report. In a later phase, users may create internal
complaints linked to an inspection and authorised staff may update their
statuses.

Gemini or another language model may be considered for optional
explanations or report wording. It must not invent detections,
coordinates, or confidence scores. Detection values must originate from
the actual computer-vision model.

## 4. Objectives

1.  Build a usable image-based infrastructure inspection workflow.
2.  Integrate and evaluate a suitable defect-detection model.
3.  Visualise genuine model outputs clearly.
4.  Persist inspection records and retrieve them reliably.
5.  Generate reports that accurately reflect saved results.
6.  Add complaint tracking only after the core inspection workflow
    works.
7.  Document performance, limitations, privacy considerations, and setup
    instructions.

## 5. Target Users

-   **Inspectors or field users:** Upload images and record inspections.
-   **Reviewers or supervisors:** Review inspection results and reports.
-   **Authority staff:** In a later phase, review complaints and update
    statuses.
-   **Project demonstrators or evaluators:** Review the workflow, model
    evaluation, and limitations.

The first prototype may use a single-user workflow. Authentication and
role-based access should be added when required by the chosen deployment
and complaint workflow.

## 6. Scope and Priorities

### In scope for the core version

-   Image upload and validation.
-   Computer-vision inference using a selected model.
-   Genuine class labels, confidence scores, and supported localisation
    outputs.
-   Annotated image visualisation.
-   Saving and retrieving inspection records.
-   Downloadable inspection reports.

### Later or optional scope

-   Inspection analytics.
-   Location metadata.
-   Internal complaint creation and status tracking.
-   Authority dashboard and access control.
-   Video or live-camera analysis.
-   Additional defect classes or infrastructure types.

### Out of scope unless separately validated

-   Certifying structural safety from a photograph.
-   Automatically determining engineering-grade defect severity from
    confidence scores.
-   Guaranteeing that an external authority has received a complaint
    without a real, verified submission integration.
-   Claiming support for defect classes that have not been tested.

## 7. Functional Requirements

  -----------------------------------------------------------------------
  ID                      Requirement             Priority
  ----------------------- ----------------------- -----------------------
  FR-01                   Accept supported image  P0
                          formats and reject      
                          invalid or unsupported  
                          files with a clear      
                          message.                

  FR-02                   Run the selected        P0
                          computer-vision model   
                          on a valid image.       

  FR-03                   Show genuine            P0
                          detections, including   
                          class, confidence, and  
                          localisation when       
                          supported by the model. 

  FR-04                   Handle images with no   P0
                          detections without      
                          fabricating results.    

  FR-05                   Display an annotated    P0
                          image whose overlays    
                          match actual model      
                          outputs.                

  FR-06                   Save and retrieve       P1
                          inspection metadata and 
                          detection results.      

  FR-07                   Generate a downloadable P1
                          report based on saved   
                          inspection data.        

  FR-08                   Filter or search        P1
                          inspection history.     

  FR-09                   Summarise inspection    P2
                          records with basic      
                          charts and counts.      

  FR-10                   Allow a user to create  P2
                          a complaint linked to   
                          an inspection.          

  FR-11                   Allow authorised users  P2
                          to review complaints    
                          and update their        
                          statuses.               

  FR-12                   Record location         P2
                          metadata when it is     
                          provided and            
                          appropriate.            
  -----------------------------------------------------------------------

## 8. Non-Functional Requirements

-   **Usability:** Keep the workflow understandable for a student
    developer and first-time user.
-   **Reliability:** Invalid files, missing model files, and inference
    failures should produce clear errors.
-   **Maintainability:** Separate interface, model inference, image
    processing, persistence, and reporting responsibilities.
-   **Performance:** Record inference time and avoid unnecessary image
    copies or repeated model loading.
-   **Privacy:** Explain how uploaded images are stored and provide a
    way to remove local records when appropriate.
-   **Security:** Never commit API keys, credentials, private images, or
    environment files to version control.
-   **Traceability:** Store model/version information with inspection
    results when feasible.
-   **Honesty:** Clearly label model-generated results and known
    limitations; do not imply that predictions are guaranteed to be
    correct.

## 9. Proposed Technology Stack

The stack is provisional and will be confirmed after model research.

  -----------------------------------------------------------------------
  Technology              Proposed role           Decision status
  ----------------------- ----------------------- -----------------------
  Python                  Main language           Proposed

  Streamlit               Prototype web interface Proposed

  OpenCV                  Image loading,          Proposed
                          processing, and visual  
                          overlays                

  PyTorch                 Model runtime if        Conditional
                          required by the         
                          selected model          

  Pandas                  Tabular data handling   Proposed
                          and analytics           

  SQLite                  Local persistence for   Proposed
                          the prototype           

  Plotly                  Charts for inspection   Optional
                          analytics               

  ReportLab               PDF report generation   Optional, for reporting
                                                  phase

  Gemini or another       Optional plain-language Not required for core
  language model          summaries               detection
  -----------------------------------------------------------------------

Do not install all dependencies during planning. Add packages only when
a phase needs them.

## 10. Dataset and Model Requirements

Before selecting a model:

1.  Identify datasets relevant to the intended defect classes and image
    conditions.
2.  Check licensing, permitted use, dataset provenance, labels, and
    annotation format.
3.  Review class balance, image resolution, duplicate images, and label
    quality.
4.  Compare suitable pretrained models and their runtime requirements.
5.  Verify whether the model supports classification, object detection,
    or segmentation. Do not promise bounding boxes if the model does not
    produce them.
6.  Establish a representative held-out test set and a reproducible
    evaluation procedure.
7.  Document known limitations and conditions where the model may fail.

Evaluate appropriate metrics such as precision, recall, and mAP for
object detection, plus inference time. Metrics should be reported
against a defined test set. Model confidence is not defect severity and
should not be presented as a calibrated probability unless calibration
has been evaluated.

## 11. High-Level Architecture

Proposed data flow:

1.  **Interface:** User selects an image and submits it.
2.  **Validation:** Check file type, size, readability, and dimensions.
3.  **Preprocessing:** Prepare the image according to the selected
    model's requirements.
4.  **Inference service:** Run the actual model and return structured
    results.
5.  **Visualisation:** Render supported boxes, masks, or labels using
    the model's outputs.
6.  **Inspection service:** Save metadata and detection results.
7.  **Reporting:** Build a report from saved, verified inspection data.
8.  **Optional follow-up modules:** Analytics, complaint tracking, and
    authority review.

A future implementation may separate these responsibilities into
modules. The architecture should remain simple until the model and
deployment requirements are known.

## 12. Data and Persistence

Potential inspection fields include:

-   Inspection ID.
-   Timestamp.
-   Original image path or managed image reference.
-   Model name and version.
-   Detection class.
-   Confidence score.
-   Bounding box or other localisation output, if supported.
-   Processing duration.
-   Optional location metadata.
-   Report path, if generated.

Complaint records may later include a complaint ID, linked inspection
ID, description, status, timestamps, and authorised reviewer
information.

Avoid storing unnecessary personal information. Define retention and
deletion behaviour before deploying the application for real users.

## 13. Security and Privacy

-   Keep secrets in local environment variables or a secrets manager.
-   Commit `.env.example`, never real `.env` files.
-   Validate uploads and set reasonable file-size limits.
-   Restrict access to uploaded images and reports when the app is
    deployed.
-   Avoid committing datasets, private images, generated databases, or
    model weights unless licensing and repository size have been
    checked.
-   Add authentication and role-based access before exposing authority
    workflows publicly.
-   Do not send images to third-party services unless the user
    understands and accepts that data flow.

## 14. Limitations and Risks

-   A model may miss defects or incorrectly label ordinary road
    features.
-   Performance may vary with lighting, weather, camera angle, distance,
    resolution, and road surface.
-   A dataset may not represent the locations where the application is
    used.
-   Bounding boxes indicate image regions, not physical measurements.
-   Confidence scores do not establish severity or structural safety.
-   Complaint routing and responsible authority mapping require verified
    jurisdiction data.
-   Cloud deployment may have memory, processing-time, storage, or
    model-size limits.

Mitigations include representative testing, clear limitation notices,
manual review, secure storage, and honest reporting of evaluation
results.

## 15. Success Metrics

Success criteria will be agreed after baseline model research. Proposed
measures include:

-   The app accepts valid images and rejects invalid inputs correctly.
-   Every displayed detection corresponds to an actual model output.
-   Precision, recall, and mAP are measured on a held-out test set where
    appropriate.
-   Inference time and hardware requirements are recorded.
-   Inspection records can be saved and retrieved without data mismatch.
-   Generated reports match stored inspection results.
-   Core workflows pass documented tests.
-   Known limitations and setup steps are documented.

Do not set an arbitrary accuracy target until the dataset, model, and
test protocol are understood.

## 16. Testing Strategy

-   **Input tests:** Valid, unsupported, corrupted, and oversized
    images.
-   **Inference tests:** Known test images, no-detection cases, and
    model-load failures.
-   **Visualisation tests:** Verify that displayed overlays match
    returned coordinates.
-   **Persistence tests:** Save, retrieve, filter, and delete inspection
    records.
-   **Report tests:** Confirm that generated reports contain correct
    stored values.
-   **Workflow tests:** Test the complete inspection process from upload
    to report.
-   **Model evaluation:** Use a held-out set and document false
    positives and false negatives.
-   **Security checks:** Check secrets, upload validation, and access
    control before deployment.

## 17. Development Roadmap

  -----------------------------------------------------------------------
  Phase                   Focus                   Exit criteria
  ----------------------- ----------------------- -----------------------
  1                       Planning and            PRD, features,
                          documentation           architecture, roadmap,
                                                  and scope reviewed

  2                       Dataset and model       Dataset and model
                          research                chosen with documented
                                                  reasons and evaluation
                                                  plan

  3                       Environment setup       Reproducible
                                                  environment and
                                                  dependency checks pass

  4                       Image input             Upload, validation, and
                                                  error handling work

  5                       AI detection            Real model inference
                                                  works and baseline
                                                  results are measured

  6                       Visualisation           Annotated output
                                                  matches actual
                                                  detections

  7                       Inspection history      Records persist and can
                                                  be retrieved

  8                       Reports                 PDF reports accurately
                                                  reflect stored results

  9                       Analytics               Dashboard summaries
                                                  match the data

  10                      Complaint management    Complaints can be
                                                  created and tracked

  11                      Authority dashboard     Permitted users can
                                                  review and update
                                                  statuses

  12                      Testing and evaluation  Critical defects
                                                  addressed and model
                                                  limitations documented

  13                      Deployment              Deployed workflow is
                                                  tested and
                                                  documentation is
                                                  complete
  -----------------------------------------------------------------------

## 18. Current Status and Next Action

**Current status: Planning only.** No application code, model, dataset,
or database has been implemented as part of this plan.

The immediate next step is to create and review the project structure
and documentation. After approval, research suitable datasets and models
before committing to an implementation design.
