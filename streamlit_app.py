from pathlib import Path
import re

import pandas as pd
import streamlit as st
from docx import Document
from pypdf import PdfReader


ROOT_DIR = Path(__file__).parent
SAMPLE_CSV = ROOT_DIR / "data" / "samples" / "converted_data.csv"


@st.cache_data
def load_demo_data() -> pd.DataFrame:
    if not SAMPLE_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(SAMPLE_CSV)


def docx_to_markdown(document: Document) -> str:
    blocks = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if paragraph.style and "heading" in paragraph.style.name.lower():
            blocks.append(f"## {text}")
        else:
            blocks.append(text)
    return "\n\n".join(blocks)


def extract_text_metadata(text: str, filename: str) -> dict[str, str]:
    compact_text = re.sub(r"\s+", " ", text).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    title = lines[0] if lines else Path(filename).stem

    date_match = re.search(
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
        compact_text,
    )
    amount_match = re.search(
        r"\b\d[\d\s.,]{2,}\s?(?:€|euros?)\b",
        compact_text,
        flags=re.IGNORECASE,
    )
    org_match = re.search(
        r"\b(Région|Region|CNM|ADEME|BPI|France Travail|DEETS|Europe|Etat|Minist[eè]re)\b",
        compact_text,
        flags=re.IGNORECASE,
    )

    lower_name = filename.lower()
    if "appel" in lower_name or "aap" in lower_name:
        document_type = "appel a projets"
    elif "formulaire" in lower_name:
        document_type = "formulaire"
    elif "cadre" in lower_name:
        document_type = "cadre d'intervention"
    elif "reglement" in lower_name:
        document_type = "reglement"
    else:
        document_type = "document texte"

    return {
        "Titre probable": title[:120],
        "Type probable": document_type,
        "Date detectee": date_match.group(1) if date_match else "Non detectee",
        "Montant detecte": amount_match.group(0) if amount_match else "Non detecte",
        "Organisme detecte": org_match.group(1) if org_match else "Non detecte",
    }


def extract_table_metadata(dataframe: pd.DataFrame, filename: str) -> dict[str, str]:
    return {
        "Nom du fichier": filename,
        "Type probable": "tableau",
        "Nombre de lignes": str(len(dataframe)),
        "Nombre de colonnes": str(len(dataframe.columns)),
        "Colonnes detectees": ", ".join(str(col) for col in list(dataframe.columns)[:6]) or "Aucune",
    }


def render_metadata(metadata: dict[str, str]) -> None:
    st.markdown("### Metadonnees detectees")
    cols = st.columns(2)
    items = list(metadata.items())
    for index, (label, value) in enumerate(items):
        cols[index % 2].write(f"**{label}** : {value}")


def dataframe_to_markdown(dataframe: pd.DataFrame, title: str) -> str:
    preview_df = dataframe.head(20).fillna("")
    table_markdown = preview_df.to_markdown(index=False)
    return f"## {title}\n\n{table_markdown}"


def render_normalized_text(content: str, filename: str) -> None:
    st.markdown("### Source normalisee")
    st.text_area("Contenu normalise", content[:5000], height=260)
    st.download_button(
        "Telecharger la source normalisee",
        data=content,
        file_name=f"{Path(filename).stem}_normalise.md",
        mime="text/markdown",
    )


def process_uploaded_file(uploaded_file, category_label: str) -> None:
    st.markdown(f"## {category_label}")
    st.success("Document recu avec succes.")

    col1, col2 = st.columns(2)
    col1.write(f"Nom : `{uploaded_file.name}`")
    col2.write(f"Taille : `{uploaded_file.size}` octets")

    suffix = Path(uploaded_file.name).suffix.lower() or "inconnu"
    st.write(f"Type detecte : `{suffix}`")

    if suffix in {".txt", ".md"}:
        text_content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        render_metadata(extract_text_metadata(text_content, uploaded_file.name))
        st.markdown("### Apercu texte")
        st.text_area("Contenu detecte", text_content[:5000], height=250)
        render_normalized_text(text_content, uploaded_file.name)
        st.write("Etape suivante : nettoyer et structurer ce texte.")
        return

    if suffix == ".csv":
        dataframe = pd.read_csv(uploaded_file)
        render_metadata(extract_table_metadata(dataframe, uploaded_file.name))
        st.markdown("### Apercu tabulaire")
        st.dataframe(dataframe, use_container_width=True)
        st.write(f"Nombre de lignes : `{len(dataframe)}`")
        st.write(f"Nombre de colonnes : `{len(dataframe.columns)}`")
        normalized_text = dataframe_to_markdown(dataframe, uploaded_file.name)
        render_normalized_text(normalized_text, uploaded_file.name)
        return

    if suffix == ".xlsx":
        workbook = pd.read_excel(uploaded_file, sheet_name=None)
        sheet_names = list(workbook.keys())

        st.markdown("### Feuilles detectees")
        st.write(", ".join(f"`{name}`" for name in sheet_names))

        selected_sheet = st.selectbox("Choisir une feuille", sheet_names)
        selected_df = workbook[selected_sheet]
        csv_content = selected_df.to_csv(index=False)
        metadata = extract_table_metadata(selected_df, uploaded_file.name)
        metadata["Feuille selectionnee"] = selected_sheet
        render_metadata(metadata)

        st.markdown("### Apercu Excel")
        st.dataframe(selected_df, use_container_width=True)
        st.write(f"Lignes : `{len(selected_df)}`")
        st.write(f"Colonnes : `{len(selected_df.columns)}`")
        st.markdown("### Conversion CSV")
        st.text_area("CSV genere", csv_content[:5000], height=220)
        st.download_button(
            "Telecharger la feuille en CSV",
            data=csv_content,
            file_name=f"{Path(uploaded_file.name).stem}_{selected_sheet}.csv",
            mime="text/csv",
        )
        normalized_text = dataframe_to_markdown(selected_df, f"{uploaded_file.name} - {selected_sheet}")
        render_normalized_text(normalized_text, uploaded_file.name)
        return

    if suffix == ".pdf":
        reader = PdfReader(uploaded_file)
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages_text.append(page_text.strip())

        pdf_text = "\n\n".join(pages_text)

        if not pdf_text:
            st.warning("Le PDF a ete charge, mais aucun texte exploitable n'a ete detecte.")
            st.write("Il est possible que le document soit scanne ou image.")
            return

        render_metadata(extract_text_metadata(pdf_text, uploaded_file.name))
        st.markdown("### Apercu PDF")
        st.text_area("Texte detecte", pdf_text[:5000], height=300)
        st.write(f"Pages lues : `{len(reader.pages)}`")
        st.write(f"Pages avec texte : `{len(pages_text)}`")
        render_normalized_text(pdf_text, uploaded_file.name)
        return

    if suffix == ".docx":
        document = Document(uploaded_file)
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        text_content = "\n\n".join(paragraphs)
        markdown_content = docx_to_markdown(document)

        if not text_content:
            st.warning("Le document DOCX a ete charge, mais aucun texte exploitable n'a ete trouve.")
            return

        render_metadata(extract_text_metadata(text_content, uploaded_file.name))
        st.markdown("### Apercu DOCX")
        st.text_area("Texte detecte", text_content[:5000], height=300)
        st.write(f"Paragraphes detectes : `{len(paragraphs)}`")
        st.markdown("### Conversion Markdown")
        st.text_area("Markdown genere", markdown_content[:5000], height=260)
        st.download_button(
            "Telecharger en Markdown",
            data=markdown_content,
            file_name=f"{Path(uploaded_file.name).stem}.md",
            mime="text/markdown",
        )
        render_normalized_text(markdown_content, uploaded_file.name)
        return

    st.write("Etape suivante : lecture du contenu et extraction de texte.")


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


def render_upload_block(title: str, help_text: str, uploader_key: str) -> None:
    st.subheader(title)
    st.caption(help_text)
    uploaded_file = st.file_uploader(
        f"Depose un document pour : {title}",
        type=["pdf", "docx", "txt", "md", "csv", "xlsx"],
        key=uploader_key,
    )

    if uploaded_file is None:
        st.info("Aucun document charge pour ce bloc.")
        return

    process_uploaded_file(uploaded_file, title)


def render_upload() -> None:
    st.subheader("Upload structure en 3 blocs")
    st.write(
        "Le flux metier repose sur trois types de documents distincts : dossier, client et projet."
    )

    render_upload_block(
        "Documents dossier",
        "Documents cibles a analyser : appel a projets, reglement, cahier des charges, cadre d'intervention.",
        "upload_dossier",
    )
    st.divider()
    render_upload_block(
        "Documents client",
        "Documents qui decrivent la structure porteuse : presentation, statuts, references, plaquette.",
        "upload_client",
    )
    st.divider()
    render_upload_block(
        "Documents projet",
        "Documents qui decrivent l'action ou la demande : note d'intention, budget, description du projet.",
        "upload_projet",
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
