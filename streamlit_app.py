from pathlib import Path
from io import BytesIO
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


def get_uploaded_suffix(uploaded_file) -> str:
    return Path(uploaded_file.name).suffix.lower() or "inconnu"


def get_uploaded_bytes(uploaded_file) -> bytes:
    return uploaded_file.getvalue()


def parse_text_bytes(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="ignore")


def parse_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(BytesIO(file_bytes))


def parse_excel_bytes(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    return pd.read_excel(BytesIO(file_bytes), sheet_name=None)


def parse_pdf_bytes(file_bytes: bytes) -> tuple[str, int, int]:
    reader = PdfReader(BytesIO(file_bytes))
    pages_text = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages_text.append(page_text.strip())
    return "\n\n".join(pages_text), len(reader.pages), len(pages_text)


def parse_docx_bytes(file_bytes: bytes) -> tuple[str, str, int]:
    document = Document(BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    text_content = "\n\n".join(paragraphs)
    markdown_content = docx_to_markdown(document)
    return text_content, markdown_content, len(paragraphs)


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


def collect_block_insights(uploaded_files) -> dict[str, str]:
    dates = set()
    amounts = set()
    organizations = set()
    keywords = set()

    for uploaded_file in uploaded_files:
        suffix = get_uploaded_suffix(uploaded_file)
        file_bytes = get_uploaded_bytes(uploaded_file)

        if suffix in {".txt", ".md"}:
            text_content = parse_text_bytes(file_bytes)
            metadata = extract_text_metadata(text_content, uploaded_file.name)
            detected_date = metadata.get("Date detectee")
            detected_amount = metadata.get("Montant detecte")
            detected_org = metadata.get("Organisme detecte")
            if detected_date and detected_date != "Non detectee":
                dates.add(detected_date)
            if detected_amount and detected_amount != "Non detecte":
                amounts.add(detected_amount)
            if detected_org and detected_org != "Non detecte":
                organizations.add(detected_org)

            words = re.findall(r"\b[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ-]{3,}\b", text_content.lower())
            keywords.update(word for word in words[:20] if len(word) > 4)

        elif suffix == ".docx":
            text_content, _, _ = parse_docx_bytes(file_bytes)
            metadata = extract_text_metadata(text_content, uploaded_file.name)
            detected_date = metadata.get("Date detectee")
            detected_amount = metadata.get("Montant detecte")
            detected_org = metadata.get("Organisme detecte")
            if detected_date and detected_date != "Non detectee":
                dates.add(detected_date)
            if detected_amount and detected_amount != "Non detecte":
                amounts.add(detected_amount)
            if detected_org and detected_org != "Non detecte":
                organizations.add(detected_org)

        elif suffix == ".pdf":
            pdf_text, _, _ = parse_pdf_bytes(file_bytes)
            metadata = extract_text_metadata(pdf_text, uploaded_file.name)
            detected_date = metadata.get("Date detectee")
            detected_amount = metadata.get("Montant detecte")
            detected_org = metadata.get("Organisme detecte")
            if detected_date and detected_date != "Non detectee":
                dates.add(detected_date)
            if detected_amount and detected_amount != "Non detecte":
                amounts.add(detected_amount)
            if detected_org and detected_org != "Non detecte":
                organizations.add(detected_org)

        elif suffix == ".csv":
            dataframe = parse_csv_bytes(file_bytes)
            keywords.add("tableau")
            keywords.update(str(col).lower() for col in list(dataframe.columns)[:8])
        elif suffix == ".xlsx":
            workbook = parse_excel_bytes(file_bytes)
            keywords.add("tableau")
            for sheet_df in workbook.values():
                keywords.update(str(col).lower() for col in list(sheet_df.columns)[:5])

    return {
        "Dates reperees": ", ".join(sorted(dates)) if dates else "Aucune",
        "Montants reperes": ", ".join(sorted(amounts)) if amounts else "Aucun",
        "Organismes reperes": ", ".join(sorted(organizations)) if organizations else "Aucun",
        "Mots-cles simples": ", ".join(sorted(list(keywords))[:12]) if keywords else "Aucun",
    }


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


def build_upload_summary(uploaded_file) -> dict[str, str]:
    suffix = get_uploaded_suffix(uploaded_file)
    return {
        "Nom": uploaded_file.name,
        "Type": suffix,
        "Taille": f"{uploaded_file.size} octets",
        "Statut": "Charge",
    }


def render_global_summary(summary_map: dict[str, list[dict[str, str]]]) -> None:
    st.subheader("Recapitulatif global")
    col1, col2, col3 = st.columns(3)

    loaded_count = sum(1 for value in summary_map.values() if value)
    col1.metric("Blocs complets", str(loaded_count))
    col2.metric("Blocs manquants", str(len(summary_map) - loaded_count))
    col3.metric("Documents charges", str(sum(len(value) for value in summary_map.values())))

    for block_name, infos in summary_map.items():
        if not infos:
            st.warning(f"{block_name} : aucun document charge")
        else:
            st.success(f"{block_name} : {len(infos)} document(s)")
            for info in infos:
                st.write(f"- {info['Nom']} | {info['Type']} | {info['Taille']}")


def assess_block_completeness(uploaded_files) -> dict[str, str]:
    if not uploaded_files:
        return {
            "Statut bloc": "vide",
            "Niveau": "0/3",
            "Commentaire": "Aucun document n'a ete charge dans ce bloc.",
        }

    suffixes = {
        get_uploaded_suffix(uploaded_file)
        for uploaded_file in uploaded_files
    }
    file_count = len(uploaded_files)

    if file_count >= 2 and len(suffixes) >= 2:
        return {
            "Statut bloc": "suffisant",
            "Niveau": "3/3",
            "Commentaire": "Le bloc contient plusieurs pieces et au moins deux formats ou types apparents.",
        }

    if file_count >= 1:
        return {
            "Statut bloc": "partiel",
            "Niveau": "2/3",
            "Commentaire": "Le bloc contient deja des pieces, mais semble encore incomplet pour une analyse plus fiable.",
        }

    return {
        "Statut bloc": "vide",
        "Niveau": "0/3",
        "Commentaire": "Aucun document n'a ete charge dans ce bloc.",
    }


def render_block_summary(title: str, uploaded_files) -> None:
    st.markdown(f"## Synthese du bloc : {title}")

    type_counts: dict[str, int] = {}
    total_size = 0
    for uploaded_file in uploaded_files:
        suffix = get_uploaded_suffix(uploaded_file)
        type_counts[suffix] = type_counts.get(suffix, 0) + 1
        total_size += uploaded_file.size

    col1, col2, col3 = st.columns(3)
    col1.metric("Documents", str(len(uploaded_files)))
    col2.metric("Types detectes", str(len(type_counts)))
    col3.metric("Taille totale", f"{total_size} octets")

    st.write(
        "Repartition : "
        + ", ".join(f"`{file_type}` x {count}" for file_type, count in sorted(type_counts.items()))
    )
    render_metadata(assess_block_completeness(uploaded_files))
    render_metadata(collect_block_insights(uploaded_files))


def build_block_normalized_text(title: str, uploaded_files) -> str:
    chunks = [f"# {title}"]
    for uploaded_file in uploaded_files:
        suffix = get_uploaded_suffix(uploaded_file)
        file_bytes = get_uploaded_bytes(uploaded_file)
        chunks.append(f"## DOCUMENT: {uploaded_file.name}")
        chunks.append(f"Type: {suffix}")

        if suffix in {".txt", ".md"}:
            text_content = parse_text_bytes(file_bytes)
            chunks.append(text_content[:10000] or "[contenu vide]")
        elif suffix == ".csv":
            dataframe = parse_csv_bytes(file_bytes)
            chunks.append(dataframe_to_markdown(dataframe, uploaded_file.name))
        elif suffix == ".xlsx":
            workbook = parse_excel_bytes(file_bytes)
            for sheet_name, sheet_df in workbook.items():
                chunks.append(dataframe_to_markdown(sheet_df, f"{uploaded_file.name} - {sheet_name}"))
        elif suffix == ".pdf":
            pdf_text, _, _ = parse_pdf_bytes(file_bytes)
            chunks.append(pdf_text[:10000] or "[aucun texte exploitable]")
        elif suffix == ".docx":
            _, markdown_content, _ = parse_docx_bytes(file_bytes)
            chunks.append(markdown_content[:10000] or "[aucun texte exploitable]")
        else:
            chunks.append("[type non pris en charge]")

    return "\n\n".join(chunks)


def process_uploaded_file(uploaded_file, category_label: str, file_index: int) -> None:
    st.markdown(f"### {category_label} - fichier {file_index}")
    st.success("Document recu avec succes.")

    col1, col2 = st.columns(2)
    col1.write(f"Nom : `{uploaded_file.name}`")
    col2.write(f"Taille : `{uploaded_file.size}` octets")

    suffix = get_uploaded_suffix(uploaded_file)
    file_bytes = get_uploaded_bytes(uploaded_file)
    st.write(f"Type detecte : `{suffix}`")

    if suffix in {".txt", ".md"}:
        text_content = parse_text_bytes(file_bytes)
        render_metadata(extract_text_metadata(text_content, uploaded_file.name))
        st.markdown("### Apercu texte")
        st.text_area("Contenu detecte", text_content[:5000], height=250)
        render_normalized_text(text_content, uploaded_file.name)
        st.write("Etape suivante : nettoyer et structurer ce texte.")
        return

    if suffix == ".csv":
        dataframe = parse_csv_bytes(file_bytes)
        render_metadata(extract_table_metadata(dataframe, uploaded_file.name))
        st.markdown("### Apercu tabulaire")
        st.dataframe(dataframe, use_container_width=True)
        st.write(f"Nombre de lignes : `{len(dataframe)}`")
        st.write(f"Nombre de colonnes : `{len(dataframe.columns)}`")
        normalized_text = dataframe_to_markdown(dataframe, uploaded_file.name)
        render_normalized_text(normalized_text, uploaded_file.name)
        return

    if suffix == ".xlsx":
        workbook = parse_excel_bytes(file_bytes)
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
        pdf_text, page_count, text_page_count = parse_pdf_bytes(file_bytes)

        if not pdf_text:
            st.warning("Le PDF a ete charge, mais aucun texte exploitable n'a ete detecte.")
            st.write("Il est possible que le document soit scanne ou image.")
            return

        render_metadata(extract_text_metadata(pdf_text, uploaded_file.name))
        st.markdown("### Apercu PDF")
        st.text_area("Texte detecte", pdf_text[:5000], height=300)
        st.write(f"Pages lues : `{page_count}`")
        st.write(f"Pages avec texte : `{text_page_count}`")
        render_normalized_text(pdf_text, uploaded_file.name)
        return

    if suffix == ".docx":
        text_content, markdown_content, paragraph_count = parse_docx_bytes(file_bytes)

        if not text_content:
            st.warning("Le document DOCX a ete charge, mais aucun texte exploitable n'a ete trouve.")
            return

        render_metadata(extract_text_metadata(text_content, uploaded_file.name))
        st.markdown("### Apercu DOCX")
        st.text_area("Texte detecte", text_content[:5000], height=300)
        st.write(f"Paragraphes detectes : `{paragraph_count}`")
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


def render_upload_block(title: str, help_text: str, uploader_key: str) -> list[dict[str, str]]:
    st.subheader(title)
    st.caption(help_text)
    uploaded_files = st.file_uploader(
        f"Depose un ou plusieurs documents pour : {title}",
        type=["pdf", "docx", "txt", "md", "csv", "xlsx"],
        key=uploader_key,
        accept_multiple_files=True,
    )

    if not uploaded_files:
        st.info("Aucun document charge pour ce bloc.")
        return []

    summaries = []
    for index, uploaded_file in enumerate(uploaded_files, start=1):
        process_uploaded_file(uploaded_file, title, index)
        summaries.append(build_upload_summary(uploaded_file))
        if index < len(uploaded_files):
            st.divider()

    st.divider()
    render_block_summary(title, uploaded_files)
    block_normalized_text = build_block_normalized_text(title, uploaded_files)
    render_normalized_text(block_normalized_text, title.replace(" ", "_").lower())

    return summaries


def render_upload() -> None:
    st.subheader("Upload structure en 3 blocs")
    st.write(
        "Le flux metier repose sur trois types de documents distincts : dossier, client et projet."
    )

    summary_map = {}

    summary_map["Documents dossier"] = render_upload_block(
        "Documents dossier",
        "Documents cibles a analyser : appel a projets, reglement, cahier des charges, cadre d'intervention.",
        "upload_dossier",
    )
    st.divider()
    summary_map["Documents client"] = render_upload_block(
        "Documents client",
        "Documents qui decrivent la structure porteuse : presentation, statuts, references, plaquette.",
        "upload_client",
    )
    st.divider()
    summary_map["Documents projet"] = render_upload_block(
        "Documents projet",
        "Documents qui decrivent l'action ou la demande : note d'intention, budget, description du projet.",
        "upload_projet",
    )
    st.divider()
    render_global_summary(summary_map)


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
