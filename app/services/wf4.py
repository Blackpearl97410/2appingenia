def _collect_items_by_status(results: list[dict[str, object]], statuses: set[str]) -> list[dict[str, object]]:
    return [result for result in results if str(result.get("statut")) in statuses]


def build_report_structured(wf3_analysis: dict[str, object]) -> dict[str, object]:
    results = list(wf3_analysis.get("resultats_criteres", []))
    valid_items = _collect_items_by_status(results, {"valide"})
    confirm_items = _collect_items_by_status(results, {"a_confirmer"})
    missing_items = _collect_items_by_status(results, {"manquant", "non_valide"})

    def _dedup(items: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in items if item))

    rapport = {
        "type_rapport": "complet",
        "format_export": "markdown",
        "resume_executif": wf3_analysis.get("resume_executif", ""),
        "statut_eligibilite": wf3_analysis.get("statut_eligibilite", "a confirmer"),
        "score_global": wf3_analysis.get("score_global", 0),
        "niveau_confiance": wf3_analysis.get("niveau_confiance", "moyen"),
        "points_valides": _dedup([item.get("libelle", "") for item in valid_items[:8]]),
        "points_a_confirmer": _dedup([item.get("libelle", "") for item in confirm_items[:8]]),
        "points_bloquants": _dedup([item.get("libelle", "") for item in missing_items[:8]]),
        "pieces_manquantes": _dedup([
            item.get("action_requise", "")
            for item in missing_items[:8]
            if "piece" in str(item.get("libelle", "")).lower() or "piece" in str(item.get("action_requise", "")).lower()
        ]),
        "recommandations": _dedup([item.get("action_requise", "") for item in missing_items[:10]]),
    }
    return rapport


def build_report_markdown(wf3_analysis: dict[str, object], report_structured: dict[str, object]) -> str:
    lines = [
        "# Rapport d'analyse local",
        "",
        f"**Statut** : {report_structured.get('statut_eligibilite', 'a confirmer')}",
        f"**Score global** : {report_structured.get('score_global', 0)}/100",
        f"**Niveau de confiance** : {report_structured.get('niveau_confiance', 'moyen')}",
        "",
        "## Resume executif",
        report_structured.get("resume_executif", ""),
        "",
        "## Points valides",
    ]

    for item in report_structured.get("points_valides", []):
        lines.append(f"- {item}")
    if not report_structured.get("points_valides"):
        lines.append("- Aucun point fortement valide pour l'instant")

    lines.extend(["", "## Points a confirmer"])
    for item in report_structured.get("points_a_confirmer", []):
        lines.append(f"- {item}")
    if not report_structured.get("points_a_confirmer"):
        lines.append("- Aucun point intermediaire a confirmer")

    lines.extend(["", "## Points bloquants ou manquants"])
    for item in report_structured.get("points_bloquants", []):
        lines.append(f"- {item}")
    if not report_structured.get("points_bloquants"):
        lines.append("- Aucun blocage majeur detecte")

    lines.extend(["", "## Recommandations d'action"])
    for item in report_structured.get("recommandations", []):
        lines.append(f"- {item}")
    if not report_structured.get("recommandations"):
        lines.append("- Aucune recommandation urgente")

    return "\n".join(lines)


def build_prefill_fields(wf2b_structured: dict[str, object]) -> list[dict[str, object]]:
    profil_client = wf2b_structured.get("profil_client", {})
    donnees_projet = wf2b_structured.get("donnees_projet", {})

    fields = [
        {
            "onglet": "Structure",
            "nom_champ": "Nom de la structure",
            "valeur": profil_client.get("nom_structure", {}).get("value", "Non detecte"),
            "source": profil_client.get("nom_structure", {}).get("source_document", ""),
        },
        {
            "onglet": "Structure",
            "nom_champ": "Forme juridique",
            "valeur": profil_client.get("forme_juridique", {}).get("value", "Non detectee"),
            "source": profil_client.get("forme_juridique", {}).get("source_document", ""),
        },
        {
            "onglet": "Structure",
            "nom_champ": "SIRET",
            "valeur": profil_client.get("siret", {}).get("value", "Non detecte"),
            "source": profil_client.get("siret", {}).get("source_document", ""),
        },
        {
            "onglet": "Contact",
            "nom_champ": "Email",
            "valeur": profil_client.get("email", {}).get("value", "Non detecte"),
            "source": profil_client.get("email", {}).get("source_document", ""),
        },
        {
            "onglet": "Contact",
            "nom_champ": "Telephone",
            "valeur": profil_client.get("telephone", {}).get("value", "Non detecte"),
            "source": profil_client.get("telephone", {}).get("source_document", ""),
        },
        {
            "onglet": "Projet",
            "nom_champ": "Titre du projet",
            "valeur": donnees_projet.get("titre_projet", {}).get("value", "Non detecte"),
            "source": donnees_projet.get("titre_projet", {}).get("source_document", ""),
        },
        {
            "onglet": "Projet",
            "nom_champ": "Montant du projet",
            "valeur": donnees_projet.get("montant_detecte", {}).get("value", "Non detecte"),
            "source": donnees_projet.get("montant_detecte", {}).get("source_document", ""),
        },
        {
            "onglet": "Projet",
            "nom_champ": "Dates du projet",
            "valeur": " | ".join(item.get("value", "") for item in donnees_projet.get("dates_detectees", [])) or "Aucune",
            "source": donnees_projet.get("titre_projet", {}).get("source_document", ""),
        },
        {
            "onglet": "Projet",
            "nom_champ": "Elements du projet",
            "valeur": " | ".join(item.get("value", "") for item in donnees_projet.get("elements_detectes", [])) or "Aucun",
            "source": donnees_projet.get("titre_projet", {}).get("source_document", ""),
        },
    ]
    return fields


def build_local_suggestions(wf2b_structured: dict[str, object], wf3_analysis: dict[str, object]) -> list[dict[str, object]]:
    profil_client = wf2b_structured.get("profil_client", {})
    donnees_projet = wf2b_structured.get("donnees_projet", {})
    activities = " ".join(item.get("value", "") for item in profil_client.get("activites", []))
    project_elements = " ".join(item.get("value", "") for item in donnees_projet.get("elements_detectes", []))
    search_space = f"{activities} {project_elements}".lower()

    catalog = [
        {
            "nom": "Aides innovation et transition numerique",
            "tags": ["numerique", "innovation", "digital", "audiovisuel"],
            "justification": "Pertinent pour des projets numeriques, de presence digitale ou d'outillage.",
        },
        {
            "nom": "Aides culture, musique et spectacle",
            "tags": ["culture", "musique", "spectacle", "production", "studio"],
            "justification": "Pertinent pour des structures culturelles, artistiques ou de production sonore.",
        },
        {
            "nom": "Aides formation et insertion",
            "tags": ["formation", "accompagnement", "atelier", "beneficiaire"],
            "justification": "Pertinent pour des actions de formation, d'accompagnement ou d'insertion.",
        },
        {
            "nom": "Aides territoriales et associatives",
            "tags": ["association", "territorial", "public", "beneficiaire"],
            "justification": "Pertinent pour des projets associatifs ancrés localement ou a impact territorial.",
        },
        {
            "nom": "Aides financement complementaire / cofinancement",
            "tags": ["budget", "financement", "cofinancement"],
            "justification": "Pertinent lorsque le projet a besoin d'un plan de financement plus solide.",
        },
    ]

    suggestions = []
    for entry in catalog:
        matches = sum(1 for tag in entry["tags"] if tag in search_space)
        if matches:
            suggestions.append(
                {
                    "nom": entry["nom"],
                    "score_pertinence": min(95, 45 + matches * 15),
                    "justification": entry["justification"],
                }
            )

    if not suggestions and wf3_analysis.get("score_global", 0) < 60:
        suggestions.append(
            {
                "nom": "Recherche d'alternatives a approfondir",
                "score_pertinence": 50,
                "justification": "Le score actuel est bas et une veille financeur plus large serait utile.",
            }
        )

    suggestions.sort(key=lambda item: item["score_pertinence"], reverse=True)
    return suggestions[:5]


def build_wf4_outputs(
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
) -> dict[str, object]:
    report_structured = build_report_structured(wf3_analysis)
    report_markdown = build_report_markdown(wf3_analysis, report_structured)
    prefill_fields = build_prefill_fields(wf2b_structured)
    suggestions = build_local_suggestions(wf2b_structured, wf3_analysis)

    return {
        "rapport_structured": report_structured,
        "rapport_markdown": report_markdown,
        "champs_preremplissage": prefill_fields,
        "suggestions": suggestions,
    }
