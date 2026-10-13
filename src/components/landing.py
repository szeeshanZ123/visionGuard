"""
Landing page component for VisionGuard AI.

Phase 1 Scope:
- Professional overview of the VisionGuard AI infrastructure platform.
- System mission, architecture roadmap, and workflow guidance.
- Explicit status display highlighting current Phase 1 capabilities.
"""

import streamlit as st


def render_landing_page():
    """Renders the landing page for VisionGuard AI."""
    st.markdown(
        """
        <div style="padding: 1.5rem 0 1rem 0;">
            <h1 style="margin-bottom: 0.2rem;">🛡️ VisionGuard AI</h1>
            <h3 style="color: #4B5563; font-weight: 400; margin-top: 0;">
                AI-Powered Infrastructure Defect Detection & Reporting
            </h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Phase 1 Status Callout
    st.info(
        "📌 **Phase 1 Active (Foundation & Ingestion)**: "
        "The current build provides image verification, metadata extraction, and storage scaffolding. "
        "Authentic deep-learning defect detection models will be integrated in Phase 2 without placeholder simulations."
    )

    st.markdown("---")

    # Platform Mission & Core Capabilities
    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.subheader("System Overview")
        st.write(
            """
            **VisionGuard AI** is designed to modernize civic and highway asset maintenance by providing
            automated visual defect analysis for public works authorities, civil engineers, and inspectors.

            Aging infrastructure often suffers from deferred maintenance due to manual inspection bottlenecks.
            VisionGuard AI bridges this gap by enabling rapid visual diagnostics of roadway distresses.
            """
        )

        st.subheader("Target Infrastructure Assets")
        st.markdown(
            """
            - **Asphalt & Concrete Roadways**: Potholes, alligator cracking, longitudinal cracks, and rutting.
            - **Bridges & Overpasses**: Concrete spalling, rebar exposure, and expansion joint fatigue.
            - **Highway Safety Fixtures**: Guardrail impacts, damaged road barriers, and obscured signage.
            - **Drainage & Curb Structures**: Broken curbs, gutter blockages, and surface subsidence.
            """
        )

    with col2:
        st.subheader("Implementation Roadmap")

        # Step 1
        with st.container(border=True):
            st.markdown("✅ **Phase 1: Ingestion & Workspace Setup (Current)**")
            st.caption(
                "Image ingestion, format validation, dimensional analysis, and modular database scaffolding."
            )

        # Step 2
        with st.container(border=True):
            st.markdown("⏳ **Phase 2: AI Model Integration (Next)**")
            st.caption(
                "Integration of genuine computer vision models (e.g. YOLO/PyTorch defect segmentation) for real defect localization."
            )

        # Step 3
        with st.container(border=True):
            st.markdown("📅 **Phase 3: Defect Scoring & Geospatial Tagging**")
            st.caption(
                "Severity metrics (PCI index approximation), GPS coordinates, and historical deterioration tracking."
            )

        # Step 4
        with st.container(border=True):
            st.markdown("📅 **Phase 4: Authority Complaint & Work Order Flow**")
            st.caption(
                "Department dashboards, repair dispatch tracking, and civic complaint lifecycle management."
            )

    st.markdown("---")

    # Workflow Section
    st.subheader("Inspection Workflow")
    step_col1, step_col2, step_col3, step_col4 = st.columns(4)

    with step_col1:
        st.markdown("##### 1. Capture")
        st.write("Acquire field imagery from inspection vehicles, mobile phones, or drone surveys.")

    with step_col2:
        st.markdown("##### 2. Ingest & Validate")
        st.write("Inspect integrity, color channels, and resolution constraints.")

    with step_col3:
        st.markdown("##### 3. AI Inference")
        st.write("*(Phase 2)* Run genuine neural network models to delineate defect boundaries.")

    with step_col4:
        st.markdown("##### 4. Actionable Report")
        st.write("*(Future Phase)* Categorize defect severity and dispatch remediation teams.")

    st.markdown("")
    st.markdown("💡 *To inspect an infrastructure image, navigate to **Defect Inspection** in the sidebar.*")
