# VisionGuard AI --- Development Roadmap

Each phase should be reviewed before the next begins. The current status
is planning only.

  --------------------------------------------------------------------------
  Phase             Goal              Main deliverable     Exit criteria
  ----------------- ----------------- -------------------- -----------------
  1\. Planning      Define scope and  PRD, feature list,   Documents
                    project docs      architecture and     reviewed and
                                      roadmap              scope approved

  2\. Model         Compare datasets  Research decision    Dataset licence,
  research          and models        record               labels, model
                                                           output and
                                                           evaluation plan
                                                           checked

  3\. Environment   Create            Environment and      Dependencies
  setup             reproducible      dependency list      install and basic
                    Python                                 checks pass
                    environment                            

  4\. Image input   Upload and        Working image input  Valid files
                    validate images   workflow             accepted; invalid
                                                           files handled

  5\. AI detection  Integrate         Genuine inference    Outputs come from
                    selected model    pipeline             the model and
                                                           baseline is
                                                           measured

  6\. Visualisation Display           Annotated image and  Overlays match
                    detections        result summary       actual output
                                                           coordinates or
                                                           masks

  7\. Inspection    Persist results   Save/search/detail   Records survive
  history                             workflow             restart and match
                                                           source results

  8\. Reports       Generate reports  Downloadable PDF     PDF opens and
                                                           reflects saved
                                                           data accurately

  9\. Analytics     Summarise         Basic charts and     Counts match
                    inspections       counts               underlying
                                                           records

  10\. Complaints   Track internal    Complaint workflow   Complaints link
                    complaints                             to inspections
                                                           and statuses
                                                           persist

  11\. Authority    Review and update Restricted reviewer  Access controls
  dashboard         complaints        workflow             and status
                                                           updates work

  12\. Testing      Evaluate app and  Test and evaluation  Critical issues
                    model             report               addressed;
                                                           limitations
                                                           documented

  13\. Deployment   Make a usable     Deployment and setup End-to-end
                    release           guide                workflow verified
                                                           in target
                                                           environment
  --------------------------------------------------------------------------

## Phase completion rule

Do not mark a phase complete merely because code was generated. Run the
application or tests, inspect the output, document unresolved issues,
and verify the acceptance criteria.
