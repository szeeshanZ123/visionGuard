# VisionGuard AI --- Development Roadmap

Each phase should be reviewed before the next begins. The current status is planning only.

The project uses a plain **HTML5, CSS3, and JavaScript** frontend paired with a **Python and Flask** backend.

-----------------------------------------------------------------------------------------------------------------------
Phase                   Goal                    Main deliverable        Exit criteria
----------------------- ----------------------- ----------------------- -----------------------------------------------
1. Planning             Define scope and        PRD, feature list,      Documents reviewed and HTML/CSS/JS + Flask
                        project docs            architecture, roadmap   scope approved

2. Model research       Compare datasets and    Research decision       Dataset licence, labels, model output format,
                        candidate models        record                  and evaluation plan confirmed

3. Environment setup    Create reproducible     Flask & Python          Dependencies install and basic server checks
                        Python environment      dependency list         pass cleanly

4. Image input          Upload and validate     Working HTML/JS upload  Valid files accepted; invalid files handled
                        images via Flask API    and Flask endpoint      gracefully with JSON errors

5. AI detection         Integrate selected      Genuine inference       Outputs originate from real model inference
                        model into backend      pipeline in Flask       and baseline metrics are documented

6. Visualisation        Display detections and  Annotated image and     Overlays match actual output coordinates or
                        metrics on frontend     result view (HTML/JS)   masks; no fabricated detections

7. Inspection history   Persist results in      SQLite persistence &    Records survive server restart and match source
                        local database          history view            results

8. Reports              Generate reports        Downloadable PDF        PDF opens and reflects saved inspection data
                                                via ReportLab           accurately

9. Analytics            Summarise inspections   Dashboard cards and     Counts match underlying SQLite records;
                        with metrics & charts   Chart.js charts         charts render accurately

10. Complaints          Track internal civic    Complaint management    Complaints link to inspections and statuses
                        complaints              workflow                persist reliably

11. Authority dashboard Review and update       Restricted reviewer     Access controls and status updates work
                        defect complaints       view                    as intended

12. Testing             Evaluate app and        Test and evaluation     Critical issues addressed; API and client flows
                        model performance       report                  pass tests; limitations documented

13. Deployment          Make a usable release   Deployment and setup    End-to-end workflow verified in target
                                                guide                   environment
-----------------------------------------------------------------------------------------------------------------------

## Phase Completion Rule

Do not mark a phase complete merely because code was generated. Run the application or tests, inspect the output, document unresolved issues, and verify the acceptance criteria.
