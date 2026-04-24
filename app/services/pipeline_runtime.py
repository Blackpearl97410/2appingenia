from __future__ import annotations

from copy import deepcopy

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
from app.services.wf4 import build_wf4_outputs


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
            "activites": _normalize_field_list("activite", profil_client_raw.get("activites", [])),
        },
        "donnees_projet": {
            "titre_projet": _normalize_field_dict("titre_projet", donnees_projet_raw.get("titre_projet", {})),
            "montant_detecte": _normalize_field_dict("montant_detecte", donnees_projet_raw.get("montant_detecte", {})),
            "dates_detectees": _normalize_field_list("date_projet", donnees_projet_raw.get("dates_detectees", [])),
            "elements_detectes": _normalize_field_list("element_projet", donnees_projet_raw.get("elements_detectes", [])),
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


def resolve_wf2a_structured(dossier_files, prefer_llm: bool = True) -> tuple[dict[str, object], dict[str, object]]:
    fallback = extract_wf2a_structured(dossier_files)
    meta = {"engine": "heuristique_locale", "fallback_used": False}
    if not prefer_llm or not dossier_files:
        return fallback, meta

    llm_result = request_wf2a_llm_payload(dossier_files)
    if not llm_result.get("ok") or not isinstance(llm_result.get("payload"), dict):
        meta.update({"fallback_used": True, "llm_error": llm_result.get("error", "llm_error")})
        return fallback, meta

    structured = normalize_wf2a_llm_payload(llm_result["payload"], fallback)
    meta.update({
        "engine": "llm_direct_python",
        "model": llm_result.get("model", ""),
        "usage": llm_result.get("usage", {}),
        "fallback_used": False,
    })
    return structured, meta


def resolve_wf2b_structured(client_files, project_files, prefer_llm: bool = True) -> tuple[dict[str, object], dict[str, object]]:
    fallback = extract_wf2b_structured(client_files, project_files)
    meta = {"engine": "heuristique_locale", "fallback_used": False}
    if not prefer_llm or (not client_files and not project_files):
        return fallback, meta

    llm_result = request_wf2b_llm_payload(client_files, project_files)
    if not llm_result.get("ok") or not isinstance(llm_result.get("payload"), dict):
        meta.update({"fallback_used": True, "llm_error": llm_result.get("error", "llm_error")})
        return fallback, meta

    structured = normalize_wf2b_llm_payload(llm_result["payload"], fallback)
    meta.update({
        "engine": "llm_direct_python",
        "model": llm_result.get("model", ""),
        "usage": llm_result.get("usage", {}),
        "fallback_used": False,
    })
    return structured, meta


def resolve_wf3_analysis(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    global_context_bridge: dict[str, str] | None = None,
    prefer_llm: bool = True,
) -> tuple[dict[str, object], dict[str, object]]:
    fallback = build_wf3_analysis(wf2a_structured, wf2b_structured, global_context_bridge)
    meta = {"engine": "heuristique_locale", "fallback_used": False}
    if not prefer_llm:
        return fallback, meta

    llm_result = request_wf3_llm_payload(wf2a_structured, wf2b_structured, global_context_bridge)
    if not llm_result.get("ok") or not isinstance(llm_result.get("payload"), dict):
        meta.update({"fallback_used": True, "llm_error": llm_result.get("error", "llm_error")})
        return fallback, meta

    structured = normalize_wf3_llm_payload(llm_result["payload"], fallback)
    meta.update({
        "engine": "llm_direct_python",
        "model": llm_result.get("model", ""),
        "usage": llm_result.get("usage", {}),
        "fallback_used": False,
    })
    return structured, meta


def resolve_pipeline_outputs(
    dossier_files,
    client_files,
    project_files,
    completed_bridge: dict[str, str],
    global_context_bridge: dict[str, str] | None = None,
    prefer_llm: bool = True,
) -> dict[str, object]:
    wf2a_structured, wf2a_meta = resolve_wf2a_structured(dossier_files, prefer_llm=prefer_llm)
    wf2b_structured, wf2b_meta = resolve_wf2b_structured(client_files, project_files, prefer_llm=prefer_llm)

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
    )
    wf4_outputs = build_wf4_outputs(completed_wf2b, wf3_analysis)

    return {
        "wf2a": completed_wf2a,
        "wf2b": completed_wf2b,
        "wf3": wf3_analysis,
        "wf4": wf4_outputs,
        "execution": {
            "prefer_llm": prefer_llm,
            "wf2a": wf2a_meta,
            "wf2b": wf2b_meta,
            "wf3": wf3_meta,
        },
        "bridge": build_bridge_from_wf2(completed_wf2a, completed_wf2b),
    }
