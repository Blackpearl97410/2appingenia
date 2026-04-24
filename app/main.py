import streamlit as st

from app.ui.pages import (
    render_home,
    render_next_steps,
    render_project_frame,
    render_swot,
)


def main() -> None:
    st.set_page_config(
        page_title="AAP Ingenia",
        page_icon="📁",
        layout="wide",
    )

    st.sidebar.title("Navigation")
    section = st.sidebar.radio(
        "Choisir une vue",
        [
            "Accueil",
            "Cadre du projet",
            "Feuille de route",
            "Donnees de demonstration",
        ],
    )

    if section == "Accueil":
        render_home()
    elif section == "Cadre du projet":
        render_project_frame()
    elif section == "Feuille de route":
        render_next_steps()
    else:
        render_swot()
