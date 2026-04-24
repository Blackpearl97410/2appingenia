from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

import streamlit as st
from app.services.data_loader import (
    load_document_catalog,
    load_smoke_test_results,
    load_swot_data as load_demo_data,
)
from app.services.document_catalog import build_smoke_test_case
from app.services.metadata import (
    add_detected_value,
    extract_keywords_from_text,
    extract_table_metadata,
    extract_text_metadata,
    format_detected_values,
)
from app.services.normalizers import (
    classify_sheet,
    dataframe_to_markdown,
    filter_business_sheets,
    workbook_to_markdown,
)
from app.services.parsers import (
    get_uploaded_bytes,
    get_uploaded_suffix,
    parse_csv_bytes,
    parse_docx_bytes,
    parse_excel_bytes,
    parse_pdf_bytes,
    parse_text_bytes,
)
from app.services.wf2 import (
    build_bridge_from_wf2,
    extract_wf2a_structured,
    extract_wf2b_structured,
    summarize_wf2b_client_profile,
    summarize_wf2b_project_data,
)
from app.services.wf3 import build_wf3_analysis
from app.services.wf4 import build_wf4_outputs
from app.services.supabase_bridge import describe_supabase_readiness
from app.services.llm_client import describe_llm_readiness
from app.services.bridge_completion import merge_completed_bridge_into_wf2
from app.services.persistence import persist_pipeline_outputs
from app.services.pipeline_runtime import resolve_pipeline_outputs
from app.services.wf2_llm import request_wf2a_llm_payload
from app.services.client_manager import list_clients, create_client


def render_metadata(metadata: dict[str, str]) -> None:
    st.markdown("### Metadonnees detectees")
    cols = st.columns(2)
    items = list(metadata.items())
    for index, (label, value) in enumerate(items):
        cols[index % 2].write(f"**{label}** : {value}")


def build_files_signature(block_files_map: dict[str, list]) -> str:
    serializable = {}
    for block_name, files in block_files_map.items():
        serializable[block_name] = [
            {
                "name": uploaded_file.name,
                "size": getattr(uploaded_file, "size", None),
                "type": getattr(uploaded_file, "type", None),
            }
            for uploaded_file in files
        ]
    return json.dumps(serializable, sort_keys=True, ensure_ascii=False)


def get_active_pipeline_outputs(signature: str) -> dict[str, object] | None:
    stored_signature = st.session_state.get("pipeline_signature")
    if stored_signature != signature:
        return None
    return st.session_state.get("pipeline_outputs")


def store_pipeline_outputs(signature: str, outputs: dict[str, object], persistence: dict[str, object] | None = None) -> None:
    st.session_state["pipeline_signature"] = signature
    st.session_state["pipeline_outputs"] = outputs
    st.session_state["pipeline_persistence"] = persistence or {}


def choose_priority_value(block_candidates: dict[str, str], priority_order: list[str]) -> str:
    for block_name in priority_order:
        value = block_candidates.get(block_name)
        if value and value not in {"Aucun", "Aucune"}:
            return f"{value} ({block_name})"
    return "Aucun"


def compute_global_prescore(
    available_blocks: list[str],
    block_criteria_scores: dict[str, int],
    issues: list[str],
) -> tuple[str, str]:
    score = 0

    score += len(available_blocks) * 10
    score += sum(min(points, 30) for points in block_criteria_scores.values())
    score -= min(len(issues), 6) * 10

    score = max(0, min(score, 100))

    if score >= 75:
        label = "bon"
    elif score >= 45:
        label = "moyen"
    else:
        label = "faible"

    return label, f"{score}/100"


def aggregate_block_text(uploaded_files) -> str:
    chunks = []
    for uploaded_file in uploaded_files:
        suffix = get_uploaded_suffix(uploaded_file)
        file_bytes = get_uploaded_bytes(uploaded_file)

        if suffix in {".txt", ".md"}:
            chunks.append(parse_text_bytes(file_bytes))
        elif suffix == ".docx":
            text_content, _, _ = parse_docx_bytes(file_bytes)
            chunks.append(text_content)
        elif suffix == ".pdf":
            pdf_text, _, _, _ = parse_pdf_bytes(file_bytes)
            chunks.append(pdf_text)
        elif suffix == ".csv":
            dataframe = parse_csv_bytes(file_bytes)
            chunks.append(" ".join(str(col) for col in dataframe.columns))
        elif suffix == ".xlsx":
            workbook = parse_excel_bytes(file_bytes)
            business_sheets, informative_sheets = filter_business_sheets(workbook)
            for sheet_name, sheet_df in business_sheets.items():
                chunks.append(sheet_name)
                chunks.append(" ".join(str(col) for col in sheet_df.columns))
            for sheet_name in informative_sheets:
                chunks.append(sheet_name)

    return "\n".join(chunk for chunk in chunks if chunk).lower()


def evaluate_block_criteria(block_name: str, uploaded_files, insights: dict[str, str]) -> dict[str, str | int]:
    text = aggregate_block_text(uploaded_files)
    dates_value = insights.get("Dates reperees", "Aucune")
    org_value = insights.get("Organismes reperes", "Aucun")
    amount_value = insights.get("Montants reperes", "Aucun")

    checks: list[str] = []
    score = 0

    def add_check(condition: bool, label: str) -> None:
        nonlocal score
        if condition:
            checks.append(label)
            score += 10

    if block_name == "Documents dossier":
        add_check(dates_value != "Aucune", "date de reference detectee")
        add_check(org_value != "Aucun", "organisme detecte")
        add_check(
            any(keyword in text for keyword in ["appel", "aap", "reglement", "cadre", "eligibilite", "candidature"]),
            "regles ou contexte d'appel detectes",
        )
    elif block_name == "Documents client":
        add_check(org_value != "Aucun", "identite de structure detectee")
        add_check(
            any(keyword in text for keyword in ["siret", "association", "sas", "sarl", "statuts", "adresse", "siege"]),
            "elements administratifs detectes",
        )
        add_check(
            any(keyword in text for keyword in ["activite", "presentation", "reference", "competence", "experience"]),
            "elements de presentation detectes",
        )
    elif block_name == "Documents projet":
        add_check(amount_value != "Aucun", "montant ou budget detecte")
        add_check(
            any(keyword in text for keyword in ["projet", "objectif", "action", "planning", "calendrier", "beneficiaire"]),
            "contenu projet detecte",
        )
        add_check(
            any(keyword in text for keyword in ["budget", "financement", "depense", "cout", "recette"]),
            "elements budgetaires detectes",
        )

    if score >= 30:
        status = "fort"
    elif score >= 20:
        status = "moyen"
    elif score >= 10:
        status = "faible"
    else:
        status = "insuffisant"

    return {
        "score": score,
        "status": status,
        "checks": " | ".join(checks) if checks else "aucun critere fort detecte",
    }


def build_block_recommendations(block_name: str, insights: dict[str, str], criteria: dict[str, str | int]) -> str:
    recommendations: list[str] = []

    dates_value = insights.get("Dates reperees", "Aucune")
    org_value = insights.get("Organismes reperes", "Aucun")
    amount_value = insights.get("Montants reperes", "Aucun")
    status = str(criteria.get("status", "insuffisant"))

    if block_name == "Documents dossier":
        if dates_value == "Aucune":
            recommendations.append("ajouter un document mentionnant clairement la date limite ou les dates de reference")
        if org_value == "Aucun":
            recommendations.append("ajouter un reglement ou cadre indiquant l'organisme financeur")
        if status in {"faible", "insuffisant"}:
            recommendations.append("ajouter une piece de cadrage type appel, reglement ou cahier des charges")

    elif block_name == "Documents client":
        if org_value == "Aucun":
            recommendations.append("ajouter un document d'identite de structure : statuts, presentation ou fiche entreprise")
        if status in {"faible", "insuffisant"}:
            recommendations.append("ajouter des elements administratifs ou de presentation : SIRET, adresse, activite, references")

    elif block_name == "Documents projet":
        if amount_value == "Aucun":
            recommendations.append("ajouter un budget, plan de financement ou document avec montant de projet")
        if dates_value == "Aucune":
            recommendations.append("ajouter un planning ou calendrier du projet")
        if status in {"faible", "insuffisant"}:
            recommendations.append("ajouter une note d'intention ou une description detaillee du projet")

    if not recommendations:
        return "bloc suffisamment renseigne pour l'etape actuelle"

    return " | ".join(recommendations[:4])


def extract_wf2a_dossier_criteria(uploaded_files) -> list[dict[str, str]]:
    return extract_wf2a_structured(uploaded_files).get("criteres", [])


def render_wf2a_dossier_section(
    dossier_files,
    wf2a_structured: dict[str, object] | None = None,
    execution_meta: dict[str, object] | None = None,
) -> None:
    st.subheader("WF2a local - Extraction criteres dossier")

    if not dossier_files:
        st.info("Aucun document dossier charge pour lancer l'extraction WF2a locale.")
        return

    wf2a = wf2a_structured or extract_wf2a_structured(dossier_files)
    criteria = wf2a.get("criteres", [])
    metadata = wf2a.get("metadata", {})

    if not criteria:
        st.warning("Aucun critere explicite n'a ete detecte dans le bloc dossier.")
        return

    if execution_meta:
        st.caption(
            f"Moteur actif : {execution_meta.get('engine', 'heuristique_locale')}"
            + (" (fallback local)" if execution_meta.get("fallback_used") else "")
        )

    st.markdown("### Metadata WF2a")
    render_metadata({
        "Type dossier detecte": metadata.get("type_dossier_detecte", "autre"),
        "Financeur detecte": metadata.get("financeur_detecte", "Non detecte"),
        "Montant max detecte": metadata.get("montant_max_detecte", "Non detecte"),
        "Date limite detectee": metadata.get("date_limite_detectee", "Non detectee"),
        "Nombre de criteres": str(metadata.get("nb_criteres_extraits", 0)),
        "Mode extraction": metadata.get("mode_extraction", "inconnu"),
    })

    st.write(f"{len(criteria)} critere(s) detecte(s)")
    for index, criterion in enumerate(criteria, start=1):
        st.markdown(
            f"**{index}. {criterion['libelle']}**  \n"
            f"Categorie : `{criterion['categorie']}`  \n"
            f"Domaine : `{criterion['domaine']}`  \n"
            f"Detail : {criterion['detail']}  \n"
            f"Source document : `{criterion.get('source_document', 'inconnu')}`  \n"
            f"Niveau de confiance : `{criterion.get('niveau_confiance', 'moyen')}`  \n"
            f"Validation requise : `{criterion.get('necessite_validation', False)}`  \n"
            f"Source texte : {criterion.get('source_texte', '')[:220]}"
        )


def extract_wf2b_client_profile(client_files) -> dict[str, str]:
    wf2b = extract_wf2b_structured(client_files, [])
    return summarize_wf2b_client_profile(wf2b)


def extract_wf2b_project_data(project_files) -> dict[str, str]:
    wf2b = extract_wf2b_structured([], project_files)
    return summarize_wf2b_project_data(wf2b)


def render_wf2b_section(
    client_files,
    project_files,
    wf2b_structured: dict[str, object] | None = None,
    execution_meta: dict[str, object] | None = None,
) -> None:
    st.subheader("WF2b local - Profil client et donnees projet")
    wf2b = wf2b_structured or extract_wf2b_structured(client_files, project_files)

    if execution_meta:
        st.caption(
            f"Moteur actif : {execution_meta.get('engine', 'heuristique_locale')}"
            + (" (fallback local)" if execution_meta.get("fallback_used") else "")
        )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Profil client")
        if not client_files:
            st.info("Aucun document client charge pour l'extraction WF2b locale.")
        else:
            render_metadata(summarize_wf2b_client_profile(wf2b))

    with col2:
        st.markdown("### Donnees projet")
        if not project_files:
            st.info("Aucun document projet charge pour l'extraction WF2b locale.")
        else:
            render_metadata(summarize_wf2b_project_data(wf2b))

    with st.expander("Voir la structure WF2b preparee pour un futur LLM", expanded=False):
        profil_client = wf2b.get("profil_client", {})
        donnees_projet = wf2b.get("donnees_projet", {})
        st.write("**Profil client structure**")
        render_metadata({
            "Nom structure": profil_client.get("nom_structure", {}).get("value", "Non detecte"),
            "Forme juridique": profil_client.get("forme_juridique", {}).get("value", "Non detectee"),
            "Source client": profil_client.get("forme_juridique", {}).get("source_document", ""),
            "Confiance forme juridique": profil_client.get("forme_juridique", {}).get("niveau_confiance", "moyen"),
        })
        st.write("**Donnees projet structurees**")
        render_metadata({
            "Titre projet": donnees_projet.get("titre_projet", {}).get("value", "Non detecte"),
            "Montant projet": donnees_projet.get("montant_detecte", {}).get("value", "Non detecte"),
            "Source projet": donnees_projet.get("titre_projet", {}).get("source_document", ""),
            "Confiance montant": donnees_projet.get("montant_detecte", {}).get("niveau_confiance", "moyen"),
        })


def build_comparable_bridge(dossier_files, client_files, project_files) -> dict[str, str]:
    wf2a = extract_wf2a_structured(dossier_files) if dossier_files else {"criteres": [], "metadata": {}}
    wf2b = extract_wf2b_structured(client_files, project_files) if (client_files or project_files) else {
        "profil_client": {},
        "donnees_projet": {},
    }
    return build_bridge_from_wf2(wf2a, wf2b)



def summarize_criterion_match_label(value: str) -> str:
    mapping = {
        "valide": "solide",
        "a_confirmer": "a confirmer",
        "manquant": "manquant",
        "non_valide": "ecart",
    }
    return mapping.get(value, value or "a verifier")


def apply_manual_completion(bridge: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    completed = dict(bridge)
    for key, value in overrides.items():
        cleaned = value.strip()
        if not cleaned:
            continue
        if "__append__" in key:
            target_key = key.split("__append__", 1)[0]
            existing_value = completed.get(target_key, "")
            if existing_value in {"", "Aucun", "Aucune", "Non detecte", "Non detectee", "A verifier"}:
                completed[target_key] = cleaned
            else:
                completed[target_key] = f"{existing_value} | {cleaned}"
        else:
            completed[key] = cleaned
    return completed


def is_missing_bridge_value(field_key: str, value: str) -> bool:
    missing_values = {
        "type_structure_requise": {"A verifier", ""},
        "date_limite_dossier": {"Aucune", ""},
        "montant_dossier": {"Aucun", ""},
        "conditions_dossier": {"Aucune", ""},
        "type_structure_client": {"Non detectee", ""},
        "identite_client": {"Aucune", ""},
        "montant_projet": {"Non detecte", ""},
        "dates_projet": {"Aucune", ""},
        "elements_projet": {"Aucun", ""},
    }
    return value in missing_values.get(field_key, {""})


def format_loaded_documents_label(uploaded_files) -> str:
    if not uploaded_files:
        return "aucun document charge"
    names = [uploaded_file.name for uploaded_file in uploaded_files]
    if len(names) <= 2:
        return ", ".join(names)
    return ", ".join(names[:2]) + f" (+{len(names) - 2} autre(s))"


def infer_block_document_context(uploaded_files) -> set[str]:
    context_tags = set()
    for uploaded_file in uploaded_files:
        name = uploaded_file.name.lower()
        if "reglement" in name or "règlement" in name:
            context_tags.add("reglement")
        if "appel" in name or "aap" in name or "cahier" in name:
            context_tags.add("appel")
        if "formulaire" in name:
            context_tags.add("formulaire")
        if "statut" in name:
            context_tags.add("statuts")
        if "reference" in name or "référence" in name:
            context_tags.add("references")
        if "plaquette" in name or "presentation" in name or "présentation" in name:
            context_tags.add("presentation")
        if "budget" in name:
            context_tags.add("budget")
        if "planning" in name or "calendrier" in name:
            context_tags.add("planning")
        if "projet" in name or "note" in name:
            context_tags.add("projet")
    return context_tags


def get_dynamic_field_label(section_title: str, field_key: str, context_tags: set[str]) -> str:
    if section_title == "Documents dossier":
        if field_key == "type_structure_requise":
            if "reglement" in context_tags or "appel" in context_tags:
                return "Structure eligible selon le dossier"
            return "Type de structure requis"
        if field_key == "date_limite_dossier":
            if "formulaire" in context_tags:
                return "Date limite ou date de depot du formulaire"
            return "Date limite du dossier"
        if field_key == "montant_dossier":
            if "budget" in context_tags:
                return "Montant, plafond ou enveloppe du dossier"
            return "Montant ou plafond du dossier"
        if field_key == "conditions_dossier":
            if "reglement" in context_tags:
                return "Conditions d'eligibilite ou pieces du reglement"
            if "formulaire" in context_tags:
                return "Champs obligatoires ou pieces du formulaire"
            return "Conditions ou pieces demandees"

    if section_title == "Documents client":
        if field_key == "type_structure_client":
            if "statuts" in context_tags:
                return "Forme juridique issue des statuts"
            return "Type de structure du client"
        if field_key == "identite_client":
            if "references" in context_tags:
                return "Activites, references ou experience du client"
            if "presentation" in context_tags:
                return "Identite, activite ou presentation du client"
            return "Identite, activite ou references du client"

    if section_title == "Documents projet":
        if field_key == "montant_projet":
            if "budget" in context_tags:
                return "Montant ou budget du projet"
            return "Montant du projet"
        if field_key == "dates_projet":
            if "planning" in context_tags:
                return "Dates, planning ou calendrier du projet"
            return "Dates ou calendrier du projet"
        if field_key == "elements_projet":
            if "projet" in context_tags:
                return "Objectifs, actions ou livrables du projet"
            return "Elements clefs du projet"

    fallback_labels = {
        "type_structure_requise": "Type de structure requis",
        "date_limite_dossier": "Date limite du dossier",
        "montant_dossier": "Montant du dossier",
        "conditions_dossier": "Conditions du dossier",
        "type_structure_client": "Type de structure du client",
        "identite_client": "Identite du client",
        "montant_projet": "Montant du projet",
        "dates_projet": "Dates du projet",
        "elements_projet": "Elements du projet",
    }
    return fallback_labels.get(field_key, field_key)


def build_manual_fields_for_section(section_title: str, context_tags: set[str]) -> list[tuple[str, str, str, str, str]]:
    if section_title == "Documents dossier":
        fields = [
            ("type_structure_requise", "type_structure_requise", "text_input", "Type de structure requis", "dossier"),
            ("date_limite_dossier", "date_limite_dossier", "text_input", "Date limite du dossier", "dossier"),
            ("montant_dossier", "montant_dossier", "text_input", "Montant ou plafond du dossier", "dossier"),
            ("conditions_dossier", "conditions_dossier", "text_area", "Conditions ou pieces demandees", "dossier"),
        ]
        if "reglement" in context_tags or "appel" in context_tags:
            fields.extend([
                ("conditions_dossier__append__public_eligible", "conditions_dossier", "text_input", "Public ou structure eligible", "dossier_public"),
                ("conditions_dossier__append__pieces_obligatoires", "conditions_dossier", "text_area", "Pieces obligatoires a fournir", "dossier_pieces"),
            ])
        if "budget" in context_tags:
            fields.append(
                ("conditions_dossier__append__depenses_eligibles", "conditions_dossier", "text_area", "Depenses ou postes eligibles", "dossier_depenses")
            )
        if "formulaire" in context_tags:
            fields.append(
                ("conditions_dossier__append__rubriques_obligatoires", "conditions_dossier", "text_area", "Rubriques obligatoires du formulaire", "dossier_rubriques")
            )
        return fields

    if section_title == "Documents client":
        fields = [
            ("type_structure_client", "type_structure_client", "text_input", "Type de structure du client", "client"),
            ("identite_client", "identite_client", "text_area", "Identite, activite ou references du client", "client"),
        ]
        if "statuts" in context_tags:
            fields.extend([
                ("identite_client__append__nom_structure", "identite_client", "text_input", "Nom de la structure", "client_nom"),
                ("identite_client__append__siret", "identite_client", "text_input", "SIRET ou identifiant", "client_siret"),
            ])
        if "references" in context_tags:
            fields.append(
                ("identite_client__append__references", "identite_client", "text_area", "References ou realisations marquantes", "client_references")
            )
        if "presentation" in context_tags:
            fields.append(
                ("identite_client__append__domaines", "identite_client", "text_area", "Domaines d'activite ou competences", "client_domaines")
            )
        return fields

    if section_title == "Documents projet":
        fields = [
            ("montant_projet", "montant_projet", "text_input", "Montant du projet", "projet"),
            ("dates_projet", "dates_projet", "text_input", "Dates ou calendrier du projet", "projet"),
            ("elements_projet", "elements_projet", "text_area", "Elements clefs du projet", "projet"),
        ]
        if "budget" in context_tags:
            fields.extend([
                ("elements_projet__append__cout_total", "elements_projet", "text_input", "Cout total ou budget global", "projet_cout_total"),
                ("elements_projet__append__cofinancement", "elements_projet", "text_input", "Cofinancement ou autres financeurs", "projet_cofinancement"),
            ])
        if "planning" in context_tags:
            fields.append(
                ("elements_projet__append__planning", "elements_projet", "text_area", "Etapes ou planning du projet", "projet_planning")
            )
        if "projet" in context_tags:
            fields.append(
                ("elements_projet__append__beneficiaires", "elements_projet", "text_area", "Public vise, objectifs ou livrables", "projet_beneficiaires")
            )
        return fields

    return []


def render_dynamic_manual_field(
    input_key: str,
    field_type: str,
    base_label: str,
    source_label: str,
    key_suffix: str,
    height: int = 120,
) -> str:
    input_label = f"{base_label} a completer"
    help_text = f"Source concernee : {source_label}"

    if field_type == "text_area":
        return st.text_area(
            input_label,
            value="",
            key=f"manual_{input_key}_{key_suffix}",
            help=help_text,
            height=height,
            placeholder=f"Saisir {base_label.lower()}",
        )

    return st.text_input(
        input_label,
        value="",
        key=f"manual_{input_key}_{key_suffix}",
        help=help_text,
        placeholder=f"Saisir {base_label.lower()}",
    )


def render_manual_completion_widget(bridge: dict[str, str], dossier_files, client_files, project_files) -> dict[str, str]:
    st.markdown("### Completion manuelle des donnees manquantes")
    st.caption("Le widget s'adapte aux blocs charges et ne propose que les informations encore manquantes ou trop faibles pour le WF3 local.")

    overrides = {}
    sections = [
        (
            "Documents dossier",
            dossier_files,
        ),
        (
            "Documents client",
            client_files,
        ),
        (
            "Documents projet",
            project_files,
        ),
    ]

    displayed_fields = 0

    for section_title, section_files in sections:
        source_label = format_loaded_documents_label(section_files)
        context_tags = infer_block_document_context(section_files)
        fields = build_manual_fields_for_section(section_title, context_tags)
        missing_fields = [
            field for field in fields
            if is_missing_bridge_value(field[1], bridge.get(field[1], ""))
        ]

        if not missing_fields:
            continue

        displayed_fields += len(missing_fields)
        with st.expander(f"{section_title} a completer", expanded=True):
            st.caption(f"Documents charges : {source_label}")
            for input_key, target_key, field_type, base_label, key_suffix in missing_fields:
                dynamic_label = get_dynamic_field_label(section_title, target_key, context_tags)
                if input_key != target_key:
                    dynamic_label = base_label
                overrides[input_key] = render_dynamic_manual_field(
                    input_key,
                    field_type,
                    dynamic_label,
                    source_label,
                    key_suffix,
                )

    if displayed_fields == 0:
        st.success("Aucune donnee prioritaire ne semble manquer dans le pont actuel.")

    return apply_manual_completion(bridge, overrides)


def render_bridge_section(bridge: dict[str, str], dossier_files, client_files, project_files) -> dict[str, str]:
    st.subheader("Pont local - Donnees comparables WF2a/WF2b")
    render_metadata(bridge)
    st.divider()
    completed_bridge = render_manual_completion_widget(bridge, dossier_files, client_files, project_files)
    st.markdown("### Pont apres completion manuelle")
    render_metadata(completed_bridge)
    return completed_bridge


def split_bridge_items(value: str) -> list[str]:
    if value in {"", "Aucun", "Aucune", "Non detecte", "Non detectee", "A verifier"}:
        return []
    parts = re.split(r"\s*\|\s*|,\s*", value)
    return [part.strip() for part in parts if part.strip()]


def contains_any_keyword(items: list[str], keywords: list[str]) -> bool:
    normalized_items = " ".join(items).lower()
    return any(keyword in normalized_items for keyword in keywords)


def compute_wf3_local(bridge: dict[str, str], global_bridge: dict[str, str] | None = None) -> dict[str, str]:
    score = 0
    justifications: list[str] = []
    manques: list[str] = []
    details: list[str] = []

    required_structure = bridge.get("type_structure_requise", "A verifier")
    client_structure = bridge.get("type_structure_client", "Non detectee")
    dossier_date = bridge.get("date_limite_dossier", "Aucune")
    project_dates = bridge.get("dates_projet", "Aucune")
    dossier_amount = bridge.get("montant_dossier", "Aucun")
    project_amount = bridge.get("montant_projet", "Non detecte")
    dossier_conditions = bridge.get("conditions_dossier", "Aucune")
    project_elements = bridge.get("elements_projet", "Aucun")
    client_identity = bridge.get("identite_client", "Aucune")

    condition_items = split_bridge_items(dossier_conditions)
    project_items = split_bridge_items(project_elements)
    client_items = split_bridge_items(client_identity)

    structure_status = "a confirmer"
    calendrier_status = "a confirmer"
    budget_status = "a confirmer"
    conditions_status = "a confirmer"
    capacite_status = "a confirmer"

    if required_structure == "A verifier":
        justifications.append("type de structure requis non explicite dans le dossier")
        details.append("Structure : critere dossier encore flou")
    elif required_structure == client_structure:
        score += 25
        justifications.append("forme juridique client compatible avec le dossier")
        details.append("Structure : compatibilite detectee entre dossier et client")
        structure_status = "ok"
    elif client_structure == "Non detectee":
        manques.append("forme juridique client non detectee")
        details.append("Structure : type client manquant")
        structure_status = "manquant"
    else:
        score -= 15
        justifications.append("forme juridique client differente de la structure requise")
        details.append("Structure : ecart entre structure requise et structure client")
        structure_status = "ecart"

    if dossier_date != "Aucune" and project_dates != "Aucune":
        score += 20
        justifications.append("dates presentes des deux cotes")
        details.append("Calendrier : dossier et projet contiennent des dates")
        calendrier_status = "ok"
    elif dossier_date != "Aucune" and project_dates == "Aucune":
        manques.append("dates projet absentes alors qu'une date dossier existe")
        details.append("Calendrier : date dossier detectee mais calendrier projet incomplet")
        calendrier_status = "manquant"
    else:
        manques.append("date limite dossier non detectee")
        details.append("Calendrier : date limite dossier absente")
        calendrier_status = "manquant"

    if dossier_amount != "Aucun" and project_amount != "Non detecte":
        score += 20
        justifications.append("montants detectes dans dossier et projet")
        details.append("Budget : montant dossier et montant projet disponibles")
        budget_status = "ok"
    elif project_amount != "Non detecte":
        manques.append("montant dossier absent")
        details.append("Budget : montant projet present mais plafond dossier absent")
        budget_status = "partiel"
    else:
        manques.append("montant projet absent")
        details.append("Budget : montant projet non renseigne")
        budget_status = "manquant"

    if dossier_conditions != "Aucune" and project_elements != "Aucun":
        score += 20
        justifications.append("conditions dossier et elements projet disponibles")
        conditions_status = "ok"
    elif dossier_conditions == "Aucune":
        manques.append("conditions dossier peu structurees")
        details.append("Conditions : attentes dossier peu structurees")
        conditions_status = "manquant"
    else:
        manques.append("elements projet peu detectes")
        details.append("Conditions : projet encore trop peu detaille")
        conditions_status = "manquant"

    if client_identity != "Aucune":
        score += 15
        justifications.append("identite ou activite client detectee")
        details.append("Capacite : client decrit par activites ou references")
        capacite_status = "ok"
    else:
        manques.append("activite client peu detectee")
        details.append("Capacite : identite ou experience client insuffisante")
        capacite_status = "manquant"

    pieces_keywords = ["piece", "pieces", "obligatoire", "rubrique", "formulaire"]
    if contains_any_keyword(condition_items, pieces_keywords):
        if project_items or client_items:
            score += 5
            justifications.append("pieces ou obligations dossier explicites et blocs repondants presents")
            details.append("Pieces : dossier explicite des obligations, reponse documentaire disponible")
        else:
            manques.append("pieces obligatoires explicites mais peu d'elements en face")
            details.append("Pieces : obligations detectees sans reponse claire cote client/projet")

    eligibility_keywords = ["eligible", "eligibilite", "association", "entreprise", "public"]
    if contains_any_keyword(condition_items, eligibility_keywords):
        if client_structure != "Non detectee" or client_items:
            score += 5
            justifications.append("conditions d'eligibilite partiellement comparables au profil client")
            details.append("Eligibilite : comparaison possible entre criteres dossier et profil client")
        else:
            manques.append("criteres d'eligibilite presents mais profil client encore trop faible")
            details.append("Eligibilite : dossier renseigne, client encore trop peu qualifie")

    budget_keywords = ["budget", "cofinancement", "financement", "cout", "depenses"]
    if contains_any_keyword(condition_items, budget_keywords) and contains_any_keyword(project_items, budget_keywords):
        score += 5
        justifications.append("coherence budgetaire amorcee entre exigences dossier et projet")
        details.append("Budget fin : mots-cles budgetaires retrouves des deux cotes")

    planning_keywords = ["planning", "calendrier", "date", "etape"]
    if contains_any_keyword(project_items, planning_keywords) and project_dates != "Aucune":
        score += 5
        justifications.append("elements de planning detectes dans le projet")
        details.append("Calendrier fin : le projet contient des jalons ou etapes")

    contexte_global = "non evalue"
    fiabilite_globale = "non evaluee"
    risque_global = "non evalue"
    actions_globales = "Aucune"

    if global_bridge is not None:
        etat_global = global_bridge.get("etat_global_documentaire", "inconnu")
        prescore_global = global_bridge.get("prescore_global_documentaire", "")
        incoherences_globales = global_bridge.get("incoherences_globales", "Aucune")
        actions_globales = global_bridge.get("actions_prealables", "Aucune")
        statut_blocs = global_bridge.get("statut_blocs", "Aucun")

        contexte_global = etat_global

        if "pret pour pre-analyse" in etat_global:
            score += 10
            fiabilite_globale = "bonne"
            details.append("Contexte global : socle documentaire globalement exploitable")
        elif "partiellement exploitable" in etat_global or "partiellement pret" in etat_global:
            score += 3
            fiabilite_globale = "moyenne"
            details.append("Contexte global : dossier exploitable mais encore incomplet")
        elif "structure complete mais informations faibles" in etat_global:
            score -= 8
            fiabilite_globale = "faible"
            manques.append("structure presente mais informations globales encore faibles")
            details.append("Contexte global : structure presente mais signaux documentaires fragiles")
        else:
            score -= 12
            fiabilite_globale = "faible"
            manques.append("contexte documentaire global insuffisant")
            details.append("Contexte global : dossier encore trop peu fiable pour un matching fort")

        if "bon" in prescore_global:
            score += 5
        elif "faible" in prescore_global:
            score -= 5

        if incoherences_globales != "Aucune incoherence simple detectee":
            score -= 10
            risque_global = "eleve"
            manques.append("incoherences globales detectees a traiter avant conclusion fiable")
            details.append(f"Risque global : {incoherences_globales}")
        elif "partiel" in statut_blocs or "vide" in statut_blocs:
            score -= 5
            risque_global = "moyen"
            details.append("Risque global : au moins un bloc reste partiel ou faible")
        else:
            risque_global = "modere"
            details.append("Risque global : pas d'incoherence simple majeure detectee")

    score = max(0, min(score, 100))

    if score >= 75:
        statut = "compatible"
    elif score >= 50:
        statut = "a confirmer"
    elif score >= 25:
        statut = "partiellement compatible"
    else:
        statut = "non compatible"

    return {
        "statut": statut,
        "score": f"{score}/100",
        "structure": structure_status,
        "calendrier": calendrier_status,
        "budget": budget_status,
        "conditions": conditions_status,
        "capacite": capacite_status,
        "contexte_global": contexte_global,
        "fiabilite_globale": fiabilite_globale,
        "risque_global": risque_global,
        "justifications_items": justifications,
        "manques_items": manques,
        "details_items": details,
        "actions_globales_items": [
            item.strip() for item in actions_globales.split(" | ")
            if item.strip() and item.strip() != "Aucune"
        ],
        "justifications": " | ".join(justifications) if justifications else "Aucune justification forte",
        "manques": " | ".join(manques) if manques else "Aucun manque majeur detecte",
        "details": " | ".join(details) if details else "Aucun detail fin disponible",
        "actions_globales": actions_globales,
    }


def render_wf3_section(
    dossier_files,
    client_files,
    project_files,
    bridge: dict[str, str] | None = None,
    global_bridge: dict[str, str] | None = None,
    pipeline_outputs: dict[str, object] | None = None,
) -> None:
    st.subheader("WF3 local - Matching dossier / client / projet")

    if not dossier_files or not client_files or not project_files:
        st.info("Le WF3 local demande des documents dans les 3 blocs : dossier, client et projet.")
        return

    wf2a_structured = pipeline_outputs.get("wf2a") if pipeline_outputs else extract_wf2a_structured(dossier_files)
    wf2b_structured = pipeline_outputs.get("wf2b") if pipeline_outputs else extract_wf2b_structured(client_files, project_files)

    if bridge is None:
        bridge = build_bridge_from_wf2(wf2a_structured, wf2b_structured)
    if global_bridge is None:
        fallback_block_files_map = {
            "Documents dossier": dossier_files,
            "Documents client": client_files,
            "Documents projet": project_files,
        }
        fallback_cross_summary = build_global_cross_block_summary(fallback_block_files_map)
        global_bridge = build_global_context_bridge(
            fallback_block_files_map,
            fallback_cross_summary,
            bridge,
        )
    if pipeline_outputs:
        wf3 = pipeline_outputs.get("wf3", {})
    else:
        completed_wf2a, completed_wf2b = merge_completed_bridge_into_wf2(
            wf2a_structured,
            wf2b_structured,
            bridge,
        )
        wf3 = build_wf3_analysis(
            completed_wf2a,
            completed_wf2b,
            global_context_bridge=global_bridge,
        )

    execution_meta = pipeline_outputs.get("execution", {}).get("wf3") if pipeline_outputs else None
    if execution_meta:
        st.caption(
            f"Moteur actif : {execution_meta.get('engine', 'heuristique_locale')}"
            + (" (fallback local)" if execution_meta.get("fallback_used") else "")
        )

    counts = wf3.get("counts", {})
    sous_scores = wf3.get("sous_scores", {})
    results = list(wf3.get("resultats_criteres", []))
    count_valide = counts.get("valide", 0)
    count_confirm = counts.get("a_confirmer", 0)
    count_missing = counts.get("manquant", 0)
    count_invalid = counts.get("non_valide", 0)
    prior_actions = []
    for result in results:
        if result.get("statut") in {"manquant", "non_valide", "a_confirmer"}:
            action = str(result.get("action_requise", "")).strip()
            if action and action not in prior_actions:
                prior_actions.append(action)

    col1, col2, col3 = st.columns(3)
    col1.metric("Statut", str(wf3.get("statut_eligibilite", "a confirmer")))
    col2.metric("Score global", f"{wf3.get('score_global', 0)}/100")
    col3.metric("Confiance", str(wf3.get("niveau_confiance", "moyen")))

    st.markdown("### Vue rapide")
    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
    quick_col1.metric("Criteres valides", str(count_valide))
    quick_col2.metric("A confirmer", str(count_confirm))
    quick_col3.metric("Manquants", str(count_missing))
    quick_col4.metric("Ecarts", str(count_invalid))

    st.markdown("### Sous-scores")
    score_col1, score_col2, score_col3, score_col4 = st.columns(4)
    score_col1.metric("Bloc client", f"{sous_scores.get('bloc_client', 0)}/100")
    score_col2.metric("Bloc projet", f"{sous_scores.get('bloc_projet', 0)}/100")
    score_col3.metric("Bloc mixte", f"{sous_scores.get('bloc_mixte', 0)}/100")
    score_col4.metric("Fiabilite doc", f"{sous_scores.get('fiabilite_documentaire', 0)}/100")

    st.markdown("### Contexte global integre")
    global_col1, global_col2, global_col3 = st.columns(3)
    global_col1.metric("Preparation", summarize_readiness_label(global_bridge.get("etat_global_documentaire", "inconnue")))
    global_col2.metric("Solidite", summarize_prescore_label(global_bridge.get("prescore_global_documentaire", "inconnue")))
    risk_value = "modere" if wf3.get("niveau_confiance") == "haut" else "moyen" if wf3.get("niveau_confiance") == "moyen" else "eleve"
    global_col3.metric("Risque", summarize_risk_label(risk_value))

    st.markdown("### Resume executif")
    st.write(str(wf3.get("resume_executif", "Aucun resume disponible.")))

    st.markdown("### Actions prioritaires")
    if prior_actions:
        for item in prior_actions[:8]:
            st.write(f"- {item}")
    else:
        st.write("- Aucune action prioritaire immediate")

    with st.expander("Voir le matching critere par critere", expanded=False):
        if not results:
            st.info("Aucun critere exploitable n'a ete produit par WF2a.")
        else:
            rows = []
            for result in results:
                rows.append(
                    {
                        "Critere": result.get("libelle", ""),
                        "Bloc": result.get("bloc_cible", ""),
                        "Statut": summarize_criterion_match_label(str(result.get("statut", ""))),
                        "Score": result.get("score", 0),
                        "Confiance": result.get("niveau_confiance", "moyen"),
                        "Source dossier": result.get("source_document", ""),
                        "Donnee utilisee": result.get("donnee_utilisee", ""),
                    }
                )
            st.dataframe(rows, use_container_width=True)

            for index, result in enumerate(results, start=1):
                st.markdown(
                    f"**{index}. {result.get('libelle', 'Critere')}**  \n"
                    f"Statut : `{summarize_criterion_match_label(str(result.get('statut', 'a_confirmer')))}`  \n"
                    f"Score : `{result.get('score', 0)}/100`  \n"
                    f"Bloc cible : `{result.get('bloc_cible', 'mixte')}`  \n"
                    f"Source dossier : `{result.get('source_document', 'inconnu')}`  \n"
                    f"Justification : {result.get('justification', 'Aucune')}  \n"
                    f"Action requise : {result.get('action_requise', 'Aucune')}  \n"
                    f"Donnee utilisee : {result.get('donnee_utilisee', 'Aucune')}  \n"
                    f"Ecart : {result.get('ecart', 'Aucun') or 'Aucun'}"
                )


def render_wf4_section(
    dossier_files,
    client_files,
    project_files,
    bridge: dict[str, str] | None = None,
    global_bridge: dict[str, str] | None = None,
    pipeline_outputs: dict[str, object] | None = None,
) -> None:
    st.subheader("WF4 local - Rapport, pre-remplissage et suggestions")

    if not dossier_files or not client_files or not project_files:
        st.info("Le WF4 local demande un dossier, un client et un projet pour generer des sorties utiles.")
        return

    if pipeline_outputs:
        wf4_outputs = pipeline_outputs.get("wf4", {})
    else:
        wf2a_structured = extract_wf2a_structured(dossier_files)
        wf2b_structured = extract_wf2b_structured(client_files, project_files)
        if bridge is None:
            bridge = build_bridge_from_wf2(wf2a_structured, wf2b_structured)
        if global_bridge is None:
            fallback_block_files_map = {
                "Documents dossier": dossier_files,
                "Documents client": client_files,
                "Documents projet": project_files,
            }
            fallback_cross_summary = build_global_cross_block_summary(fallback_block_files_map)
            global_bridge = build_global_context_bridge(
                fallback_block_files_map,
                fallback_cross_summary,
                bridge,
            )

        completed_wf2a, completed_wf2b = merge_completed_bridge_into_wf2(
            wf2a_structured,
            wf2b_structured,
            bridge,
        )
        wf3_analysis = build_wf3_analysis(
            completed_wf2a,
            completed_wf2b,
            global_context_bridge=global_bridge,
        )
        wf4_outputs = build_wf4_outputs(completed_wf2b, wf3_analysis)

    execution_meta = pipeline_outputs.get("execution", {}) if pipeline_outputs else {}
    if execution_meta:
        st.caption(
            "Moteurs actifs : "
            f"WF2a={execution_meta.get('wf2a', {}).get('engine', 'heuristique_locale')}, "
            f"WF2b={execution_meta.get('wf2b', {}).get('engine', 'heuristique_locale')}, "
            f"WF3={execution_meta.get('wf3', {}).get('engine', 'heuristique_locale')}"
        )

    rapport = wf4_outputs.get("rapport_structured", {})
    preremplissage = list(wf4_outputs.get("champs_preremplissage", []))
    suggestions = list(wf4_outputs.get("suggestions", []))
    report_markdown = str(wf4_outputs.get("rapport_markdown", ""))

    col1, col2, col3 = st.columns(3)
    col1.metric("Type rapport", str(rapport.get("type_rapport", "complet")))
    col2.metric("Format", str(rapport.get("format_export", "markdown")))
    col3.metric("Suggestions", str(len(suggestions)))

    st.markdown("### Rapport structure")
    render_metadata({
        "Statut": str(rapport.get("statut_eligibilite", "a confirmer")),
        "Score global": f"{rapport.get('score_global', 0)}/100",
        "Niveau de confiance": str(rapport.get("niveau_confiance", "moyen")),
        "Points valides": str(len(rapport.get("points_valides", []))),
        "Points a confirmer": str(len(rapport.get("points_a_confirmer", []))),
        "Points bloquants": str(len(rapport.get("points_bloquants", []))),
    })
    st.write(str(rapport.get("resume_executif", "Aucun resume.")))

    with st.expander("Voir le rapport markdown", expanded=False):
        st.text_area("Rapport markdown", report_markdown, height=320)
        st.download_button(
            "Telecharger le rapport markdown",
            data=report_markdown,
            file_name="rapport_wf4_local.md",
            mime="text/markdown",
            key="download_wf4_markdown",
        )

    st.markdown("### Champs de pre-remplissage")
    if preremplissage:
        st.dataframe(preremplissage, use_container_width=True)
    else:
        st.info("Aucun champ de pre-remplissage disponible.")

    st.markdown("### Suggestions alternatives")
    if suggestions:
        for index, suggestion in enumerate(suggestions, start=1):
            st.markdown(
                f"**{index}. {suggestion.get('nom', 'Suggestion')}**  \n"
                f"Pertinence : `{suggestion.get('score_pertinence', 0)}/100`  \n"
                f"Justification : {suggestion.get('justification', 'Aucune justification')}"
            )
    else:
        st.info("Aucune suggestion alternative locale n'a ete detectee pour l'instant.")


def collect_block_insights(uploaded_files) -> dict[str, str]:
    dates: dict[str, set[str]] = {}
    amounts: dict[str, set[str]] = {}
    organizations: dict[str, set[str]] = {}
    keywords: dict[str, set[str]] = {}
    provenances: list[str] = []

    for uploaded_file in uploaded_files:
        suffix = get_uploaded_suffix(uploaded_file)
        file_bytes = get_uploaded_bytes(uploaded_file)
        source_name = uploaded_file.name
        local_findings = []

        if suffix in {".txt", ".md"}:
            text_content = parse_text_bytes(file_bytes)
            metadata = extract_text_metadata(text_content, uploaded_file.name)
            detected_date = metadata.get("Date detectee", "")
            detected_amount = metadata.get("Montant detecte", "")
            detected_org = metadata.get("Organisme detecte", "")
            add_detected_value(dates, "date", detected_date, source_name)
            add_detected_value(amounts, "amount", detected_amount, source_name)
            add_detected_value(organizations, "org", detected_org, source_name)
            if detected_date not in {"", "Non detectee"}:
                local_findings.append(f"date {detected_date}")
            if detected_amount not in {"", "Non detecte"}:
                local_findings.append(f"montant {detected_amount}")
            if detected_org not in {"", "Non detecte"}:
                local_findings.append(f"organisme {detected_org}")
            for word in extract_keywords_from_text(text_content):
                add_detected_value(keywords, "keyword", word, source_name)

        elif suffix == ".docx":
            text_content, _, _ = parse_docx_bytes(file_bytes)
            metadata = extract_text_metadata(text_content, uploaded_file.name)
            detected_date = metadata.get("Date detectee", "")
            detected_amount = metadata.get("Montant detecte", "")
            detected_org = metadata.get("Organisme detecte", "")
            add_detected_value(dates, "date", detected_date, source_name)
            add_detected_value(amounts, "amount", detected_amount, source_name)
            add_detected_value(organizations, "org", detected_org, source_name)
            if detected_date not in {"", "Non detectee"}:
                local_findings.append(f"date {detected_date}")
            if detected_amount not in {"", "Non detecte"}:
                local_findings.append(f"montant {detected_amount}")
            if detected_org not in {"", "Non detecte"}:
                local_findings.append(f"organisme {detected_org}")
            for word in extract_keywords_from_text(text_content):
                add_detected_value(keywords, "keyword", word, source_name)

        elif suffix == ".pdf":
            pdf_text, _, _, pdf_error = parse_pdf_bytes(file_bytes)
            if pdf_error:
                provenances.append(f"{source_name} -> {pdf_error}")
                continue
            metadata = extract_text_metadata(pdf_text, uploaded_file.name)
            detected_date = metadata.get("Date detectee", "")
            detected_amount = metadata.get("Montant detecte", "")
            detected_org = metadata.get("Organisme detecte", "")
            add_detected_value(dates, "date", detected_date, source_name)
            add_detected_value(amounts, "amount", detected_amount, source_name)
            add_detected_value(organizations, "org", detected_org, source_name)
            if detected_date not in {"", "Non detectee"}:
                local_findings.append(f"date {detected_date}")
            if detected_amount not in {"", "Non detecte"}:
                local_findings.append(f"montant {detected_amount}")
            if detected_org not in {"", "Non detecte"}:
                local_findings.append(f"organisme {detected_org}")
            for word in extract_keywords_from_text(pdf_text):
                add_detected_value(keywords, "keyword", word, source_name)

        elif suffix == ".csv":
            dataframe = parse_csv_bytes(file_bytes)
            add_detected_value(keywords, "keyword", "tableau", source_name)
            for col in list(dataframe.columns)[:8]:
                add_detected_value(keywords, "keyword", str(col).lower(), source_name)
            local_findings.append(f"{len(dataframe.columns)} colonnes")
        elif suffix == ".xlsx":
            workbook = parse_excel_bytes(file_bytes)
            business_sheets, informative_sheets = filter_business_sheets(workbook)
            add_detected_value(keywords, "keyword", "tableau", source_name)
            for sheet_df in business_sheets.values():
                for col in list(sheet_df.columns)[:5]:
                    add_detected_value(keywords, "keyword", str(col).lower(), source_name)
            local_findings.append(f"{len(business_sheets)} feuille(s) metier")
            if informative_sheets:
                local_findings.append(f"{len(informative_sheets)} feuille(s) informatives")

        if local_findings:
            provenances.append(f"{source_name} -> " + ", ".join(local_findings[:4]))

    return {
        "Dates reperees": format_detected_values(dates),
        "Montants reperes": format_detected_values(amounts),
        "Organismes reperes": format_detected_values(organizations),
        "Mots-cles simples": format_detected_values(keywords),
        "Provenance synthese": " | ".join(provenances[:6]) if provenances else "Aucune",
    }


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


def summarize_readiness_label(value: str) -> str:
    normalized = value.lower()
    if "pret pour pre-analyse" in normalized:
        return "solide"
    if "partiellement exploitable" in normalized or "partiellement pret" in normalized:
        return "moyen"
    if "structure complete mais informations faibles" in normalized:
        return "fragile"
    if "insuffisant" in normalized:
        return "incomplet"
    return value


def summarize_prescore_label(value: str) -> str:
    normalized = value.lower()
    if "bon" in normalized:
        return "solide"
    if "moyen" in normalized:
        return "moyen"
    if "faible" in normalized:
        return "fragile"
    return value


def summarize_risk_label(value: str) -> str:
    normalized = value.lower()
    if "eleve" in normalized:
        return "eleve"
    if "moyen" in normalized:
        return "moyen"
    if "modere" in normalized:
        return "modere"
    if "non evalue" in normalized:
        return "a verifier"
    return value


def summarize_control_label(value: str) -> str:
    normalized = value.lower()
    if normalized == "ok":
        return "solide"
    if normalized == "partiel":
        return "partiel"
    if normalized == "manquant":
        return "manquant"
    if normalized == "ecart":
        return "ecart"
    if normalized == "a confirmer":
        return "a verifier"
    return value


def split_display_items(value: str) -> list[str]:
    if value in {"", "Aucun", "Aucune", "Aucune incoherence simple detectee"}:
        return []
    return [item.strip() for item in value.split(" | ") if item.strip()]


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


def render_cross_block_summary(summary: dict[str, str]) -> None:
    st.subheader("Synthese globale inter-blocs")

    col1, col2 = st.columns(2)
    col1.metric("Preparation", summarize_readiness_label(summary.get("Etat global", "inconnu")))
    col2.metric("Solidite", summarize_prescore_label(summary.get("Pre-score global", "inconnu")))

    st.markdown("### Lecture rapide")
    st.write(f"**Blocs disponibles** : {summary.get('Blocs disponibles', 'Aucun')}")
    st.write(f"**Blocs encore manquants** : {summary.get('Blocs manquants', 'Aucun')}")

    st.markdown("### Priorites retenues")
    st.write(f"- Date de reference : {summary.get('Date prioritaire', 'Aucune')}")
    st.write(f"- Organisme principal : {summary.get('Organisme prioritaire', 'Aucun')}")
    st.write(f"- Montant de reference : {summary.get('Montant prioritaire', 'Aucun')}")

    st.markdown("### Vigilances")
    control_items = split_display_items(summary.get("Controle simple", "Aucun"))
    issue_items = split_display_items(summary.get("Incoherences detectees", "Aucune"))
    if control_items:
        for item in control_items:
            st.write(f"- {item}")
    else:
        st.write("- aucun controle simple remonte")
    if issue_items:
        for item in issue_items:
            st.write(f"- {item}")
    else:
        st.write("- aucune incoherence simple detectee")

    st.markdown("### Actions par bloc")
    st.write(f"- Dossier : {summary.get('Action dossier', 'Aucune')}")
    st.write(f"- Client : {summary.get('Action client', 'Aucune')}")
    st.write(f"- Projet : {summary.get('Action projet', 'Aucune')}")

    with st.expander("Voir les details detectes par bloc", expanded=False):
        st.write(f"**Statut des blocs** : {summary.get('Statut des blocs', 'Aucun')}")
        st.write(f"**Criteres dossier** : {summary.get('Criteres dossier', 'Aucun')}")
        st.write(f"**Criteres client** : {summary.get('Criteres client', 'Aucun')}")
        st.write(f"**Criteres projet** : {summary.get('Criteres projet', 'Aucun')}")
        st.write(f"**Organismes par bloc** : {summary.get('Organismes par bloc', 'Aucun')}")
        st.write(f"**Dates par bloc** : {summary.get('Dates par bloc', 'Aucune')}")
        st.write(f"**Montants par bloc** : {summary.get('Montants par bloc', 'Aucun')}")


def build_global_context_bridge(
    block_files_map: dict[str, list],
    cross_summary: dict[str, str],
    local_bridge: dict[str, str],
) -> dict[str, str]:
    dossier_insights = collect_block_insights(block_files_map.get("Documents dossier", [])) if block_files_map.get("Documents dossier") else {}
    client_insights = collect_block_insights(block_files_map.get("Documents client", [])) if block_files_map.get("Documents client") else {}
    project_insights = collect_block_insights(block_files_map.get("Documents projet", [])) if block_files_map.get("Documents projet") else {}

    return {
        "etat_global_documentaire": cross_summary.get("Etat global", "inconnu"),
        "prescore_global_documentaire": cross_summary.get("Pre-score global", "inconnu"),
        "blocs_disponibles": cross_summary.get("Blocs disponibles", "Aucun"),
        "blocs_manquants": cross_summary.get("Blocs manquants", "Aucun"),
        "statut_blocs": cross_summary.get("Statut des blocs", "Aucun"),
        "incoherences_globales": cross_summary.get("Incoherences detectees", "Aucune"),
        "controle_global": cross_summary.get("Controle simple", "Aucun"),
        "actions_prealables": " | ".join(
            [
                cross_summary.get("Action dossier", "Aucune"),
                cross_summary.get("Action client", "Aucune"),
                cross_summary.get("Action projet", "Aucune"),
            ]
        ),
        "priorite_date": cross_summary.get("Date prioritaire", "Aucune"),
        "priorite_organisme": cross_summary.get("Organisme prioritaire", "Aucun"),
        "priorite_montant": cross_summary.get("Montant prioritaire", "Aucun"),
        "fiabilite_dossier": cross_summary.get("Criteres dossier", "Aucun"),
        "fiabilite_client": cross_summary.get("Criteres client", "Aucun"),
        "fiabilite_projet": cross_summary.get("Criteres projet", "Aucun"),
        "provenance_dossier": dossier_insights.get("Provenance synthese", "Aucune"),
        "provenance_client": client_insights.get("Provenance synthese", "Aucune"),
        "provenance_projet": project_insights.get("Provenance synthese", "Aucune"),
        "mots_cles_dossier": dossier_insights.get("Mots-cles simples", "Aucun"),
        "mots_cles_client": client_insights.get("Mots-cles simples", "Aucun"),
        "mots_cles_projet": project_insights.get("Mots-cles simples", "Aucun"),
        "resume_pont_metier": " | ".join(
            [
                f"Structure requise: {local_bridge.get('type_structure_requise', 'A verifier')}",
                f"Structure client: {local_bridge.get('type_structure_client', 'Non detectee')}",
                f"Date dossier: {local_bridge.get('date_limite_dossier', 'Aucune')}",
                f"Dates projet: {local_bridge.get('dates_projet', 'Aucune')}",
                f"Montant dossier: {local_bridge.get('montant_dossier', 'Aucun')}",
                f"Montant projet: {local_bridge.get('montant_projet', 'Non detecte')}",
            ]
        ),
    }


def render_global_context_bridge(global_bridge: dict[str, str]) -> None:
    st.subheader("Pont global - Contexte documentaire et fiabilite")

    col1, col2, col3 = st.columns(3)
    col1.metric("Preparation du dossier", summarize_readiness_label(global_bridge.get("etat_global_documentaire", "inconnue")))
    col2.metric("Solidite documentaire", summarize_prescore_label(global_bridge.get("prescore_global_documentaire", "inconnue")))
    col3.metric("Blocs exploites", global_bridge.get("blocs_disponibles", "Aucun"))

    st.markdown("### Lecture metier")
    st.write(f"**Etat de preparation** : {global_bridge.get('etat_global_documentaire', 'inconnu')}")
    st.write(f"**Points de vigilance avant analyse** : {global_bridge.get('incoherences_globales', 'Aucune')}")
    st.write(f"**Actions a traiter en priorite** : {global_bridge.get('actions_prealables', 'Aucune')}")

    st.markdown("### Qualite du socle documentaire")
    st.write(f"**Blocs encore manquants** : {global_bridge.get('blocs_manquants', 'Aucun')}")
    st.write(f"**Niveau des blocs** : {global_bridge.get('statut_blocs', 'Aucun')}")
    st.write(f"**Lecture transversale possible** : {global_bridge.get('controle_global', 'Aucun')}")

    st.markdown("### Signaux prioritaires retenus")
    st.write(f"**Date de reference la plus utile** : {global_bridge.get('priorite_date', 'Aucune')}")
    st.write(f"**Organisme le plus probable** : {global_bridge.get('priorite_organisme', 'Aucun')}")
    st.write(f"**Montant de reference** : {global_bridge.get('priorite_montant', 'Aucun')}")

    with st.expander("Voir la fiabilite par bloc", expanded=False):
        st.write(f"**Fiabilite du bloc dossier** : {global_bridge.get('fiabilite_dossier', 'Aucun')}")
        st.write(f"**Fiabilite du bloc client** : {global_bridge.get('fiabilite_client', 'Aucun')}")
        st.write(f"**Fiabilite du bloc projet** : {global_bridge.get('fiabilite_projet', 'Aucun')}")

    with st.expander("Voir la provenance et le contexte fin", expanded=False):
        st.write(f"**Provenance dossier** : {global_bridge.get('provenance_dossier', 'Aucune')}")
        st.write(f"**Provenance client** : {global_bridge.get('provenance_client', 'Aucune')}")
        st.write(f"**Provenance projet** : {global_bridge.get('provenance_projet', 'Aucune')}")
        st.write(f"**Mots-cles dossier** : {global_bridge.get('mots_cles_dossier', 'Aucun')}")
        st.write(f"**Mots-cles client** : {global_bridge.get('mots_cles_client', 'Aucun')}")
        st.write(f"**Mots-cles projet** : {global_bridge.get('mots_cles_projet', 'Aucun')}")
        st.write(f"**Resume pont metier** : {global_bridge.get('resume_pont_metier', 'Aucun')}")
        st.write(f"**Actions prealables** : {global_bridge.get('actions_prealables', 'Aucune')}")


def build_global_cross_block_summary(block_files_map: dict[str, list]) -> dict[str, str]:
    dossier_priority = ["Documents dossier", "Documents projet", "Documents client"]
    client_priority = ["Documents client", "Documents projet", "Documents dossier"]
    project_priority = ["Documents projet", "Documents dossier", "Documents client"]

    available_blocks = [name for name, files in block_files_map.items() if files]
    missing_blocks = [name for name, files in block_files_map.items() if not files]

    block_insights = {
        name: collect_block_insights(files) if files else {}
        for name, files in block_files_map.items()
    }
    block_criteria = {
        name: evaluate_block_criteria(name, files, block_insights.get(name, {})) if files else {
            "score": 0,
            "status": "insuffisant",
            "checks": "bloc vide",
        }
        for name, files in block_files_map.items()
    }
    block_recommendations = {
        name: build_block_recommendations(name, block_insights.get(name, {}), block_criteria.get(name, {}))
        if files else "charger au moins un document dans ce bloc"
        for name, files in block_files_map.items()
    }

    organizations = {}
    dates = {}
    amounts = {}
    block_statuses = {
        name: assess_block_completeness(files).get("Statut bloc", "vide")
        for name, files in block_files_map.items()
    }

    for block_name, insights in block_insights.items():
        if not insights:
            continue
        org_value = insights.get("Organismes reperes", "Aucun")
        date_value = insights.get("Dates reperees", "Aucune")
        amount_value = insights.get("Montants reperes", "Aucun")
        if org_value != "Aucun":
            organizations[block_name] = org_value
        if date_value != "Aucune":
            dates[block_name] = date_value
        if amount_value != "Aucun":
            amounts[block_name] = amount_value

    strong_blocks = [
        name for name, criteria in block_criteria.items()
        if criteria.get("status") in {"fort", "moyen"}
    ]

    if len(available_blocks) == 3 and len(strong_blocks) == 3:
        readiness = "pret pour pre-analyse"
    elif len(available_blocks) == 3 and len(strong_blocks) >= 2:
        readiness = "partiellement exploitable"
    elif len(available_blocks) == 3:
        readiness = "structure complete mais informations faibles"
    elif len(available_blocks) == 2:
        readiness = "partiellement pret"
    else:
        readiness = "insuffisant pour comparaison"

    checks = []
    issues = []
    if "Documents dossier" in organizations and "Documents projet" in organizations:
        checks.append("dossier/projet : organismes detectes disponibles")
    if "Documents client" in available_blocks and "Documents projet" in available_blocks:
        checks.append("client/projet : comparaison possible")
    if missing_blocks:
        checks.append("blocs manquants : " + ", ".join(missing_blocks))
        issues.append("au moins un bloc est manquant")

    weak_blocks = [name for name, status in block_statuses.items() if status != "suffisant"]
    if weak_blocks:
        issues.append("blocs a renforcer : " + ", ".join(weak_blocks))

    low_criteria_blocks = [
        name for name, criteria in block_criteria.items()
        if criteria.get("status") in {"faible", "insuffisant"}
    ]
    if low_criteria_blocks:
        issues.append("criteres insuffisamment identifies dans : " + ", ".join(low_criteria_blocks))

    if "Documents dossier" in dates and "Documents projet" not in dates:
        issues.append("date detectee dans le dossier mais absente du projet")
    if "Documents dossier" in organizations and "Documents client" not in organizations:
        issues.append("organisme detecte dans le dossier mais absent du bloc client")
    if "Documents projet" in amounts and "Documents dossier" not in amounts:
        issues.append("montant detecte dans le projet mais absent du dossier")

    if not organizations:
        issues.append("aucun organisme clairement detecte a l'echelle globale")
    if not dates:
        issues.append("aucune date clairement detectee a l'echelle globale")
    if not amounts:
        issues.append("aucun montant clairement detecte a l'echelle globale")

    if len(set(organizations.values())) > 1 and len(organizations) >= 2:
        issues.append("organismes detectes differents selon les blocs")
    if len(set(dates.values())) > 1 and len(dates) >= 2:
        issues.append("dates detectees non homogenes entre les blocs")
    if len(set(amounts.values())) > 1 and len(amounts) >= 2:
        issues.append("montants detectes non homogenes entre les blocs")

    if not issues:
        issues_text = "Aucune incoherence simple detectee"
    else:
        issues_text = " | ".join(issues[:8])

    prescore_label, prescore_value = compute_global_prescore(
        available_blocks=available_blocks,
        block_criteria_scores={name: int(criteria.get("score", 0)) for name, criteria in block_criteria.items()},
        issues=issues,
    )

    return {
        "Etat global": readiness,
        "Pre-score global": f"{prescore_label} ({prescore_value})",
        "Blocs disponibles": ", ".join(available_blocks) if available_blocks else "Aucun",
        "Blocs manquants": ", ".join(missing_blocks) if missing_blocks else "Aucun",
        "Statut des blocs": " | ".join(f"{k}: {v}" for k, v in block_statuses.items()),
        "Criteres dossier": f"{block_criteria['Documents dossier']['status']} ({block_criteria['Documents dossier']['score']}/30) - {block_criteria['Documents dossier']['checks']}",
        "Criteres client": f"{block_criteria['Documents client']['status']} ({block_criteria['Documents client']['score']}/30) - {block_criteria['Documents client']['checks']}",
        "Criteres projet": f"{block_criteria['Documents projet']['status']} ({block_criteria['Documents projet']['score']}/30) - {block_criteria['Documents projet']['checks']}",
        "Action dossier": block_recommendations["Documents dossier"],
        "Action client": block_recommendations["Documents client"],
        "Action projet": block_recommendations["Documents projet"],
        "Date prioritaire": choose_priority_value(dates, dossier_priority),
        "Organisme prioritaire": choose_priority_value(organizations, client_priority),
        "Montant prioritaire": choose_priority_value(amounts, project_priority),
        "Organismes par bloc": " | ".join(f"{k}: {v}" for k, v in organizations.items()) if organizations else "Aucun",
        "Dates par bloc": " | ".join(f"{k}: {v}" for k, v in dates.items()) if dates else "Aucune",
        "Montants par bloc": " | ".join(f"{k}: {v}" for k, v in amounts.items()) if amounts else "Aucun",
        "Controle simple": " | ".join(checks) if checks else "Aucun controle disponible",
        "Incoherences detectees": issues_text,
    }


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
            business_sheets, informative_sheets = filter_business_sheets(workbook)
            if informative_sheets:
                chunks.append("## FEUILLES INFORMATIVES")
                chunks.append(", ".join(informative_sheets))
            for sheet_name, sheet_df in business_sheets.items():
                chunks.append(dataframe_to_markdown(sheet_df, f"{uploaded_file.name} - {sheet_name}"))
        elif suffix == ".pdf":
            pdf_text, _, _, pdf_error = parse_pdf_bytes(file_bytes)
            if pdf_error:
                chunks.append(f"[{pdf_error}]")
            else:
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
        business_sheets, informative_sheets = filter_business_sheets(workbook)
        displayed_sheets = business_sheets if business_sheets else workbook

        st.markdown("### Feuilles detectees")
        st.write(", ".join(f"`{name}`" for name in sheet_names))
        if informative_sheets:
            st.info("Feuilles informatives detectees : " + ", ".join(f"`{name}`" for name in informative_sheets))

        first_sheet_name = next(iter(displayed_sheets.keys()))
        first_df = displayed_sheets[first_sheet_name]
        metadata = extract_table_metadata(first_df, uploaded_file.name)
        metadata["Nombre de feuilles"] = str(len(sheet_names))
        metadata["Feuilles metier"] = str(len(displayed_sheets))
        render_metadata(metadata)

        st.markdown("### Apercu Excel par feuille")
        for sheet_name, sheet_df in displayed_sheets.items():
            csv_content = sheet_df.to_csv(index=False)
            with st.expander(f"Feuille : {sheet_name}", expanded=False):
                st.dataframe(sheet_df, use_container_width=True)
                st.write(f"Lignes : `{len(sheet_df)}`")
                st.write(f"Colonnes : `{len(sheet_df.columns)}`")
                st.text_area(
                    f"CSV genere - {sheet_name}",
                    csv_content[:5000],
                    height=180,
                    key=f"csv_preview_{uploaded_file.name}_{sheet_name}",
                )
                st.download_button(
                    f"Telecharger {sheet_name} en CSV",
                    data=csv_content,
                    file_name=f"{Path(uploaded_file.name).stem}_{sheet_name}.csv",
                    mime="text/csv",
                    key=f"csv_download_{uploaded_file.name}_{sheet_name}",
                )
        normalized_text = workbook_to_markdown(workbook, uploaded_file.name)
        render_normalized_text(normalized_text, uploaded_file.name)
        return

    if suffix == ".pdf":
        pdf_text, page_count, text_page_count, pdf_error = parse_pdf_bytes(file_bytes)

        if pdf_error:
            st.error(f"Lecture PDF impossible : {pdf_error}")
            st.write("Ce fichier peut etre corrompu, mal exporte, ou non conforme au format PDF attendu.")
            st.write("Le bloc continue a fonctionner, mais ce document n'est pas exploitable pour l'instant.")
            return

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
    catalog = load_document_catalog()
    base_doc_count = len(catalog) if not catalog.empty else 0

    st.title("AAP Ingenia")
    st.caption("Back-office local de pre-analyse documentaire aligne sur les workflows Subly")

    col1, col2, col3 = st.columns(3)
    col1.metric("Statut", "WF1 a WF4 locaux")
    col2.metric("Mode", "Prototype metier")
    col3.metric("Base documentaire", f"{base_doc_count} docs")

    st.markdown(
        """
        Cette version sert maintenant a valider un vrai flux local :

        - ingestion dossier / client / projet ;
        - extraction structuree `WF2a` et `WF2b` ;
        - matching critere par critere `WF3` ;
        - sorties locales `WF4` : rapport, pre-remplissage et suggestions ;
        - preparation de la base documentaire et de Supabase.
        """
    )


def render_project() -> None:
    st.subheader("Ou en est le projet ?")
    st.markdown(
        """
        - Le cadrage produit et le schema cible sont deja poses dans `contexte/`
        - Les 4 sorties metier sont maintenant representees localement
        - La base documentaire locale est integree en catalogue
        - Le pont Supabase est prepare mais pas encore lance localement
        """
    )

    st.subheader("Cap actuel")
    st.write(
        "Stabiliser les cas reels, brancher Supabase, puis sortir progressivement la logique metier du gros fichier Streamlit."
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


def render_document_catalog_page() -> None:
    st.subheader("Base documentaire integree")
    st.write(
        "Cette vue recense les documents du dossier de base locale pour preparer l'ingestion, les cas de test et le futur seed Supabase."
    )

    catalog = load_document_catalog()
    if catalog.empty:
        st.warning("Aucun document de base n'a ete detecte.")
        return

    role_counts = catalog["role_workflow_recommande"].value_counts()
    family_counts = catalog["famille_documentaire"].value_counts()
    ext_counts = catalog["extension"].value_counts()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Documents", str(len(catalog)))
    col2.metric("Extensions", str(catalog["extension"].nunique()))
    col3.metric("Familles", str(catalog["famille_documentaire"].nunique()))
    col4.metric("Roles recommandes", str(catalog["role_workflow_recommande"].nunique()))

    st.markdown("### Lecture rapide")
    st.write("**Repartition par role recommande**")
    for role, count in role_counts.items():
        st.write(f"- {role} : {count}")
    st.write("**Top familles documentaires**")
    for family, count in family_counts.head(8).items():
        st.write(f"- {family} : {count}")

    with st.expander("Voir le detail du catalogue", expanded=False):
        st.dataframe(catalog, use_container_width=True)
        st.write("**Top extensions**")
        for extension, count in ext_counts.items():
            st.write(f"- {extension} : {count}")

    smoke_case = build_smoke_test_case()
    with st.expander("Jeu de test documentaire retenu", expanded=False):
        st.write("**Dossier**")
        for item in smoke_case["dossier"]:
            st.write(f"- {item.name}")
        st.write("**Client**")
        for item in smoke_case["client"]:
            st.write(f"- {item.name}")
        st.write("**Projet**")
        for item in smoke_case["projet"]:
            st.write(f"- {item.name}")

    smoke_results = load_smoke_test_results()
    if smoke_results:
        wf3 = smoke_results.get("wf3", {})
        st.markdown("### Resultat du smoke-test reel")
        render_metadata({
            "Statut": wf3.get("statut_eligibilite", "inconnu"),
            "Score": f"{wf3.get('score_global', 0)}/100",
            "Confiance": wf3.get("niveau_confiance", "inconnue"),
            "Resume": wf3.get("resume_executif", "Aucun"),
        })


def render_supabase_page() -> None:
    st.subheader("Connexion Supabase")

    readiness = describe_supabase_readiness()
    is_configured = readiness.get("SUPABASE_URL") == "configuree" and readiness.get("SUPABASE_ANON_KEY") == "configuree"

    if is_configured:
        st.success("Supabase Cloud connecte — toutes les cles sont configurees.")
    else:
        st.warning("Cles Supabase non configurees. Ajoutez-les dans les secrets Streamlit ou dans le fichier `.env`.")

    render_metadata(readiness)

    st.markdown("### Infrastructure")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Mode deploiement**")
        st.write("Supabase Cloud (hosted) — pas besoin de Docker ni de CLI local")
        st.write("")
        st.write("**Schema BDD**")
        st.write("`supabase/migrations/` — pret a appliquer via le dashboard Supabase")
    with col2:
        st.write("**Storage**")
        st.write("Bucket `subly-documents` — prive, cree automatiquement au premier appel")
        st.write("")
        st.write("**Seed**")
        st.write("`supabase/seed.sql` — donnees de demonstration disponibles")

    if is_configured:
        st.markdown("### Test de connexion")
        if st.button("Tester la connexion Supabase", key="btn_test_supabase"):
            from app.services.supabase_bridge import create_supabase_client
            client = create_supabase_client()
            if client is None:
                st.error("Impossible de creer le client Supabase.")
            else:
                try:
                    resp = client.table("clients").select("id").limit(1).execute()
                    st.success(f"Connexion BDD OK — table `clients` accessible ({len(resp.data)} ligne(s))")
                except Exception as exc:
                    st.error(f"Connexion echouee : {exc}")


def render_llm_page() -> None:
    st.subheader("Connexion Claude API")

    llm_info = describe_llm_readiness()
    is_configured = llm_info.get("ANTHROPIC_API_KEY") == "configuree"

    if is_configured:
        st.success("Claude API configuree et operationnelle.")
    else:
        st.warning("Cle Anthropic non configuree. Ajoutez `ANTHROPIC_API_KEY` dans les secrets Streamlit ou dans le fichier `.env`.")

    render_metadata(llm_info)

    st.markdown("### Strategie d'integration")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Point d'entree**")
        st.write("`app/services/llm_client.py` — appels directs Python")
        st.write("")
        st.write("**Modele**")
        st.write(f"`{llm_info.get('Modele', 'claude-sonnet-4-20250514')}`")
    with col2:
        st.write("**Fallback**")
        st.write("Heuristiques locales actives si la cle est absente — l'app ne plante jamais")
        st.write("")
        st.write("**Usage prevu**")
        st.write("WF2a (criteres), WF2b (profil client), WF3 (scoring), WF4 (rapport)")

    if is_configured:
        st.markdown("### Test de connexion")
        if st.button("Tester l'appel Claude API", key="btn_test_llm"):
            from app.services.llm_client import call_anthropic_message
            with st.spinner("Appel en cours..."):
                result = call_anthropic_message(
                    "Tu es un assistant de test. Reponds en une seule phrase courte.",
                    "Dis juste OK pour confirmer que tu fonctionnes."
                )
            if result.get("ok"):
                usage = result.get("usage", {})
                st.success(f"Claude repond : *{result.get('text', '')}*")
                st.caption(f"Modele : {result.get('model')} — {usage.get('input_tokens')} tokens entree / {usage.get('output_tokens')} tokens sortie")
            else:
                st.error(f"Echec : {result.get('error')}")

    st.markdown("### Test de preparation WF2a")
    smoke_case = build_smoke_test_case()
    dossier_files = smoke_case["dossier"]

    if not dossier_files:
        st.info("Aucun document dossier de smoke-test n'est disponible.")
        return

    st.write("Documents dossier du test :")
    for item in dossier_files:
        st.write(f"- {item.name}")

    if st.button("Tester la preparation WF2a LLM", key="wf2a_llm_prepare"):
        result = request_wf2a_llm_payload(dossier_files)
        if not result.get("ok"):
            st.warning(f"WF2a LLM non execute : {result.get('error', 'erreur inconnue')}")
        else:
            payload = result.get("payload", {})
            metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
            criteres = payload.get("criteres", []) if isinstance(payload, dict) else []
            render_metadata({
                "Mode": str(result.get("mode", "llm_direct_python")),
                "Modele": str(result.get("model", "")),
                "Input tokens": str(result.get("usage", {}).get("input_tokens", "inconnu")),
                "Output tokens": str(result.get("usage", {}).get("output_tokens", "inconnu")),
                "Criteres retournes": str(len(criteres)),
            })
            if metadata:
                st.write("**Metadata retournee**")
                render_metadata({
                    "Type dossier": str(metadata.get("type_dossier_detecte", "inconnu")),
                    "Financeur": str(metadata.get("financeur_detecte", "inconnu")),
                    "Montant max": str(metadata.get("montant_max_detecte", "inconnu")),
                    "Date limite": str(metadata.get("date_limite_detectee", "inconnue")),
                })
            if criteres:
                with st.expander("Voir le payload JSON brut", expanded=False):
                    st.json(payload)


def render_upload_block(title: str, help_text: str, uploader_key: str):
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

    for index, uploaded_file in enumerate(uploaded_files, start=1):
        process_uploaded_file(uploaded_file, title, index)
        if index < len(uploaded_files):
            st.divider()

    st.divider()
    render_block_summary(title, uploaded_files)
    block_normalized_text = build_block_normalized_text(title, uploaded_files)
    render_normalized_text(block_normalized_text, title.replace(" ", "_").lower())

    return uploaded_files


def render_upload() -> None:
    st.subheader("Upload structure en 3 blocs")
    st.write(
        "Le flux metier repose sur trois types de documents distincts : dossier, client et projet."
    )

    summary_map = {}
    block_files_map = {}

    block_files_map["Documents dossier"] = render_upload_block(
        "Documents dossier",
        "Documents cibles a analyser : appel a projets, reglement, cahier des charges, cadre d'intervention.",
        "upload_dossier",
    )
    summary_map["Documents dossier"] = [
        build_upload_summary(uploaded_file) for uploaded_file in block_files_map["Documents dossier"]
    ]
    st.divider()
    block_files_map["Documents client"] = render_upload_block(
        "Documents client",
        "Documents qui decrivent la structure porteuse : presentation, statuts, references, plaquette.",
        "upload_client",
    )
    summary_map["Documents client"] = [
        build_upload_summary(uploaded_file) for uploaded_file in block_files_map["Documents client"]
    ]
    st.divider()
    block_files_map["Documents projet"] = render_upload_block(
        "Documents projet",
        "Documents qui decrivent l'action ou la demande : note d'intention, budget, description du projet.",
        "upload_projet",
    )
    summary_map["Documents projet"] = [
        build_upload_summary(uploaded_file) for uploaded_file in block_files_map["Documents projet"]
    ]
    st.divider()
    render_global_summary(summary_map)

    cross_summary = build_global_cross_block_summary(block_files_map)
    bridge = build_comparable_bridge(
        block_files_map["Documents dossier"],
        block_files_map["Documents client"],
        block_files_map["Documents projet"],
    )
    global_context_bridge = build_global_context_bridge(
        block_files_map,
        cross_summary,
        bridge,
    )
    files_signature = build_files_signature(block_files_map)
    active_pipeline_outputs = get_active_pipeline_outputs(files_signature)

    st.divider()
    diagnostic_tab, extraction_tab, bridge_tab, wf4_tab = st.tabs(
        ["Diagnostic prioritaire", "Extractions detaillees", "Ponts et completions", "WF4 sorties"]
    )

    with bridge_tab:
        with st.expander("Pont metier WF2a / WF2b", expanded=True):
            completed_bridge = render_bridge_section(
                bridge,
                block_files_map["Documents dossier"],
                block_files_map["Documents client"],
                block_files_map["Documents projet"],
            )
        with st.expander("Pont global - Contexte documentaire", expanded=False):
            render_global_context_bridge(global_context_bridge)

    st.divider()
    st.markdown("### Execution pilotee")
    llm_ready = describe_llm_readiness()
    supabase_ready = describe_supabase_readiness()
    use_llm_default = llm_ready.get("ANTHROPIC_API_KEY") == "configuree"
    persist_default = (
        supabase_ready.get("SUPABASE_URL") == "configuree"
        and supabase_ready.get("SUPABASE_SERVICE_ROLE_KEY") == "configuree"
    )
    col_exec_1, col_exec_2 = st.columns(2)
    prefer_llm = col_exec_1.checkbox(
        "Preferer Claude API pour WF2/WF3",
        value=use_llm_default,
        help="Utilise Claude si la cle API est configuree, sinon repasse automatiquement sur l'heuristique locale.",
    )
    persist_supabase = col_exec_2.checkbox(
        "Persister les resultats dans Supabase",
        value=persist_default,
        help="Enregistre client, dossier, documents, criteres, analyse, resultats et rapport dans Supabase.",
    )

    # ── Sélecteur de client ────────────────────────────────────────────────
    selected_client_id: str | None = None
    if persist_supabase:
        st.markdown("#### Client a associer a ce dossier")
        existing_clients = list_clients()
        client_options = {c.label(): c.id for c in existing_clients}

        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            mode = st.radio(
                "Mode",
                ["Selectionner un client existant", "Creer un nouveau client"],
                horizontal=True,
                key="client_select_mode",
                label_visibility="collapsed",
            )

        if mode == "Selectionner un client existant":
            if client_options:
                chosen_label = st.selectbox(
                    "Client",
                    options=list(client_options.keys()),
                    key="client_selector",
                )
                selected_client_id = client_options[chosen_label]
                st.caption(f"ID : `{selected_client_id}`")
            else:
                st.info("Aucun client dans Supabase. Creez-en un ci-dessous.")
        else:
            with st.form("form_new_client", border=True):
                new_nom = st.text_input("Nom de la structure *", key="new_client_nom")
                col_f1, col_f2 = st.columns(2)
                new_forme = col_f1.text_input("Forme juridique", key="new_client_forme")
                new_secteur = col_f2.text_input("Secteur d'activite", key="new_client_secteur")
                col_f3, col_f4 = st.columns(2)
                new_email = col_f3.text_input("Email de contact", key="new_client_email")
                new_tel = col_f4.text_input("Telephone", key="new_client_tel")
                new_siret = st.text_input("SIRET (optionnel)", key="new_client_siret")
                submitted = st.form_submit_button("Creer ce client", type="primary")
                if submitted:
                    if not new_nom.strip():
                        st.error("Le nom de la structure est obligatoire.")
                    else:
                        created = create_client(
                            nom=new_nom,
                            forme_juridique=new_forme or None,
                            secteur_activite=new_secteur or None,
                            contact_email=new_email or None,
                            contact_telephone=new_tel or None,
                            siret=new_siret or None,
                        )
                        if created:
                            st.success(f"Client cree : **{created.nom}** (`{created.id}`).")
                            selected_client_id = created.id
                            st.rerun()
                        else:
                            st.error("Erreur lors de la creation du client dans Supabase.")

    if st.button("Executer le pipeline", key="execute_pipeline_button", type="primary"):
        pipeline_outputs = resolve_pipeline_outputs(
            block_files_map["Documents dossier"],
            block_files_map["Documents client"],
            block_files_map["Documents projet"],
            completed_bridge=completed_bridge,
            global_context_bridge=global_context_bridge,
            prefer_llm=prefer_llm,
        )
        persistence_result = None
        if persist_supabase:
            persistence_result = persist_pipeline_outputs(
                block_files_map["Documents dossier"],
                block_files_map["Documents client"],
                block_files_map["Documents projet"],
                pipeline_outputs,
                selected_client_id=selected_client_id,
            )
        store_pipeline_outputs(files_signature, pipeline_outputs, persistence_result)
        active_pipeline_outputs = pipeline_outputs

    if active_pipeline_outputs:
        execution_meta = active_pipeline_outputs.get("execution", {})
        st.success("Derniere execution disponible pour les fichiers actuellement charges.")
        render_metadata(
            {
                "WF2a": execution_meta.get("wf2a", {}).get("engine", "heuristique_locale"),
                "WF2b": execution_meta.get("wf2b", {}).get("engine", "heuristique_locale"),
                "WF3": execution_meta.get("wf3", {}).get("engine", "heuristique_locale"),
                "Fallback": "oui"
                if any(
                    step.get("fallback_used")
                    for step in execution_meta.values()
                    if isinstance(step, dict)
                )
                else "non",
            }
        )
        persistence_result = st.session_state.get("pipeline_persistence", {})
        if persistence_result:
            if persistence_result.get("ok"):
                st.caption(
                    f"Supabase : analyse {persistence_result.get('analyse_id')} enregistree, "
                    f"{persistence_result.get('documents_count', 0)} document(s), "
                    f"{persistence_result.get('criteres_count', 0)} critere(s)."
                )
            else:
                st.warning(f"Persistance Supabase non finalisee : {persistence_result.get('error', 'erreur inconnue')}")
    else:
        st.info("Aucune execution pilotee en memoire pour les fichiers actuels. Les vues ci-dessous utilisent les sorties locales par defaut.")

    with diagnostic_tab:
        st.markdown("### Lecture prioritaire")
        render_cross_block_summary(cross_summary)
        st.divider()
        render_wf3_section(
            block_files_map["Documents dossier"],
            block_files_map["Documents client"],
            block_files_map["Documents projet"],
            bridge=completed_bridge,
            global_bridge=global_context_bridge,
            pipeline_outputs=active_pipeline_outputs,
        )

    with extraction_tab:
        with st.expander("WF2a local - Criteres dossier", expanded=True):
            render_wf2a_dossier_section(
                block_files_map["Documents dossier"],
                wf2a_structured=active_pipeline_outputs.get("wf2a") if active_pipeline_outputs else None,
                execution_meta=active_pipeline_outputs.get("execution", {}).get("wf2a") if active_pipeline_outputs else None,
            )
        with st.expander("WF2b local - Profil client et donnees projet", expanded=True):
            render_wf2b_section(
                block_files_map["Documents client"],
                block_files_map["Documents projet"],
                wf2b_structured=active_pipeline_outputs.get("wf2b") if active_pipeline_outputs else None,
                execution_meta=active_pipeline_outputs.get("execution", {}).get("wf2b") if active_pipeline_outputs else None,
            )

    with wf4_tab:
        render_wf4_section(
            block_files_map["Documents dossier"],
            block_files_map["Documents client"],
            block_files_map["Documents projet"],
            bridge=completed_bridge,
            global_bridge=global_context_bridge,
            pipeline_outputs=active_pipeline_outputs,
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
