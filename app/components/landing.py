"""
Landing page component for VisionGuard AI.

Aligns directly with docs/PRD.md and docs/DEVELOPMENT_ROADMAP.md:
- Mission: Automated computer vision defect analysis for infrastructure distresses.
- Architecture: Decoupled app, ai, database, and reports subsystems.
- Roadmap: 13-phase engineering progression.
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

    # Status Callout linked to Planning Starter Docs
    st.info(
        "📌 **Workspace Aligned with Planning Starter**: "
        "Project architecture organized into `app/`, `ai/`, `database/`, `data/`, `reports/`, and `docs/`. "
        "Strict adherence to authentic AI detection without simulated or fabricated predictions."
    )

    st.markdown("---")

    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.subheader("System Overview")
        st.write(
            """
            **VisionGuard AI** is a computer-vision application that analyses infrastructure imagery
            for supported defects and helps users record inspections. The primary initial target is
            road infrastructure (candidate distresses: potholes and cracks).
            """
        )

        st.subheader("Target Infrastructure Defects")
        st.markdown(
            """
            - **Road Potholes**: Surface depressions and asphalt cavities.
            - **Road Cracks**: Longitudinal, transverse, and alligator fatigue cracking.
            - **Future Scope**: Concrete spalling, curb subsidence, and roadside fixtures.
            """
        )

        st.subheader("Core Documentation")
        st.markdown(
            """
            All project planning specifications are available in the `docs/` repository directory:
            - `docs/PROJECT_OVERVIEW.md` - Problem statement, users, and boundaries
            - `docs/PRD.md` - Product requirements and functional scope
            - `docs/FEATURES.md` - Feature priorities and acceptance criteria
            - `docs/SYSTEM_ARCHITECTURE.md` - Data flow and component boundaries
            - `docs/TECHNOLOGY_STACK.md` - Evaluated tech stack (Python, Streamlit, OpenCV, PyTorch)
            - `docs/DATASET_AND_MODEL_RESEARCH.md` - Dataset checklist and model decision criteria
            - `docs/TESTING_STRATEGY.md` - Input, model, and workflow test plan
            - `docs/DEVELOPMENT_ROADMAP.md` - Complete 13-phase development lifecycle
            """
        )

    with col2:
        st.subheader("Phased Development Roadmap")

        roadmap_items = [
            ("Phase 1: Planning", "PRD, feature list, architecture, and roadmap approved.", "✅"),
            ("Phase 2: Model Research", "Compare candidate datasets and detection models.", "🔍"),
            ("Phase 3: Environment Setup", "Standardize Python dependencies and virtual environment.", "📦"),
            ("Phase 4: Image Input", "Validate uploaded image formats, dimensions, and integrity.", "🖼️"),
            ("Phase 5: AI Detection", "Integrate genuine computer vision model (no mocks).", "🤖"),
            ("Phase 6: Visualisation", "Render genuine overlays matching model coordinates.", "🎯"),
            ("Phase 7: Inspection History", "Persist inspection records to SQLite database.", "💾"),
            ("Phase 8: Reports", "Generate downloadable PDF inspection summaries.", "📄"),
            ("Phase 9: Analytics", "Aggregate defect metrics and trend visualizations.", "📊"),
            ("Phase 10: Complaints", "Log internal civic complaints linked to inspections.", "📋"),
            ("Phase 11: Authority Dashboard", "Restricted reviewer workflow for repair statuses.", "🏛️"),
            ("Phase 12: Testing", "Comprehensive test suite and model evaluation.", "🧪"),
            ("Phase 13: Deployment", "Production packaging and deployment guide.", "🚀"),
        ]

        for phase, desc, icon in roadmap_items[:6]:
            with st.container(border=True):
                st.markdown(f"**{icon} {phase}**")
                st.caption(desc)

        with st.expander("View remaining phases (7-13)..."):
            for phase, desc, icon in roadmap_items[6:]:
                st.markdown(f"**{icon} {phase}**")
                st.caption(desc)

    st.markdown("---")

    # Workflow Section
    st.subheader("Inspection Workflow")
    step_col1, step_col2, step_col3, step_col4 = st.columns(4)

    with step_col1:
        st.markdown("##### 1. Capture")
        st.write("Acquire field imagery from inspection vehicles, mobile phones, or surveys.")

    with step_col2:
        st.markdown("##### 2. Validate")
        st.write("Verify file integrity, dimensions, and OpenCV tensor compatibility.")

    with step_col3:
        st.markdown("##### 3. Detect")
        st.write("Execute genuine neural detection engine to identify supported defect classes.")

    with step_col4:
        st.markdown("##### 4. Report")
        st.write("Persist findings to SQLite and export verifiable inspection summaries.")
