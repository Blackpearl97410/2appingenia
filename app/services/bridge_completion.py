from __future__ import annotations

from copy import deepcopy


def _manual_field_value(value: str) -> dict[str, object]:
    return {
        "value": value,
        "source_document": "saisie_manuelle",
        "source_texte": value,
        "niveau_confiance": "moyen",
        "necessite_validation": True,
        "mode_extraction": "completion_manuelle",
    }


def _bridge_value_is_present(value: str, missing_values: set[str]) -> bool:
    return bool(value) and value not in missing_values


def merge_completed_bridge_into_wf2(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    completed_bridge: dict[str, str],
) -> tuple[dict[str, object], dict[str, object]]:
    merged_wf2a = deepcopy(wf2a_structured)
    merged_wf2b = deepcopy(wf2b_structured)

    profil_client = merged_wf2b.setdefault("profil_client", {})
    donnees_projet = merged_wf2b.setdefault("donnees_projet", {})
    criteres = merged_wf2a.setdefault("criteres", [])
    metadata = merged_wf2a.setdefault("metadata", {})

    if _bridge_value_is_present(completed_bridge.get("type_structure_client", ""), {"", "Non detectee"}):
        profil_client["forme_juridique"] = _manual_field_value(completed_bridge["type_structure_client"])

    if _bridge_value_is_present(completed_bridge.get("identite_client", ""), {"", "Aucune"}):
        if not str(profil_client.get("nom_structure", {}).get("value", "")).strip() or profil_client.get("nom_structure", {}).get("value") == "Non detecte":
            profil_client["nom_structure"] = _manual_field_value(completed_bridge["identite_client"])
        profil_client["activites"] = [_manual_field_value(completed_bridge["identite_client"])]

    if _bridge_value_is_present(completed_bridge.get("montant_projet", ""), {"", "Non detecte"}):
        donnees_projet["montant_detecte"] = _manual_field_value(completed_bridge["montant_projet"])

    if _bridge_value_is_present(completed_bridge.get("dates_projet", ""), {"", "Aucune"}):
        donnees_projet["dates_detectees"] = [_manual_field_value(completed_bridge["dates_projet"])]

    if _bridge_value_is_present(completed_bridge.get("elements_projet", ""), {"", "Aucun"}):
        donnees_projet["elements_detectes"] = [_manual_field_value(completed_bridge["elements_projet"])]

    def add_manual_criterion(
        criterion_id: str,
        categories: tuple[str, str, str],
        bridge_key: str,
        missing_values: set[str],
    ) -> None:
        value = completed_bridge.get(bridge_key, "")
        if not _bridge_value_is_present(value, missing_values):
            return
        label, category, domain = categories
        if any(str(item.get("libelle", "")).lower() == label.lower() for item in criteres):
            return
        criteres.append(
            {
                "id_local": criterion_id,
                "categorie": category,
                "domaine": domain,
                "libelle": label,
                "detail": value,
                "source_document": "saisie_manuelle",
                "source_texte": value,
                "source_document_id": None,
                "est_piece_exigee": "piece" in value.lower(),
                "est_critere_eliminatoire": category == "bloquant",
                "niveau_confiance": "moyen",
                "necessite_validation": True,
                "mode_extraction": "completion_manuelle",
            }
        )

    add_manual_criterion(
        "manual_structure_requirement",
        ("Type de structure eligible", "obligatoire", "juridique"),
        "type_structure_requise",
        {"", "A verifier"},
    )
    add_manual_criterion(
        "manual_deadline_requirement",
        ("Date limite ou calendrier impose", "obligatoire", "administratif"),
        "date_limite_dossier",
        {"", "Aucune"},
    )
    add_manual_criterion(
        "manual_budget_requirement",
        ("Montant, plafond ou enveloppe du dispositif", "souhaitable", "financier"),
        "montant_dossier",
        {"", "Aucun"},
    )
    add_manual_criterion(
        "manual_conditions_requirement",
        ("Conditions d'eligibilite et pieces attendues", "obligatoire", "administratif"),
        "conditions_dossier",
        {"", "Aucune"},
    )

    if _bridge_value_is_present(completed_bridge.get("date_limite_dossier", ""), {"", "Aucune"}):
        metadata["date_limite_detectee"] = completed_bridge["date_limite_dossier"]
    if _bridge_value_is_present(completed_bridge.get("montant_dossier", ""), {"", "Aucun"}):
        metadata["montant_max_detecte"] = completed_bridge["montant_dossier"]

    metadata["nb_criteres_extraits"] = len(criteres)

    return merged_wf2a, merged_wf2b
