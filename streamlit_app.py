from pathlib import Path

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).parent
SAMPLE_CSV = ROOT_DIR / "data" / "samples" / "converted_data.csv"


@st.cache_data
def load_demo_data() -> pd.DataFrame:
    if not SAMPLE_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(SAMPLE_CSV)


def render_home() -> None:
    st.title("AAP Ingenia")
    st.caption("Prototype simple pour cadrer un futur outil d'analyse de dossiers")

    col1, col2, col3 = st.columns(3)
    col1.metric("Statut", "Prototype en ligne")
    col2.metric("Mode", "Simple et stable")
    col3.metric("Donnees demo", "Disponibles")

    st.markdown(
        """
        Cette version sert a garder une base propre et facile a deployer.

        Elle permet deja de :
        - presenter le projet ;
        - visualiser des donnees de demonstration ;
        - tester un premier upload de document ;
        - preparer la suite sans complexite inutile.
        """
    )


def render_project() -> None:
    st.subheader("Ou en est le projet ?")
    st.markdown(
        """
        - Le cadrage produit est deja bien avance
        - Le schema de donnees a ete reflechi
        - L'application web commence simplement
        - La connexion a une base reelle viendra plus tard
        """
    )

    st.subheader("Prochaine etape conseillee")
    st.write(
        "Construire un parcours d'upload simple, puis afficher les metadonnees du fichier avant toute analyse automatisee."
    )


def render_demo_data() -> None:
    st.subheader("Donnees de demonstration")
    df = load_demo_data()

    if df.empty:
        st.warning("Le fichier de demonstration est introuvable.")
        return

    st.dataframe(df, use_container_width=True)

    first_row = df.iloc[0]
    st.markdown("### Resume")
    st.write(first_row.get("resume_executif", "Aucun resume disponible."))


def render_upload() -> None:
    st.subheader("Upload et lecture simple")
    uploaded_file = st.file_uploader(
        "Depose un document de test",
        type=["pdf", "docx", "txt", "csv", "xlsx"],
    )

    if uploaded_file is None:
        st.info("Aucun document charge pour le moment.")
        return

    st.success("Document recu avec succes.")

    col1, col2 = st.columns(2)
    col1.write(f"Nom : `{uploaded_file.name}`")
    col2.write(f"Taille : `{uploaded_file.size}` octets")

    suffix = Path(uploaded_file.name).suffix.lower() or "inconnu"
    st.write(f"Type detecte : `{suffix}`")

    if suffix == ".txt":
        text_content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        st.markdown("### Apercu texte")
        st.text_area("Contenu detecte", text_content[:5000], height=250)
        st.write("Etape suivante : nettoyer et structurer ce texte.")
        return

    if suffix == ".csv":
        dataframe = pd.read_csv(uploaded_file)
        st.markdown("### Apercu tabulaire")
        st.dataframe(dataframe, use_container_width=True)
        st.write(f"Nombre de lignes : `{len(dataframe)}`")
        st.write(f"Nombre de colonnes : `{len(dataframe.columns)}`")
        return

    if suffix == ".xlsx":
        st.info("Le fichier Excel est bien recu. La lecture detaillee viendra dans l'etape suivante.")
        st.write("Etape suivante : lire les feuilles et afficher un apercu.")
        return

    if suffix == ".pdf":
        st.info("Le PDF est bien recu. L'extraction de texte n'est pas encore active.")
        st.write("Etape suivante : brancher une extraction de texte PDF.")
        return

    if suffix == ".docx":
        st.info("Le document Word est bien recu. La lecture du contenu viendra ensuite.")
        st.write("Etape suivante : extraire le texte du DOCX.")
        return

    st.write("Etape suivante : lecture du contenu et extraction de texte.")


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
            "Upload",
        ],
    )

    if page == "Accueil":
        render_home()
    elif page == "Projet":
        render_project()
    elif page == "Donnees demo":
        render_demo_data()
    else:
        render_upload()


if __name__ == "__main__":
    main()
