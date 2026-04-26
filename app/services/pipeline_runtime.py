from __future__ import annotations

from copy import deepcopy
import re

from app.services.wf2 import (
    VALID_CONFIDENCE,
    build_bridge_from_wf2,
    build_field_value,
    build_structured_criterion,
    extract_wf2a_structured,
    extract_wf2b_structured,
    normalize_category,
    normalize_confidence,
    normalize_domain,
)
from app.services.bridge_completion import merge_completed_bridge_into_wf2
from app.services.wf2_llm import request_wf2a_llm_payload
from app.services.wf2b_llm import request_wf2b_llm_payload
from app.services.wf3 import build_wf3_analysis
from app.services.wf3_llm import request_wf3_llm_payload
from app.services.wf4 import (
    build_completion_checklist,
    build_project_budget_markdown,
    build_project_presentation_markdown,
    build_wf4_outputs,
)
from app.services.wf4_llm import (
    get_section_guidance,
    infer_presentation_section_type,
    request_wf4a_llm_payload,
    request_wf4a_section_payload,
    request_wf4b_llm_payload,
    request_wf4c_llm_payload,
)


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "oui", "yes"}
    return default


def _normalize_field_dict(field_name: str, raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raw = {}
    return {
        "field_name": field_name,
        "value": str(raw.get("value", "Non detecte")),
        "source_document": str(raw.get("source_document", "")),
        "source_texte": str(raw.get("source_texte", "")),
        "niveau_confiance": normalize_confidence(str(raw.get("niveau_confiance", "moyen"))),
        "necessite_validation": _coerce_bool(raw.get("necessite_validation", False)),
        "mode_extraction": str(raw.get("mode_extraction", "llm_direct_python")),
    }


def _normalize_field_list(field_name: str, raw_items: object) -> list[dict[str, object]]:
    if not isinstance(raw_items, list):
        raw_items = []
    return [_normalize_field_dict(field_name, item) for item in raw_items if isinstance(item, dict)]


def normalize_wf2a_llm_payload(payload: dict[str, object], fallback: dict[str, object]) -> dict[str, object]:
    criteres = []
    raw_criteres = payload.get("criteres", []) if isinstance(payload, dict) else []
    if isinstance(raw_criteres, list):
        for index, item in enumerate(raw_criteres, start=1):
            if not isinstance(item, dict):
                continue
            criteres.append(
                build_structured_criterion(
                    index,
                    str(item.get("categorie", "interpretatif")),
                    str(item.get("domaine", "administratif")),
                    str(item.get("libelle", f"Critere {index}")),
                    str(item.get("detail", "")),
                    str(item.get("source_document", "")),
                    str(item.get("source_texte", "")),
                    est_piece_exigee=_coerce_bool(item.get("est_piece_exigee", False)),
                    est_critere_eliminatoire=_coerce_bool(item.get("est_critere_eliminatoire", False)),
                    niveau_confiance=str(item.get("niveau_confiance", "moyen")),
                    necessite_validation=_coerce_bool(item.get("necessite_validation", False)),
                )
            )

    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}

    fallback_metadata = fallback.get("metadata", {})
    return {
        "criteres": criteres or list(fallback.get("criteres", [])),
        "metadata": {
            "type_dossier_detecte": str(metadata.get("type_dossier_detecte", fallback_metadata.get("type_dossier_detecte", "autre"))),
            "financeur_detecte": str(metadata.get("financeur_detecte", fallback_metadata.get("financeur_detecte", "Non detecte"))),
            "montant_max_detecte": str(metadata.get("montant_max_detecte", fallback_metadata.get("montant_max_detecte", "Non detecte"))),
            "date_limite_detectee": str(metadata.get("date_limite_detectee", fallback_metadata.get("date_limite_detectee", "Non detectee"))),
            "nb_criteres_extraits": len(criteres or list(fallback.get("criteres", []))),
            "rubriques_attendues": list(metadata.get("rubriques_attendues", fallback_metadata.get("rubriques_attendues", []))),
            "pieces_attendues": list(metadata.get("pieces_attendues", fallback_metadata.get("pieces_attendues", []))),
            "contraintes_budgetaires": list(metadata.get("contraintes_budgetaires", fallback_metadata.get("contraintes_budgetaires", []))),
            "attentes_redactionnelles": list(metadata.get("attentes_redactionnelles", fallback_metadata.get("attentes_redactionnelles", []))),
            "mode_extraction": "llm_direct_python",
            "documents_sources": list(fallback_metadata.get("documents_sources", [])),
        },
        "llm_contract": deepcopy(fallback.get("llm_contract", {})),
    }


def normalize_wf2b_llm_payload(payload: dict[str, object], fallback: dict[str, object]) -> dict[str, object]:
    payload = payload if isinstance(payload, dict) else {}
    profil_client_raw = payload.get("profil_client", {})
    donnees_projet_raw = payload.get("donnees_projet", {})
    metadata_raw = payload.get("metadata", {})

    if not isinstance(profil_client_raw, dict):
        profil_client_raw = {}
    if not isinstance(donnees_projet_raw, dict):
        donnees_projet_raw = {}
    if not isinstance(metadata_raw, dict):
        metadata_raw = {}

    fallback_metadata = fallback.get("metadata", {})
    return {
        "profil_client": {
            "nom_structure": _normalize_field_dict("nom_structure", profil_client_raw.get("nom_structure", {})),
            "forme_juridique": _normalize_field_dict("forme_juridique", profil_client_raw.get("forme_juridique", {})),
            "siret": _normalize_field_dict("siret", profil_client_raw.get("siret", {})),
            "email": _normalize_field_dict("email", profil_client_raw.get("email", {})),
            "telephone": _normalize_field_dict("telephone", profil_client_raw.get("telephone", {})),
            "territoire_implantation": _normalize_field_dict("territoire_implantation", profil_client_raw.get("territoire_implantation", {})),
            "activites": _normalize_field_list("activite", profil_client_raw.get("activites", [])),
            "historique_references": _normalize_field_list("historique_reference", profil_client_raw.get("historique_references", [])),
            "capacites_porteuses": _normalize_field_list("capacite_porteuse", profil_client_raw.get("capacites_porteuses", [])),
        },
        "donnees_projet": {
            "titre_projet": _normalize_field_dict("titre_projet", donnees_projet_raw.get("titre_projet", {})),
            "montant_detecte": _normalize_field_dict("montant_detecte", donnees_projet_raw.get("montant_detecte", {})),
            "contexte_besoin": _normalize_field_list("contexte_besoin", donnees_projet_raw.get("contexte_besoin", [])),
            "objectifs": _normalize_field_list("objectif", donnees_projet_raw.get("objectifs", [])),
            "actions_prevues": _normalize_field_list("action_prevue", donnees_projet_raw.get("actions_prevues", [])),
            "publics_cibles": _normalize_field_list("public_cible", donnees_projet_raw.get("publics_cibles", [])),
            "territoire_concerne": _normalize_field_list("territoire_concerne", donnees_projet_raw.get("territoire_concerne", [])),
            "dates_detectees": _normalize_field_list("date_projet", donnees_projet_raw.get("dates_detectees", [])),
            "elements_detectes": _normalize_field_list("element_projet", donnees_projet_raw.get("elements_detectes", [])),
            "partenariats": _normalize_field_list("partenariat", donnees_projet_raw.get("partenariats", [])),
            "moyens_humains_techniques": _normalize_field_list("moyens_humains_techniques", donnees_projet_raw.get("moyens_humains_techniques", [])),
            "livrables_prevus": _normalize_field_list("livrable_prevu", donnees_projet_raw.get("livrables_prevus", [])),
            "cofinancements": _normalize_field_list("cofinancement", donnees_projet_raw.get("cofinancements", [])),
        },
        "metadata": {
            "mode_extraction": "llm_direct_python",
            "documents_client_sources": list(metadata_raw.get("documents_client_sources", fallback_metadata.get("documents_client_sources", []))),
            "documents_projet_sources": list(metadata_raw.get("documents_projet_sources", fallback_metadata.get("documents_projet_sources", []))),
        },
        "llm_contract": deepcopy(fallback.get("llm_contract", {})),
    }


def normalize_wf3_llm_payload(payload: dict[str, object], fallback: dict[str, object]) -> dict[str, object]:
    payload = payload if isinstance(payload, dict) else {}
    results = []
    raw_results = payload.get("resultats_criteres", [])
    if isinstance(raw_results, list):
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            status = str(item.get("statut", "a_confirmer"))
            if status not in {"valide", "a_confirmer", "manquant", "non_valide"}:
                status = "a_confirmer"
            results.append(
                {
                    "critere_id": item.get("critere_id"),
                    "libelle": str(item.get("libelle", "")),
                    "categorie": normalize_category(str(item.get("categorie", "souhaitable"))),
                    "domaine": normalize_domain(str(item.get("domaine", "administratif"))),
                    "source_document": str(item.get("source_document", "")),
                    "source_texte": str(item.get("source_texte", "")),
                    "bloc_cible": str(item.get("bloc_cible", "mixte")),
                    "statut": status,
                    "score": int(item.get("score", 0) or 0),
                    "justification": str(item.get("justification", "")),
                    "ecart": str(item.get("ecart", "")),
                    "action_requise": str(item.get("action_requise", "")),
                    "donnee_utilisee": str(item.get("donnee_utilisee", "")),
                    "niveau_confiance": normalize_confidence(str(item.get("niveau_confiance", "moyen"))),
                    "necessite_validation": _coerce_bool(item.get("necessite_validation", status == "a_confirmer")),
                }
            )

    if not results:
        return fallback

    counts = {"valide": 0, "a_confirmer": 0, "manquant": 0, "non_valide": 0}
    for result in results:
        counts[result["statut"]] += 1

    return {
        "score_global": int(payload.get("score_global", fallback.get("score_global", 0)) or 0),
        "statut_eligibilite": str(payload.get("statut_eligibilite", fallback.get("statut_eligibilite", "a confirmer"))),
        "niveau_confiance": normalize_confidence(str(payload.get("niveau_confiance", fallback.get("niveau_confiance", "moyen")))),
        "sous_scores": payload.get("sous_scores", fallback.get("sous_scores", {})),
        "resume_executif": str(payload.get("resume_executif", fallback.get("resume_executif", ""))),
        "resultats_criteres": results,
        "counts": counts,
        "global_bonus": fallback.get("global_bonus", 0),
    }


def resolve_wf2a_structured(
    dossier_files,
    prefer_llm: bool = True,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    fallback = extract_wf2a_structured(dossier_files)
    meta = {"engine": "heuristique_locale", "fallback_used": False}
    if not prefer_llm or not dossier_files:
        return fallback, meta

    llm_result = request_wf2a_llm_payload(
        dossier_files,
        provider_override=llm_provider,
        model_override=llm_model,
    )
    if not llm_result.get("ok") or not isinstance(llm_result.get("payload"), dict):
        meta.update({"fallback_used": True, "llm_error": llm_result.get("error", "llm_error")})
        return fallback, meta

    structured = normalize_wf2a_llm_payload(llm_result["payload"], fallback)
    meta.update({
        "engine": "llm_direct_python",
        "model": llm_result.get("model", ""),
        "provider": llm_result.get("provider", ""),
        "usage": llm_result.get("usage", {}),
        "fallback_used": False,
    })
    return structured, meta


def resolve_wf2b_structured(
    client_files,
    project_files,
    prefer_llm: bool = True,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    fallback = extract_wf2b_structured(client_files, project_files)
    meta = {"engine": "heuristique_locale", "fallback_used": False}
    if not prefer_llm or (not client_files and not project_files):
        return fallback, meta

    llm_result = request_wf2b_llm_payload(
        client_files,
        project_files,
        provider_override=llm_provider,
        model_override=llm_model,
    )
    if not llm_result.get("ok") or not isinstance(llm_result.get("payload"), dict):
        meta.update({"fallback_used": True, "llm_error": llm_result.get("error", "llm_error")})
        return fallback, meta

    structured = normalize_wf2b_llm_payload(llm_result["payload"], fallback)
    meta.update({
        "engine": "llm_direct_python",
        "model": llm_result.get("model", ""),
        "provider": llm_result.get("provider", ""),
        "usage": llm_result.get("usage", {}),
        "fallback_used": False,
    })
    return structured, meta


def resolve_wf3_analysis(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    global_context_bridge: dict[str, str] | None = None,
    prefer_llm: bool = True,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    fallback = build_wf3_analysis(wf2a_structured, wf2b_structured, global_context_bridge)
    meta = {"engine": "heuristique_locale", "fallback_used": False}
    if not prefer_llm:
        return fallback, meta

    llm_result = request_wf3_llm_payload(
        wf2a_structured,
        wf2b_structured,
        global_context_bridge,
        provider_override=llm_provider,
        model_override=llm_model,
    )
    if not llm_result.get("ok") or not isinstance(llm_result.get("payload"), dict):
        meta.update({"fallback_used": True, "llm_error": llm_result.get("error", "llm_error")})
        return fallback, meta

    structured = normalize_wf3_llm_payload(llm_result["payload"], fallback)
    meta.update({
        "engine": "llm_direct_python",
        "model": llm_result.get("model", ""),
        "provider": llm_result.get("provider", ""),
        "usage": llm_result.get("usage", {}),
        "fallback_used": False,
    })
    return structured, meta


def _dedup_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if str(item).strip()))


def _normalize_presentation_payload(payload: dict[str, object], fallback_outputs: dict[str, object]) -> dict[str, object]:
    payload = payload if isinstance(payload, dict) else {}
    sections = []
    raw_sections = payload.get("sections", [])
    if isinstance(raw_sections, list):
        raw_sections = sorted(
            [item for item in raw_sections if isinstance(item, dict)],
            key=lambda item: int(item.get("ordre", 999) or 999),
        )
        for item in raw_sections:
            title = str(item.get("titre", "")).strip() or "Section"
            objective = str(item.get("objectif_section", "")).strip()
            body = str(item.get("contenu_redige", "")).strip() or "A_COMPLETER"
            vigilance = [str(entry).strip() for entry in item.get("points_de_vigilance", []) if str(entry).strip()]
            sources = [str(entry).strip() for entry in item.get("sources_utilisees", []) if str(entry).strip()]
            content_parts = []
            if objective:
                content_parts.append(f"Objectif : {objective}")
            content_parts.append(body)
            if vigilance:
                content_parts.append("Points de vigilance : " + " | ".join(vigilance))
            if sources:
                content_parts.append("Sources : " + " | ".join(sources))
            sections.append(
                {
                    "section": title,
                    "statut": str(item.get("statut", "a_completer")).strip() or "a_completer",
                    "contenu": "\n\n".join(content_parts),
                }
            )

    if not sections:
        return fallback_outputs["livrables"]["presentation_projet"]

    markdown = build_project_presentation_markdown(sections)
    return {
        "sections": sections,
        "markdown": markdown,
        "resume_executif": str(payload.get("resume_executif", "")).strip(),
        "donnees_manquantes": _dedup_strings([str(item) for item in payload.get("donnees_manquantes", [])]),
        "pieces_ou_annexes_a_prevoir": _dedup_strings(
            [str(item) for item in payload.get("pieces_ou_annexes_a_prevoir", [])]
        ),
    }


def _normalize_single_presentation_section(payload: dict[str, object], fallback_section: dict[str, object]) -> dict[str, object]:
    payload = payload if isinstance(payload, dict) else {}
    titre = str(payload.get("titre", "")).strip() or str(fallback_section.get("section", "")).strip() or "Section"
    objectif = str(payload.get("objectif_section", "")).strip() or titre
    contenu = str(payload.get("contenu_redige", "")).strip() or str(fallback_section.get("contenu", "")).strip()
    statut = str(payload.get("statut", "")).strip().lower()
    if statut not in {"redige", "partiel", "a_completer", "a_confirmer"}:
        statut = str(fallback_section.get("statut", "partiel")).strip().lower() or "partiel"
    sources = _dedup_strings([str(item) for item in payload.get("sources_utilisees", [])])
    vigilances = _dedup_strings([str(item) for item in payload.get("points_de_vigilance", [])])
    content_parts = []
    if objectif:
        content_parts.append(f"Objectif : {objectif}")
    if contenu:
        content_parts.append(contenu)
    if vigilances:
        content_parts.append("Points de vigilance : " + " | ".join(vigilances))
    if sources:
        content_parts.append("Sources : " + " | ".join(sources))
    return {
        "section": titre,
        "statut": statut,
        "contenu": "\n\n".join(content_parts).strip() or str(fallback_section.get("contenu", "")).strip(),
    }


def _should_enrich_presentation_section(section: dict[str, object], enriched_count: int) -> bool:
    if enriched_count >= 5:
        return False
    title = str(section.get("section", "")).strip().lower()
    content = str(section.get("contenu", "")).strip()
    status = str(section.get("statut", "")).strip().lower()
    strategic_keywords = (
        "resume",
        "contexte",
        "description",
        "public",
        "methodologie",
        "mise en oeuvre",
        "moyens",
        "partenariat",
        "budget",
        "plan de financement",
    )
    if not any(keyword in title for keyword in strategic_keywords):
        return False
    return len(content) < 1200 or status in {"partiel", "a_completer", "a_confirmer"}


def _normalize_budget_rows(items: object) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        section = str(item.get("section", "")).strip()
        sous_section = str(item.get("sous_section", "")).strip()
        poste = (
            str(item.get("poste", "")).strip()
            or str(item.get("intitule", "")).strip()
            or str(item.get("financeur_ou_source", "")).strip()
            or str(item.get("financeur", "")).strip()
            or str(item.get("source", "")).strip()
            or "A_COMPLETER"
        )
        montant = (
            str(item.get("montant", "")).strip()
            or str(item.get("montant_previsionnel", "")).strip()
            or str(item.get("montant_total", "")).strip()
            or str(item.get("cout_total", "")).strip()
            or "A_COMPLETER"
        )
        commentaire_parts = [
            str(item.get("commentaire", "")).strip(),
            str(item.get("description", "")).strip(),
            str(item.get("detail", "")).strip(),
            str(item.get("details", "")).strip(),
            str(item.get("remarques", "")).strip(),
        ]
        quantite = str(item.get("quantite", "")).strip()
        unite = str(item.get("unite", "")).strip()
        cout_unitaire = str(item.get("cout_unitaire", "")).strip()
        if quantite or unite or cout_unitaire:
            commentaire_parts.append(
                "Quantite="
                f"{quantite or 'A_COMPLETER'} | "
                f"Unite={unite or 'A_COMPLETER'} | "
                f"Cout unitaire={cout_unitaire or 'A_COMPLETER'}"
            )
        financeurs = item.get("financeurs", [])
        if isinstance(financeurs, list):
            financeurs_text = ", ".join(str(entry).strip() for entry in financeurs if str(entry).strip())
            if financeurs_text:
                commentaire_parts.append(f"Financeurs lies: {financeurs_text}")
        rows.append(
            {
                "section": section,
                "sous_section": sous_section,
                "poste": poste,
                "montant_previsionnel": montant,
                "commentaire": " | ".join(part for part in commentaire_parts if part),
                "statut": str(item.get("statut", "")).strip() or str(item.get("status", "")).strip(),
                "source": str(item.get("source", "")).strip(),
            }
        )
    return rows


def _parse_budget_number(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    upper = text.upper()
    if upper in {"A_COMPLETER", "A COMPLETER", "A_CONFIRMER", "CONFIRME"}:
        return None
    cleaned = text.replace("\u202f", "").replace("\xa0", "").replace(" ", "")
    cleaned = cleaned.replace("EUR", "").replace("€", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    cleaned = re.sub(r"[^0-9.\\-]", "", cleaned)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _format_budget_number(value: float) -> str:
    rounded = round(value, 2)
    if rounded.is_integer():
        return f"{int(rounded)} EUR"
    return f"{rounded:.2f} EUR"


def _enrich_budget_amounts(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for row in rows:
        row_copy = dict(row)
        current_amount = str(row_copy.get("montant_previsionnel", "")).strip()
        if current_amount in {"", "A_COMPLETER", "A completer"}:
            comment = str(row_copy.get("commentaire", "")).strip()
            qty_match = re.search(r"Quantite=([^|]+)", comment)
            unit_cost_match = re.search(r"Cout unitaire=([^|]+)", comment)
            qty = _parse_budget_number(qty_match.group(1).strip() if qty_match else "")
            unit_cost = _parse_budget_number(unit_cost_match.group(1).strip() if unit_cost_match else "")
            if qty is not None and unit_cost is not None:
                row_copy["montant_previsionnel"] = _format_budget_number(qty * unit_cost)
        enriched.append(row_copy)
    return enriched


def _extract_budget_root(payload: dict[str, object]) -> dict[str, object]:
    payload = payload if isinstance(payload, dict) else {}
    nested = payload.get("budget_projet")
    if isinstance(nested, dict):
        return nested
    return payload


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_budget_group_dict(groups: object, *, kind: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not isinstance(groups, dict):
        return rows

    for _, group in groups.items():
        if not isinstance(group, dict):
            continue
        section_name = str(group.get("intitule", "")).strip() or str(group.get("section", "")).strip()
        details = group.get("details", [])
        if not isinstance(details, list):
            continue

        for detail in details:
            if not isinstance(detail, dict):
                continue

            base_comment_parts = [
                str(detail.get("remarque", "")).strip(),
                str(detail.get("commentaire", "")).strip(),
                str(detail.get("description", "")).strip(),
            ]
            quantite = str(detail.get("quantite", "")).strip()
            unite = str(detail.get("unite", "")).strip()
            cout_unitaire = str(detail.get("cout_unitaire", "")).strip()
            if quantite or unite or cout_unitaire:
                base_comment_parts.append(
                    "Quantite="
                    f"{quantite or 'A_COMPLETER'} | "
                    f"Unite={unite or 'A_COMPLETER'} | "
                    f"Cout unitaire={cout_unitaire or 'A_COMPLETER'}"
                )

            if kind == "charge":
                rows.append(
                    {
                        "section": section_name,
                        "poste": str(detail.get("poste", "")).strip() or section_name,
                        "montant_previsionnel": (
                            str(detail.get("montant", "")).strip()
                            or str(detail.get("montant_total", "")).strip()
                            or "A_COMPLETER"
                        ),
                        "commentaire": " | ".join(part for part in base_comment_parts if part),
                        "statut": str(detail.get("statut", "")).strip(),
                        "source": str(detail.get("financeur", "")).strip(),
                    }
                )
            else:
                rows.append(
                    {
                        "section": section_name,
                        "poste": str(detail.get("source", "")).strip()
                        or str(detail.get("poste", "")).strip()
                        or section_name,
                        "montant_previsionnel": (
                            str(detail.get("montant_sollicite", "")).strip()
                            or str(detail.get("montant", "")).strip()
                            or str(detail.get("montant_detecte", "")).strip()
                            or "A_COMPLETER"
                        ),
                        "commentaire": " | ".join(part for part in base_comment_parts if part),
                        "statut": str(detail.get("statut", "")).strip(),
                        "source": str(detail.get("source", "")).strip(),
                    }
                )

    return rows


def _flatten_budget_section(section: object, *, kind: str) -> list[dict[str, object]]:
    if not isinstance(section, dict):
        return []

    section_name = str(section.get("section", "")).strip() or str(section.get("titre", "")).strip()
    flattened: list[dict[str, object]] = []

    def append_lines(lines: object, current_sub_section: str = "") -> None:
        if not isinstance(lines, list):
            return
        for line in lines:
            if not isinstance(line, dict):
                continue
            parent_label = str(line.get("poste", "")).strip() or str(line.get("intitule", "")).strip()
            description = line.get("description", "") or line.get("detail", "") or line.get("details", "")

            sous_postes = line.get("sous_postes", [])
            if isinstance(sous_postes, list) and sous_postes:
                for sub_line in sous_postes:
                    if not isinstance(sub_line, dict):
                        continue
                    sub_label = str(sub_line.get("intitule", "")).strip() or parent_label
                    combined_description = " | ".join(
                        part
                        for part in [str(description).strip(), str(sub_line.get("detail", "")).strip(), str(sub_line.get("details", "")).strip()]
                        if part
                    )
                    flattened.append(
                        {
                            "section": section_name,
                            "sous_section": current_sub_section or parent_label,
                            "poste": sub_label if kind == "charge" else "",
                            "financeur_ou_source": sub_label if kind == "produit" else "",
                            "financeur": parent_label if kind == "produit" else "",
                            "intitule": sub_label,
                            "description": combined_description,
                            "quantite": sub_line.get("quantite", ""),
                            "unite": sub_line.get("unite", ""),
                            "cout_unitaire": sub_line.get("cout_unitaire", ""),
                            "montant_total": sub_line.get("montant_total", "") if kind == "charge" else sub_line.get("montant", ""),
                            "montant": sub_line.get("montant", ""),
                            "statut": sub_line.get("statut", ""),
                            "source": sub_line.get("source", ""),
                            "commentaire": sub_line.get("commentaire", "") or sub_line.get("remarques", "") or f"Poste parent : {parent_label}",
                            "financeurs": sub_line.get("financeurs", []),
                        }
                    )
                continue

            flattened.append(
                {
                    "section": section_name,
                    "sous_section": current_sub_section,
                    "poste": parent_label if kind == "charge" else "",
                    "financeur_ou_source": parent_label if kind == "produit" else "",
                    "financeur": str(line.get("financeur", "")).strip() if kind == "produit" else "",
                    "intitule": str(line.get("intitule", "")).strip(),
                    "description": description,
                    "quantite": line.get("quantite", ""),
                    "unite": line.get("unite", ""),
                    "cout_unitaire": line.get("cout_unitaire", ""),
                    "montant_total": line.get("montant_total", "") if kind == "charge" else line.get("montant", ""),
                    "montant": line.get("montant", ""),
                    "statut": line.get("statut", ""),
                    "source": line.get("source", ""),
                    "commentaire": line.get("commentaire", "") or line.get("remarques", ""),
                    "financeurs": line.get("financeurs", []),
                }
            )

    append_lines(section.get("lignes", []))
    append_lines(section.get("details", []))

    sous_sections = section.get("sous_sections", [])
    if isinstance(sous_sections, list):
        for sub_section in sous_sections:
            if not isinstance(sub_section, dict):
                continue
            sub_name = str(sub_section.get("titre", "")).strip() or str(sub_section.get("section", "")).strip()
            append_lines(sub_section.get("lignes", []), sub_name)
            append_lines(sub_section.get("details", []), sub_name)

    return flattened


def _normalize_budget_notes(payload: dict[str, object]) -> list[str]:
    notes = _dedup_strings([str(item) for item in payload.get("notes_budgetaires", [])])
    notes.extend(_dedup_strings([str(item) for item in payload.get("vigilances", [])]))

    financeur = payload.get("financeur_principal", {})
    if isinstance(financeur, dict):
        financeur_note = " | ".join(
            part
            for part in [
                str(financeur.get("nom", "")).strip(),
                str(financeur.get("type", "")).strip(),
                f"taux max={str(financeur.get('taux_max', '')).strip()}" if str(financeur.get("taux_max", "")).strip() else "",
                f"plafond={str(financeur.get('plafond', '')).strip()}" if str(financeur.get("plafond", "")).strip() else "",
            ]
            if part
        )
        if financeur_note:
            notes.append("Financeur principal : " + financeur_note)
        notes.extend(_dedup_strings(_coerce_string_list(financeur.get("criteres_eligibilite", []))))

    periode = payload.get("periode", {})
    if isinstance(periode, dict):
        debut = str(periode.get("debut", "")).strip()
        fin = str(periode.get("fin", "")).strip()
        if debut or fin:
            notes.append(f"Periode budgetaire : {debut or 'A_COMPLETER'} -> {fin or 'A_COMPLETER'}")

    synthese = str(payload.get("synthese_financements", "")).strip() or str(payload.get("synthese_executive", "")).strip()
    if synthese:
        notes.append(synthese)
    synthese_financement = payload.get("synthese_financement", {})
    if isinstance(synthese_financement, dict):
        for label, key in [
            ("Montant total projet", "montant_total_projet"),
            ("Montant subvention principale", "montant_subvention_CNM"),
            ("Montant autofinancement", "montant_autofinancement"),
            ("Montant cofinancements", "montant_cofinancements"),
            ("Taux subvention principale", "taux_subvention_CNM"),
            ("Taux autofinancement", "taux_autofinancement"),
            ("Taux cofinancement", "taux_cofinancement"),
        ]:
            value = str(synthese_financement.get(key, "")).strip()
            if value:
                notes.append(f"{label} : {value}")

    analyse = payload.get("analyse_equilibre") or payload.get("analyse_budgetaire")
    if isinstance(analyse, str):
        if analyse.strip():
            notes.append(analyse.strip())
    elif isinstance(analyse, dict):
        notes.extend(_dedup_strings(_coerce_string_list(analyse.get("alertes", []))))
        notes.extend(_dedup_strings(_coerce_string_list(analyse.get("coherences_detectees", []))))
        notes.extend(_dedup_strings(_coerce_string_list(analyse.get("incoherences_detectees", []))))
        niveau = str(analyse.get("niveau_fiabilite", "")).strip()
        if niveau:
            notes.append(f"Niveau de fiabilite budgetaire : {niveau}")

    contraintes = payload.get("contraintes_financeur", {})
    if isinstance(contraintes, dict):
        for label, key in [
            ("Plafond subvention", "plafond_subvention"),
            ("Taux maximum", "taux_maximum"),
            ("Autofinancement minimum", "autofinancement_minimum"),
            ("Cofinancement attendu", "cofinancement_attendu"),
        ]:
            value = str(contraintes.get(key, "")).strip()
            if value:
                notes.append(f"{label} : {value}")
        notes.extend(_dedup_strings(_coerce_string_list(contraintes.get("regles_specifiques", []))))

    pieces = payload.get("pièces_jointes", payload.get("pieces_jointes", []))
    pieces_list = _coerce_string_list(pieces)
    if pieces_list:
        notes.append("Pieces jointes budget : " + " | ".join(str(item).strip() for item in pieces_list if str(item).strip()))

    return _dedup_strings(notes)


def _has_meaningful_budget_amount(row: dict[str, object]) -> bool:
    value = str(row.get("montant_previsionnel", "")).strip()
    return value not in {"", "A_COMPLETER", "A completer", "A_CONFIRMER"}


def _merge_budget_rows(
    primary_rows: list[dict[str, object]],
    fallback_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    max_len = max(len(primary_rows), len(fallback_rows))
    for index in range(max_len):
        primary = primary_rows[index] if index < len(primary_rows) and isinstance(primary_rows[index], dict) else {}
        fallback = fallback_rows[index] if index < len(fallback_rows) and isinstance(fallback_rows[index], dict) else {}
        row = dict(fallback)
        row.update(primary)
        if not str(row.get("montant_previsionnel", "")).strip():
            fallback_amount = str(fallback.get("montant_previsionnel", "")).strip()
            if fallback_amount:
                row["montant_previsionnel"] = fallback_amount
        if str(row.get("montant_previsionnel", "")).strip() in {"", "A completer"}:
            row["montant_previsionnel"] = "A_COMPLETER"
        if not str(row.get("commentaire", "")).strip():
            fallback_comment = str(fallback.get("commentaire", "")).strip()
            if fallback_comment:
                row["commentaire"] = fallback_comment
        merged.append(row)
    return merged


def _row_richness_score(row: dict[str, object]) -> int:
    score = 0
    if str(row.get("poste", "")).strip():
        score += 1
    if str(row.get("section", "")).strip() or str(row.get("sous_section", "")).strip():
        score += 1
    if str(row.get("commentaire", "")).strip():
        score += 1
    if str(row.get("source", "")).strip():
        score += 1
    if _has_meaningful_budget_amount(row):
        score += 3
    return score


def _prefer_richer_budget_rows(
    primary_rows: list[dict[str, object]],
    fallback_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not primary_rows:
        return [dict(row) for row in fallback_rows]
    if not fallback_rows:
        return [dict(row) for row in primary_rows]

    primary_meaningful = sum(1 for row in primary_rows if _has_meaningful_budget_amount(row))
    fallback_meaningful = sum(1 for row in fallback_rows if _has_meaningful_budget_amount(row))

    if primary_meaningful == 0 and fallback_meaningful > 0:
        return _merge_budget_rows(fallback_rows, primary_rows)

    merged: list[dict[str, object]] = []
    max_len = max(len(primary_rows), len(fallback_rows))
    for index in range(max_len):
        primary = primary_rows[index] if index < len(primary_rows) and isinstance(primary_rows[index], dict) else {}
        fallback = fallback_rows[index] if index < len(fallback_rows) and isinstance(fallback_rows[index], dict) else {}
        chosen = primary if _row_richness_score(primary) >= _row_richness_score(fallback) else fallback
        other = fallback if chosen is primary else primary
        row = dict(other)
        row.update(chosen)
        if not str(row.get("montant_previsionnel", "")).strip():
            row["montant_previsionnel"] = "A_COMPLETER"
        merged.append(row)
    return merged


def _normalize_budget_payload(payload: dict[str, object], fallback_structured: dict[str, object]) -> dict[str, object]:
    payload = _extract_budget_root(payload)
    charges = _normalize_budget_rows(payload.get("charges", []))
    produits = _normalize_budget_rows(payload.get("produits", []))
    budget_previsionnel = payload.get("budget_previsionnel", {})
    if not charges and isinstance(budget_previsionnel, dict):
        charges = _normalize_budget_group_dict(budget_previsionnel.get("charges", {}), kind="charge")
    if not produits:
        produits = _normalize_budget_group_dict(payload.get("produits", {}), kind="produit")

    if not charges:
        section_rows = []
        for section in payload.get("sections_charges", []):
            if not isinstance(section, dict):
                continue
            section_name = str(section.get("section", "")).strip()
            for line in section.get("lignes", []):
                if not isinstance(line, dict):
                    continue
                section_rows.append(
                    {
                        "poste": str(line.get("poste", "")).strip() or section_name,
                        "montant_previsionnel": str(line.get("montant_total", "")).strip(),
                        "commentaire": str(line.get("commentaire", "")).strip()
                        or str(line.get("description", "")).strip(),
                    }
                )
        charges = _normalize_budget_rows(section_rows)

    sections = payload.get("sections", {})
    if not charges and isinstance(sections, dict):
        charges = _normalize_budget_rows(_flatten_budget_section(sections.get("charges", {}), kind="charge"))

    if not produits:
        section_rows = []
        for section in payload.get("sections_produits", []):
            if not isinstance(section, dict):
                continue
            section_name = str(section.get("section", "")).strip()
            for line in section.get("lignes", []):
                if not isinstance(line, dict):
                    continue
                section_rows.append(
                    {
                        "poste": str(line.get("financeur_ou_source", "")).strip() or section_name,
                        "montant_previsionnel": str(line.get("montant", "")).strip(),
                        "commentaire": str(line.get("commentaire", "")).strip()
                        or str(line.get("description", "")).strip(),
                    }
                )
        produits = _normalize_budget_rows(section_rows)

    if not produits and isinstance(sections, dict):
        produits = _normalize_budget_rows(_flatten_budget_section(sections.get("produits", {}), kind="produit"))

    if not charges and not produits:
        return fallback_structured

    notes = _normalize_budget_notes(payload)
    metadonnees = payload.get("metadonnees", {})
    if isinstance(metadonnees, dict):
        notes.extend(_dedup_strings(_coerce_string_list(metadonnees.get("points_bloquants", []))))
    totaux = payload.get("totaux", {}) if isinstance(payload.get("totaux", {}), dict) else {}
    if not totaux and isinstance(budget_previsionnel, dict):
        totaux = {
            "total_charges": str(budget_previsionnel.get("total_charges", "")).strip(),
            "total_produits": str(payload.get("total_produits", "")).strip(),
            "equilibre_budgetaire": "",
        }
    if not totaux and isinstance(sections, dict):
        charges_section = sections.get("charges", {})
        produits_section = sections.get("produits", {})
        if isinstance(charges_section, dict) or isinstance(produits_section, dict):
            totaux = {
                "total_charges": str(charges_section.get("total_charges", "")).strip() if isinstance(charges_section, dict) else "",
                "total_produits": str(produits_section.get("total_produits", "")).strip() if isinstance(produits_section, dict) else "",
                "equilibre_budgetaire": str(payload.get("statut", "")).strip(),
            }
    if totaux:
        charges_total = str(
            totaux.get("charges", totaux.get("total_charges", "A_COMPLETER"))
        ).strip() or "A_COMPLETER"
        produits_total = str(
            totaux.get("produits", totaux.get("total_produits", "A_COMPLETER"))
        ).strip() or "A_COMPLETER"
        equilibre = str(
            totaux.get("equilibre", totaux.get("equilibre_budgetaire", "A_CONFIRMER"))
        ).strip() or "A_CONFIRMER"
        notes.append(
            "Totaux : charges="
            f"{charges_total} | "
            f"produits={produits_total} | "
            f"equilibre={equilibre}"
        )

    if isinstance(payload.get("analyse_budgetaire"), dict):
        analyse = payload.get("analyse_budgetaire", {})
        notes.extend(_dedup_strings([str(item) for item in analyse.get("alertes", [])]))
        notes.extend(_dedup_strings([str(item) for item in analyse.get("incoherences_detectees", [])]))

    fallback_charges = list(fallback_structured.get("charges", []))
    fallback_produits = list(fallback_structured.get("produits", []))
    charges = _enrich_budget_amounts(_prefer_richer_budget_rows(charges, fallback_charges))
    produits = _enrich_budget_amounts(_prefer_richer_budget_rows(produits, fallback_produits))

    if not any(_has_meaningful_budget_amount(row) for row in charges + produits):
        notes.append(
            "Le budget agent ne fournit pas encore de montants exploitables. "
            "La trame conserve donc la meilleure structure disponible pour completer manuellement."
        )

    financeur_principal = payload.get("financeur_principal", {})
    if not isinstance(financeur_principal, dict) or not financeur_principal:
        financeur_principal = (
            {"nom": str(metadonnees.get("financeur_detecte", "")).strip()}
            if isinstance(metadonnees, dict) and str(metadonnees.get("financeur_detecte", "")).strip()
            else {}
        )

    structure_porteuse = payload.get("structure_porteuse", {})
    if not isinstance(structure_porteuse, dict) or not structure_porteuse:
        structure_porteuse = (
            {
                "nom": str(metadonnees.get("porteur_projet", "")).strip(),
                "forme_juridique": str(metadonnees.get("forme_juridique", "")).strip(),
                "territoire": str(metadonnees.get("territoire", "")).strip(),
            }
            if isinstance(metadonnees, dict)
            and (
                str(metadonnees.get("porteur_projet", "")).strip()
                or str(metadonnees.get("forme_juridique", "")).strip()
                or str(metadonnees.get("territoire", "")).strip()
            )
            else {}
        )

    return {
        "titre": str(payload.get("titre_document", payload.get("titre", fallback_structured.get("titre", "Budget previsionnel")))).strip()
        or fallback_structured.get("titre", "Budget previsionnel"),
        "colonnes": list(payload.get("colonnes", fallback_structured.get("colonnes", []))),
        "charges": charges,
        "produits": produits,
        "notes": notes,
        "metadata": {
            "description": str(payload.get("description", "")).strip(),
            "synthese_financements": str(payload.get("synthese_financements", "")).strip(),
            "statut": str(payload.get("statut", "")).strip(),
            "periode": payload.get("periode", {}) if isinstance(payload.get("periode", {}), dict) else {},
            "financeur_principal": financeur_principal,
            "structure_porteuse": structure_porteuse,
            "metadonnees": payload.get("metadonnees", {}) if isinstance(payload.get("metadonnees", {}), dict) else {},
        },
        "points_a_completer": _dedup_strings(_coerce_string_list(payload.get("points_a_completer", []))),
    }


def resolve_wf4_outputs(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
    prefer_llm: bool = True,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    fallback_outputs = build_wf4_outputs(wf2b_structured, wf3_analysis)
    meta = {"engine": "heuristique_locale", "fallback_used": False, "parts": {}}
    if not prefer_llm:
        return fallback_outputs, meta

    wf4_outputs = deepcopy(fallback_outputs)
    llm_parts_ok = 0
    active_provider = ""
    active_model = ""

    wf4a_result = request_wf4a_llm_payload(
        wf2a_structured,
        wf2b_structured,
        wf3_analysis,
        provider_override=llm_provider,
        model_override=llm_model,
    )
    if wf4a_result.get("provider"):
        active_provider = str(wf4a_result.get("provider", ""))
        active_model = str(wf4a_result.get("model", ""))
    if wf4a_result.get("ok") and isinstance(wf4a_result.get("payload"), dict):
        presentation = _normalize_presentation_payload(
            wf4a_result["payload"],
            fallback_outputs,
        )
        wf4_outputs["livrables"]["presentation_projet"] = presentation
        if presentation.get("resume_executif"):
            wf4_outputs["rapport_structured"]["resume_executif"] = presentation["resume_executif"]
        llm_parts_ok += 1
        meta["parts"]["presentation_projet"] = "llm"
    else:
        meta["parts"]["presentation_projet"] = f"fallback:{wf4a_result.get('error', 'llm_error')}"

    presentation_payload = wf4_outputs["livrables"].get("presentation_projet", {})
    section_results = []
    if isinstance(presentation_payload, dict):
        current_sections = list(presentation_payload.get("sections", []))
        enriched_sections = []
        llm_section_attempts = 0
        for index, section in enumerate(current_sections):
            if not isinstance(section, dict):
                enriched_sections.append(section)
                continue
            if index >= 10:
                enriched_sections.append(section)
                continue
            section_body = str(section.get("contenu", "")).strip()
            if not _should_enrich_presentation_section(section, llm_section_attempts):
                enriched_sections.append(section)
                continue

            section_request = {
                "titre": str(section.get("section", "")).strip(),
                "objectif_section": str(section.get("section", "")).strip(),
                "contenu_initial": section_body,
                "statut_initial": str(section.get("statut", "")).strip().lower(),
                "section_type": infer_presentation_section_type(str(section.get("section", "")).strip()),
                "consignes_section": get_section_guidance(
                    infer_presentation_section_type(str(section.get("section", "")).strip())
                ),
            }
            llm_section_attempts += 1
            section_result = request_wf4a_section_payload(
                wf2a_structured,
                wf2b_structured,
                wf3_analysis,
                section_request,
                provider_override=llm_provider,
                model_override=llm_model,
            )
            section_results.append(section_result)
            if section_result.get("ok") and isinstance(section_result.get("payload"), dict):
                enriched_sections.append(_normalize_single_presentation_section(section_result["payload"], section))
            else:
                enriched_sections.append(section)

        if enriched_sections:
            presentation_payload["sections"] = enriched_sections
            presentation_payload["markdown"] = build_project_presentation_markdown(enriched_sections)
            llm_section_count = sum(
                1 for result in section_results if result.get("ok") and isinstance(result.get("payload"), dict)
            )
            if llm_section_count:
                meta["parts"]["presentation_sections"] = f"llm:{llm_section_count}/{len(section_results)}"
            elif section_results:
                first_error = next(
                    (str(result.get("error", "llm_error")) for result in section_results if not result.get("ok")),
                    "llm_error",
                )
                meta["parts"]["presentation_sections"] = f"fallback:{first_error}"

    wf4b_result = request_wf4b_llm_payload(
        wf2a_structured,
        wf2b_structured,
        wf3_analysis,
        provider_override=llm_provider,
        model_override=llm_model,
    )
    if not active_provider and wf4b_result.get("provider"):
        active_provider = str(wf4b_result.get("provider", ""))
        active_model = str(wf4b_result.get("model", ""))
    if wf4b_result.get("ok") and isinstance(wf4b_result.get("payload"), dict):
        budget_structured = _normalize_budget_payload(
            wf4b_result["payload"],
            fallback_outputs["livrables"]["budget_projet"]["structured"],
        )
        wf4_outputs["livrables"]["budget_projet"] = {
            "structured": budget_structured,
            "markdown": build_project_budget_markdown(budget_structured),
        }
        llm_parts_ok += 1
        if wf4b_result.get("agent_id"):
            meta["parts"]["budget_projet"] = f"llm_agent:{wf4b_result.get('agent_id')}"
        else:
            meta["parts"]["budget_projet"] = "llm"
    else:
        meta["parts"]["budget_projet"] = f"fallback:{wf4b_result.get('error', 'llm_error')}"

    wf4c_result = request_wf4c_llm_payload(
        wf2a_structured,
        wf2b_structured,
        wf3_analysis,
        provider_override=llm_provider,
        model_override=llm_model,
    )
    if not active_provider and wf4c_result.get("provider"):
        active_provider = str(wf4c_result.get("provider", ""))
        active_model = str(wf4c_result.get("model", ""))
    if wf4c_result.get("ok") and isinstance(wf4c_result.get("payload"), dict):
        payload = wf4c_result["payload"]
        required = bool(payload.get("required"))
        if required:
            structure_structured = _normalize_budget_payload(
                payload,
                fallback_outputs["livrables"]["budget_structure"]["structured"] or {},
            )
            wf4_outputs["livrables"]["budget_structure"] = {
                "required": True,
                "structured": structure_structured,
                "markdown": build_project_budget_markdown(structure_structured),
                "niveau_certitude": str(payload.get("niveau_certitude", "moyen")).strip(),
                "justification_requirement": str(payload.get("justification_requirement", "")).strip(),
            }
        else:
            wf4_outputs["livrables"]["budget_structure"] = {
                "required": False,
                "structured": None,
                "markdown": "",
                "niveau_certitude": str(payload.get("niveau_certitude", "moyen")).strip(),
                "justification_requirement": str(payload.get("justification_requirement", "")).strip(),
            }
        llm_parts_ok += 1
        meta["parts"]["budget_structure"] = "llm"
    else:
        meta["parts"]["budget_structure"] = f"fallback:{wf4c_result.get('error', 'llm_error')}"

    checklist = list(build_completion_checklist(wf3_analysis, wf2b_structured))
    presentation_extra = wf4_outputs["livrables"]["presentation_projet"]
    if isinstance(presentation_extra, dict):
        for item in presentation_extra.get("donnees_manquantes", []):
            checklist.append({"bloc": "presentation", "element": str(item), "action": "Completer cette information", "source": ""})
        for item in presentation_extra.get("pieces_ou_annexes_a_prevoir", []):
            checklist.append({"bloc": "pieces", "element": str(item), "action": "Prevoir cette piece ou annexe", "source": ""})

    budget_project_structured = wf4_outputs["livrables"]["budget_projet"].get("structured", {})
    for item in budget_project_structured.get("points_a_completer", []):
        checklist.append({"bloc": "budget_projet", "element": str(item), "action": "Completer ou confirmer ce poste budgetaire", "source": ""})

    budget_structure_payload = wf4_outputs["livrables"]["budget_structure"]
    if isinstance(budget_structure_payload, dict):
        structured = budget_structure_payload.get("structured", {}) or {}
        for item in structured.get("points_a_completer", []):
            checklist.append({"bloc": "budget_structure", "element": str(item), "action": "Completer ou confirmer ce poste structure", "source": ""})
        justification = str(budget_structure_payload.get("justification_requirement", "")).strip()
        if justification:
            checklist.append({"bloc": "budget_structure", "element": "Justification du besoin", "action": justification, "source": ""})

    deduped_checklist = []
    seen = set()
    for item in checklist:
        key = (str(item.get("bloc", "")), str(item.get("element", "")), str(item.get("action", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped_checklist.append(item)
    wf4_outputs["livrables"]["points_a_completer"] = deduped_checklist[:18]

    if llm_parts_ok:
        meta.update(
            {
                "engine": "llm_direct_python",
                "provider": active_provider,
                "model": active_model,
                "fallback_used": llm_parts_ok < 3,
                "budget_project_agent_id": wf4b_result.get("agent_id", ""),
                "wf4a_usage": wf4a_result.get("usage", {}),
                "wf4b_usage": wf4b_result.get("usage", {}),
                "wf4c_usage": wf4c_result.get("usage", {}),
            }
        )
        return wf4_outputs, meta

    meta.update(
        {
            "fallback_used": True,
            "llm_error": "wf4_llm_inexploitable",
            "provider": active_provider,
            "model": active_model,
            "budget_project_agent_id": wf4b_result.get("agent_id", ""),
            "wf4a_usage": wf4a_result.get("usage", {}),
            "wf4b_usage": wf4b_result.get("usage", {}),
            "wf4c_usage": wf4c_result.get("usage", {}),
        }
    )
    return fallback_outputs, meta


def resolve_pipeline_outputs(
    dossier_files,
    client_files,
    project_files,
    completed_bridge: dict[str, str],
    global_context_bridge: dict[str, str] | None = None,
    prefer_llm: bool = True,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> dict[str, object]:
    wf2a_structured, wf2a_meta = resolve_wf2a_structured(
        dossier_files,
        prefer_llm=prefer_llm,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    wf2b_structured, wf2b_meta = resolve_wf2b_structured(
        client_files,
        project_files,
        prefer_llm=prefer_llm,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )

    completed_wf2a, completed_wf2b = merge_completed_bridge_into_wf2(
        wf2a_structured,
        wf2b_structured,
        completed_bridge,
    )
    wf3_analysis, wf3_meta = resolve_wf3_analysis(
        completed_wf2a,
        completed_wf2b,
        global_context_bridge=global_context_bridge,
        prefer_llm=prefer_llm,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    wf4_outputs, wf4_meta = resolve_wf4_outputs(
        completed_wf2a,
        completed_wf2b,
        wf3_analysis,
        prefer_llm=prefer_llm,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )

    return {
        "wf2a": completed_wf2a,
        "wf2b": completed_wf2b,
        "wf3": wf3_analysis,
        "wf4": wf4_outputs,
        "execution": {
            "prefer_llm": prefer_llm,
            "llm_selection": {
                "provider": llm_provider or "",
                "model": llm_model or "",
            },
            "wf2a": wf2a_meta,
            "wf2b": wf2b_meta,
            "wf3": wf3_meta,
            "wf4": wf4_meta,
        },
        "bridge": build_bridge_from_wf2(completed_wf2a, completed_wf2b),
    }
