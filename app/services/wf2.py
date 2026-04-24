from __future__ import annotations

import re
from pathlib import Path

from app.services.metadata import extract_text_metadata
from app.services.normalizers import filter_business_sheets, workbook_to_markdown
from app.services.parsers import (
    get_uploaded_bytes,
    get_uploaded_suffix,
    parse_csv_bytes,
    parse_docx_bytes,
    parse_excel_bytes,
    parse_pdf_bytes,
    parse_text_bytes,
)


VALID_CATEGORIES = {"obligatoire", "souhaitable", "bloquant", "interpretatif"}
VALID_DOMAINS = {
    "administratif",
    "technique",
    "financier",
    "juridique",
    "pedagogique",
    "territorial",
    "sectoriel",
}
VALID_CONFIDENCE = {"haut", "moyen", "bas"}


def normalize_category(value: str) -> str:
    if value in VALID_CATEGORIES:
        return value
    return "interpretatif"


def normalize_domain(value: str) -> str:
    if value in VALID_DOMAINS:
        return value
    return "administratif"


def normalize_confidence(value: str) -> str:
    if value in VALID_CONFIDENCE:
        return value
    return "moyen"


def extract_document_payloads(uploaded_files) -> list[dict[str, str]]:
    payloads = []

    for uploaded_file in uploaded_files:
        suffix = get_uploaded_suffix(uploaded_file)
        file_bytes = get_uploaded_bytes(uploaded_file)
        text = ""

        if suffix in {".txt", ".md"}:
            text = parse_text_bytes(file_bytes)
        elif suffix == ".docx":
            text, _, _ = parse_docx_bytes(file_bytes)
        elif suffix == ".pdf":
            text, _, _, _ = parse_pdf_bytes(file_bytes)
        elif suffix == ".csv":
            dataframe = parse_csv_bytes(file_bytes)
            text = dataframe.to_csv(index=False)
        elif suffix == ".xlsx":
            workbook = parse_excel_bytes(file_bytes)
            business_sheets, informative_sheets = filter_business_sheets(workbook)
            workbook_for_text = business_sheets if business_sheets else workbook
            text = workbook_to_markdown(workbook_for_text, uploaded_file.name)
            if informative_sheets:
                text += "\n\nFeuilles informatives: " + ", ".join(informative_sheets)

        payloads.append(
            {
                "document_name": uploaded_file.name,
                "suffix": suffix,
                "text": text,
            }
        )

    return payloads


def find_source_excerpt(text: str, needle: str, max_length: int = 220) -> str:
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""

    needle_lower = needle.lower()
    compact_lower = compact.lower()
    index = compact_lower.find(needle_lower)

    if index == -1:
        return compact[:max_length]

    start = max(0, index - 80)
    end = min(len(compact), index + len(needle) + 140)
    snippet = compact[start:end].strip()
    return snippet[:max_length]


def detect_dossier_type(text: str) -> str:
    if "marche public" in text:
        return "marche_public"
    if "subvention" in text:
        return "subvention"
    if "ami" in text:
        return "ami"
    if "appel" in text or "aap" in text:
        return "aap"
    return "autre"


def build_structured_criterion(
    criterion_id: int,
    categorie: str,
    domaine: str,
    libelle: str,
    detail: str,
    source_document: str,
    source_extrait: str,
    est_piece_exigee: bool = False,
    est_critere_eliminatoire: bool = False,
    niveau_confiance: str = "moyen",
    necessite_validation: bool = False,
) -> dict[str, str | bool]:
    normalized_category = normalize_category(categorie)
    normalized_confidence = normalize_confidence(niveau_confiance)

    if normalized_category == "interpretatif":
        necessite_validation = True
    if normalized_confidence == "bas":
        necessite_validation = True

    return {
        "id_local": f"critere_{criterion_id}",
        "categorie": normalized_category,
        "domaine": normalize_domain(domaine),
        "libelle": libelle,
        "detail": detail,
        "source_document": source_document,
        "source_texte": source_extrait or "",
        "source_document_id": None,
        "est_piece_exigee": est_piece_exigee,
        "est_critere_eliminatoire": est_critere_eliminatoire,
        "niveau_confiance": normalized_confidence,
        "necessite_validation": necessite_validation,
        "mode_extraction": "heuristique_preparee_pour_llm",
    }


def extract_wf2a_structured(dossier_files) -> dict[str, object]:
    payloads = extract_document_payloads(dossier_files)
    criteres: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    criterion_id = 1

    amount_pattern = re.compile(r"\b\d[\d\s.,]{2,}\s?(?:€|euros?)\b", flags=re.IGNORECASE)
    date_pattern = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")

    keyword_rules = [
        ("eligibilite", "obligatoire", "administratif", "Condition d'eligibilite detectee", False, False, "moyen"),
        ("candidature", "obligatoire", "administratif", "Element de candidature detecte", False, False, "moyen"),
        ("budget", "souhaitable", "financier", "Element budgetaire detecte", False, False, "moyen"),
        ("planning", "souhaitable", "technique", "Element de planning detecte", False, False, "moyen"),
        ("calendrier", "souhaitable", "technique", "Element de calendrier detecte", False, False, "moyen"),
        ("piece", "obligatoire", "administratif", "Piece demandee detectee", True, False, "moyen"),
        ("obligatoire", "bloquant", "administratif", "Mention explicite d'obligation detectee", False, True, "haut"),
    ]

    for payload in payloads:
        text = payload["text"]
        document_name = payload["document_name"]
        if not text:
            continue

        date_matches = date_pattern.findall(text)
        amount_matches = amount_pattern.findall(text)

        if date_matches:
            detail = date_matches[0]
            unique_key = ("Date de reference detectee", detail, document_name)
            if unique_key not in seen:
                seen.add(unique_key)
                criteres.append(
                    build_structured_criterion(
                        criterion_id,
                        "obligatoire",
                        "administratif",
                        "Date de reference detectee",
                        detail,
                        document_name,
                        find_source_excerpt(text, detail),
                        niveau_confiance="haut",
                    )
                )
                criterion_id += 1

        if amount_matches:
            detail = amount_matches[0]
            unique_key = ("Montant detecte dans le dossier", detail, document_name)
            if unique_key not in seen:
                seen.add(unique_key)
                criteres.append(
                    build_structured_criterion(
                        criterion_id,
                        "souhaitable",
                        "financier",
                        "Montant detecte dans le dossier",
                        detail,
                        document_name,
                        find_source_excerpt(text, detail),
                        niveau_confiance="haut",
                    )
                )
                criterion_id += 1

        text_lower = text.lower()
        for keyword, categorie, domaine, libelle, is_piece, is_eliminatory, confidence in keyword_rules:
            if keyword in text_lower:
                detail = f"Mot-cle repere : {keyword}"
                unique_key = (libelle, detail, document_name)
                if unique_key in seen:
                    continue
                seen.add(unique_key)
                criteres.append(
                    build_structured_criterion(
                        criterion_id,
                        categorie,
                        domaine,
                        libelle,
                        detail,
                        document_name,
                        find_source_excerpt(text, keyword),
                        est_piece_exigee=is_piece,
                        est_critere_eliminatoire=is_eliminatory,
                        niveau_confiance=confidence,
                    )
                )
                criterion_id += 1

    combined_text = "\n\n".join(payload["text"] for payload in payloads if payload["text"])
    metadata = extract_text_metadata(combined_text, "dossier_concatene.txt") if combined_text else {}

    return {
        "criteres": criteres[:30],
        "metadata": {
            "type_dossier_detecte": detect_dossier_type(combined_text.lower()) if combined_text else "autre",
            "financeur_detecte": metadata.get("Organisme detecte", "Non detecte"),
            "montant_max_detecte": metadata.get("Montant detecte", "Non detecte"),
            "date_limite_detectee": metadata.get("Date detectee", "Non detectee"),
            "nb_criteres_extraits": len(criteres[:30]),
            "mode_extraction": "heuristique_preparee_pour_llm",
            "documents_sources": [payload["document_name"] for payload in payloads],
        },
        "llm_contract": {
            "categories_valides": sorted(VALID_CATEGORIES),
            "domaines_valides": sorted(VALID_DOMAINS),
            "niveaux_confiance_valides": sorted(VALID_CONFIDENCE),
            "sortie_cible": "criteres + metadata",
        },
    }


def build_field_value(
    field_name: str,
    value: str,
    source_document: str,
    source_text: str,
    confidence: str = "moyen",
    validation_required: bool = False,
) -> dict[str, object]:
    return {
        "field_name": field_name,
        "value": value,
        "source_document": source_document,
        "source_texte": source_text,
        "niveau_confiance": normalize_confidence(confidence),
        "necessite_validation": validation_required or normalize_confidence(confidence) == "bas",
        "mode_extraction": "heuristique_preparee_pour_llm",
    }


def first_non_empty_line(text: str) -> str:
    for line in [line.strip() for line in text.splitlines() if line.strip()]:
        if len(line) > 3:
            return line[:140]
    return ""


def extract_wf2b_structured(client_files, project_files) -> dict[str, object]:
    client_payloads = extract_document_payloads(client_files)
    project_payloads = extract_document_payloads(project_files)

    client_text = "\n\n".join(payload["text"] for payload in client_payloads if payload["text"]).lower()
    project_text = "\n\n".join(payload["text"] for payload in project_payloads if payload["text"]).lower()

    legal_forms = ["association", "sas", "sarl", "ei", "micro-entreprise", "entreprise individuelle"]
    detected_legal_form = next((form for form in legal_forms if form in client_text), "Non detectee")

    siret_match = re.search(r"\b\d{14}\b", client_text)
    email_match = re.search(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", client_text)
    phone_match = re.search(r"(\+262|0)[0-9\s.-]{8,}", client_text)
    amount_match = re.search(r"\b\d[\d\s.,]{2,}\s?(?:€|euros?)\b", project_text, flags=re.IGNORECASE)
    date_matches = re.findall(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", project_text)

    activity_keywords = [
        "formation", "culture", "musique", "audiovisuel", "numerique",
        "spectacle", "production", "association", "studio",
    ]
    project_keywords = [
        "objectif", "public", "beneficiaire", "planning", "calendrier",
        "budget", "financement", "action", "atelier", "accompagnement",
    ]

    client_source = client_payloads[0]["document_name"] if client_payloads else ""
    client_source_text = client_payloads[0]["text"] if client_payloads else ""
    project_source = project_payloads[0]["document_name"] if project_payloads else ""
    project_source_text = project_payloads[0]["text"] if project_payloads else ""

    detected_activities = [keyword for keyword in activity_keywords if keyword in client_text]
    detected_project_elements = [keyword for keyword in project_keywords if keyword in project_text]

    profil_client = {
        "forme_juridique": build_field_value(
            "forme_juridique",
            detected_legal_form,
            client_source,
            find_source_excerpt(client_source_text, detected_legal_form) if detected_legal_form != "Non detectee" else "",
            confidence="haut" if detected_legal_form != "Non detectee" else "bas",
            validation_required=detected_legal_form == "Non detectee",
        ),
        "siret": build_field_value(
            "siret",
            siret_match.group(0) if siret_match else "Non detecte",
            client_source,
            find_source_excerpt(client_source_text, siret_match.group(0)) if siret_match else "",
            confidence="haut" if siret_match else "bas",
            validation_required=siret_match is None,
        ),
        "email": build_field_value(
            "email",
            email_match.group(0) if email_match else "Non detecte",
            client_source,
            find_source_excerpt(client_source_text, email_match.group(0)) if email_match else "",
            confidence="haut" if email_match else "bas",
            validation_required=email_match is None,
        ),
        "telephone": build_field_value(
            "telephone",
            phone_match.group(0).strip() if phone_match else "Non detecte",
            client_source,
            find_source_excerpt(client_source_text, phone_match.group(0)) if phone_match else "",
            confidence="moyen" if phone_match else "bas",
            validation_required=phone_match is None,
        ),
        "activites": [
            build_field_value(
                "activite",
                keyword,
                client_source,
                find_source_excerpt(client_source_text, keyword),
                confidence="moyen",
            )
            for keyword in detected_activities[:8]
        ],
        "nom_structure": build_field_value(
            "nom_structure",
            first_non_empty_line(client_source_text) or Path(client_source).stem if client_source else "Non detecte",
            client_source,
            find_source_excerpt(client_source_text, first_non_empty_line(client_source_text)) if client_source_text else "",
            confidence="moyen" if client_source else "bas",
            validation_required=not client_source,
        ),
    }

    donnees_projet = {
        "titre_projet": build_field_value(
            "titre_projet",
            first_non_empty_line(project_source_text) or "Non detecte",
            project_source,
            find_source_excerpt(project_source_text, first_non_empty_line(project_source_text)) if project_source_text else "",
            confidence="moyen" if project_source_text else "bas",
            validation_required=not project_source_text,
        ),
        "montant_detecte": build_field_value(
            "montant_detecte",
            amount_match.group(0) if amount_match else "Non detecte",
            project_source,
            find_source_excerpt(project_source_text, amount_match.group(0)) if amount_match else "",
            confidence="haut" if amount_match else "bas",
            validation_required=amount_match is None,
        ),
        "dates_detectees": [
            build_field_value(
                "date_projet",
                match,
                project_source,
                find_source_excerpt(project_source_text, match),
                confidence="moyen",
            )
            for match in date_matches[:5]
        ],
        "elements_detectes": [
            build_field_value(
                "element_projet",
                keyword,
                project_source,
                find_source_excerpt(project_source_text, keyword),
                confidence="moyen",
            )
            for keyword in detected_project_elements[:8]
        ],
    }

    return {
        "profil_client": profil_client,
        "donnees_projet": donnees_projet,
        "metadata": {
            "mode_extraction": "heuristique_preparee_pour_llm",
            "documents_client_sources": [payload["document_name"] for payload in client_payloads],
            "documents_projet_sources": [payload["document_name"] for payload in project_payloads],
        },
        "llm_contract": {
            "sortie_cible": "profil_client + donnees_projet + metadata",
            "niveaux_confiance_valides": sorted(VALID_CONFIDENCE),
        },
    }


def summarize_wf2b_client_profile(wf2b_structured: dict[str, object]) -> dict[str, str]:
    profil_client = wf2b_structured.get("profil_client", {})
    activities = profil_client.get("activites", [])
    return {
        "forme_juridique": profil_client.get("forme_juridique", {}).get("value", "Non detectee"),
        "siret": profil_client.get("siret", {}).get("value", "Non detecte"),
        "email": profil_client.get("email", {}).get("value", "Non detecte"),
        "telephone": profil_client.get("telephone", {}).get("value", "Non detecte"),
        "activites_detectees": ", ".join(item.get("value", "") for item in activities) if activities else "Aucune",
    }


def summarize_wf2b_project_data(wf2b_structured: dict[str, object]) -> dict[str, str]:
    donnees_projet = wf2b_structured.get("donnees_projet", {})
    dates = donnees_projet.get("dates_detectees", [])
    elements = donnees_projet.get("elements_detectes", [])
    return {
        "titre_projet": donnees_projet.get("titre_projet", {}).get("value", "Non detecte"),
        "montant_detecte": donnees_projet.get("montant_detecte", {}).get("value", "Non detecte"),
        "dates_detectees": ", ".join(item.get("value", "") for item in dates) if dates else "Aucune",
        "elements_detectes": ", ".join(item.get("value", "") for item in elements) if elements else "Aucun",
    }


def build_bridge_from_wf2(wf2a_structured: dict[str, object], wf2b_structured: dict[str, object]) -> dict[str, str]:
    criteres = wf2a_structured.get("criteres", [])
    metadata = wf2a_structured.get("metadata", {})
    profil_client = summarize_wf2b_client_profile(wf2b_structured)
    donnees_projet = summarize_wf2b_project_data(wf2b_structured)

    bridge = {
        "type_structure_requise": "A verifier",
        "date_limite_dossier": metadata.get("date_limite_detectee", "Aucune"),
        "montant_dossier": metadata.get("montant_max_detecte", "Aucun"),
        "conditions_dossier": "Aucune",
        "type_structure_client": profil_client.get("forme_juridique", "Non detectee"),
        "identite_client": profil_client.get("activites_detectees", "Aucune"),
        "montant_projet": donnees_projet.get("montant_detecte", "Non detecte"),
        "dates_projet": donnees_projet.get("dates_detectees", "Aucune"),
        "elements_projet": donnees_projet.get("elements_detectes", "Aucun"),
    }

    extracted_conditions = []
    for criterion in criteres:
        label = str(criterion.get("libelle", ""))
        detail = str(criterion.get("detail", ""))
        category = str(criterion.get("categorie", ""))

        if "date" in label.lower() and bridge["date_limite_dossier"] in {"Aucune", "Non detectee"}:
            bridge["date_limite_dossier"] = detail
        if "montant" in label.lower() and bridge["montant_dossier"] in {"Aucun", "Non detecte"}:
            bridge["montant_dossier"] = detail
        if category in {"obligatoire", "bloquant"}:
            extracted_conditions.append(label)
        if "association" in detail.lower() or "association" in label.lower():
            bridge["type_structure_requise"] = "association"

    if extracted_conditions:
        bridge["conditions_dossier"] = " | ".join(extracted_conditions[:8])

    return bridge
