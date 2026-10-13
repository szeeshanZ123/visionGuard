"""
VisionGuard AI - Infrastructure Defect Detection and Reporting Application

Phase 1 Entry Point:
- Simple, professional landing page.
- Image ingestion and verification for road & infrastructure images.
- Technical metadata extraction.
- Clear placeholders for authentic AI model integration (Phase 2).
"""

import streamlit as st
from src.database.db import init_db, check_db_health
from src.components.landing import render_landing_page
from src.components.upload import render_upload_section


def setup_page():
    """Configures the Streamlit page layout and metadata."""
    st.set_page_config(
        page_title="VisionGuard AI - Infrastructure Defect Inspection",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def render_sidebar():
    """Renders the sidebar navigation and system status."""
    st.sidebar.markdown(
        """
        <div style="text-align: left; padding-bottom: 0.8rem;">
            <h2 style="margin: 0; display: inline-flex; align-items: center; gap: 0.5rem;">
                🛡️ VisionGuard AI
            </h2>
            <p style="color: #6B7280; font-size: 0.85rem; margin-top: 0.2rem;">
                Infrastructure Defect Detection
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("### Navigation")
    selected_page = st.sidebar.radio(
        "Go to",
        options=["🏠 Landing & Overview", "📷 Defect Inspection (Upload)"],
        index=0,
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")

    # System Status & Telemetry
    st.sidebar.markdown("### System Status")

    # DB Health check
    db_status = check_db_health()
    if db_status.get("connected"):
        st.sidebar.success("Database: Connected (SQLite)")
    else:
        st.sidebar.error("Database: Offline")

    st.sidebar.info("Model Engine: Staged for Phase 2")

    # Version / Build specs
    st.sidebar.markdown("---")
    st.sidebar.caption("Build: v0.1.0-phase1")
    st.sidebar.caption("Vision Core: OpenCV & Pillow")
    st.sidebar.caption("Phase: 1 of 4 (Ingestion & Foundations)")

    return selected_page


def main():
    """Main application routine."""
    setup_page()

    # Initialize storage scaffolding
    init_db()

    # Sidebar Navigation
    page = render_sidebar()

    # Route page
    if page == "🏠 Landing & Overview":
        render_landing_page()
    elif page == "📷 Defect Inspection (Upload)":
        render_upload_section()

    # Subtle Footer
    st.markdown("---")
    st.caption(
        "© VisionGuard AI • Built with Python, Streamlit, and OpenCV. "
        "Strict adherence to genuine AI models (No mock predictions)."
    )


if __name__ == "__main__":
    main()
