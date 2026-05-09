from __future__ import annotations

import streamlit as st

from app.ui.styles import inject_global_styles, render_theme_toggle

from app.ui.pages import (
    render_demo_data,
    render_document_catalog_page,
    render_home,
    render_llm_page,
    render_project,
    render_supabase_page,
    render_upload,
)


def main() -> None:
    st.set_page_config(
        page_title="AAP Ingenia",
        page_icon="📁",
        layout="wide",
    )

    inject_global_styles()

    st.sidebar.markdown("## 📁 AAP Ingenia")
    render_theme_toggle()
    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigation",
        [
            "Analyser un dossier",
            "Accueil",
            "Donnees demo",
            "Base documentaire",
            "Configuration",
            "Projet",
        ],
    )

    if page == "Analyser un dossier":
        render_upload()
    elif page == "Accueil":
        render_home()
    elif page == "Donnees demo":
        render_demo_data()
    elif page == "Base documentaire":
        render_document_catalog_page()
    elif page == "Configuration":
        render_supabase_page()
        st.divider()
        render_llm_page()
    else:
        render_project()


if __name__ == "__main__":
    main()
