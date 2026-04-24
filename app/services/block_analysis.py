from __future__ import annotations

import json
import re

from app.services.metadata import (
    add_detected_value,
    extract_keywords_from_text,
    extract_text_metadata,
    format_detected_values,
)
from app.services.normalizers import dataframe_to_markdown, filter_business_sheets
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


# ── Helpers: Labels ──────────────────────────────────────────────────────────

def summarize_criterion_match_label(value: str) -> str:
    mapping = {
        "valide": "solide",
        "a_confirmer": "a confirmer",
        "manquant": "manquant",
        "non_valide": "ecart",
    }
    return mapping.get(value, value or "a verifier")


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


# ── Bridge helpers ────────────────────────────────────────────────────────────

def split_bridge_items(value: str) -> list[str]:
    if value in {"", "Aucun", "Aucune", "Non detecte", "Non detectee", "A verifier"}:
        return []
    parts = re.split(r"\s*\|\s*|,\s*", value)
    return [part.strip() for part in parts if part.strip()]


def contains_any_keyword(items: list[str], keywords: list[str]) -> bool:
    normalized_items = " ".join(items).lower()
    return any(keyword in normalized_items for keyword in keywords)


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


def choose_priority_value(block_candidates: dict[str, str], priority_order: list[str]) -> str:
    for block_name in priority_order:
        value = block_candidates.get(block_name)
        if value and value not in {"Aucun", "Aucune"}:
            return f"{value} ({block_name})"
    return "Aucun"


# ── Document context helpers ──────────────────────────────────────────────────

def format_loaded_documents_label(uploaded_files) -> str:
    if not uploaded_files:
        return "aucun document charge"
    names = [uploaded_file.name for uploaded_file in uploaded_files]
    if len(names) <= 2:
        return ", ".join(names)
    return ", ".join(names[:2]) + f" (+{len(names) - 2} autre(s))"


def infer_block_document_context(uploaded_files) -> set[str]:
    context_tags: set[str] = set()
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


# ── Document parsing ──────────────────────────────────────────────────────────

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


def build_upload_summary(uploaded_file) -> dict[str, str]:
    suffix = get_uploaded_suffix(uploaded_file)
    return {
        "Nom": uploaded_file.name,
        "Type": suffix,
        "Taille": f"{uploaded_file.size} octets",
        "Statut": "Charge",
    }


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


# ── Block evaluation ──────────────────────────────────────────────────────────

def assess_block_completeness(uploaded_files) -> dict[str, str]:
    if not uploaded_files:
        return {
            "Statut bloc": "vide",
            "Niveau": "0/3",
            "Commentaire": "Aucun document n'a ete charge dans ce bloc.",
        }

    suffixes = {get_uploaded_suffix(uploaded_file) for uploaded_file in uploaded_files}
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


# ── WF2 extraction wrappers ───────────────────────────────────────────────────

def extract_wf2a_dossier_criteria(uploaded_files) -> list[dict[str, str]]:
    return extract_wf2a_structured(uploaded_files).get("criteres", [])


def extract_wf2b_client_profile(client_files) -> dict[str, str]:
    wf2b = extract_wf2b_structured(client_files, [])
    return summarize_wf2b_client_profile(wf2b)


def extract_wf2b_project_data(project_files) -> dict[str, str]:
    wf2b = extract_wf2b_structured([], project_files)
    return summarize_wf2b_project_data(wf2b)


def build_comparable_bridge(dossier_files, client_files, project_files) -> dict[str, str]:
    wf2a = extract_wf2a_structured(dossier_files) if dossier_files else {"criteres": [], "metadata": {}}
    wf2b = (
        extract_wf2b_structured(client_files, project_files)
        if (client_files or project_files)
        else {"profil_client": {}, "donnees_projet": {}}
    )
    return build_bridge_from_wf2(wf2a, wf2b)


# ── Global context bridge ─────────────────────────────────────────────────────

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
        "actions_prealables": " | ".join([
            cross_summary.get("Action dossier", "Aucune"),
            cross_summary.get("Action client", "Aucune"),
            cross_summary.get("Action projet", "Aucune"),
        ]),
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
        "resume_pont_metier": " | ".join([
            f"Structure requise: {local_bridge.get('type_structure_requise', 'A verifier')}",
            f"Structure client: {local_bridge.get('type_structure_client', 'Non detectee')}",
            f"Date dossier: {local_bridge.get('date_limite_dossier', 'Aucune')}",
            f"Dates projet: {local_bridge.get('dates_projet', 'Aucune')}",
            f"Montant dossier: {local_bridge.get('montant_dossier', 'Aucun')}",
            f"Montant projet: {local_bridge.get('montant_projet', 'Non detecte')}",
        ]),
    }


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

    organizations: dict[str, str] = {}
    dates: dict[str, str] = {}
    amounts: dict[str, str] = {}
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

    checks: list[str] = []
    issues: list[str] = []
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

    issues_text = "Aucune incoherence simple detectee" if not issues else " | ".join(issues[:8])

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


# ── Legacy local WF3 (kept for reference) ────────────────────────────────────

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
