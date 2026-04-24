from __future__ import annotations

import streamlit as st

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

    page = st.sidebar.radio(
        "Navigation",
        [
            "Accueil",
            "Projet",
            "Donnees demo",
            "Base documentaire",
            "Supabase",
            "LLM",
            "Upload",
        ],
    )

    if page == "Accueil":
        render_home()
    elif page == "Projet":
        render_project()
    elif page == "Donnees demo":
        render_demo_data()
    elif page == "Base documentaire":
        render_document_catalog_page()
    elif page == "Supabase":
        render_supabase_page()
    elif page == "LLM":
        render_llm_page()
    else:
        render_upload()


if __name__ == "__main__":
    main()
