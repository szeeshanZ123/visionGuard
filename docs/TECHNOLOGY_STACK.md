# VisionGuard AI --- Proposed Technology Stack

**Status:** Provisional. Confirm choices after model and deployment
research.

  -----------------------------------------------------------------------
  Technology              Intended role           Notes
  ----------------------- ----------------------- -----------------------
  Python                  Main language           Suitable ecosystem for
                                                  computer vision and
                                                  data work.

  Streamlit               Prototype web interface Helps build an
                                                  interactive student
                                                  project quickly.

  OpenCV                  Image processing and    Draws boxes or masks
                          overlays                only from actual model
                                                  output.

  PyTorch                 Deep-learning runtime   Use if the selected
                                                  model requires it; do
                                                  not assume yet.

  Pandas                  Tabular processing and  Useful for summaries
                          analytics               and data handling.

  SQLite                  Local prototype storage Simple persistence;
                                                  reassess if deployment
                                                  requires multi-user
                                                  access.

  Plotly                  Charts                  Optional, primarily for
                                                  the analytics phase.

  ReportLab               PDF generation          Add when reports are
                                                  implemented.

  Gemini or another       Optional explanation    Not required for core
  language model          text                    detection; must not
                                                  invent detections or
                                                  coordinates.
  -----------------------------------------------------------------------

## Selection principles

1.  Choose tools based on the selected model and target deployment.
2.  Install dependencies only when the relevant phase begins.
3.  Avoid adding packages that do not support an agreed requirement.
4.  Consider model size, inference speed, licence, hardware needs, and
    deployment limits.
5.  Keep the first implementation simple and testable.
