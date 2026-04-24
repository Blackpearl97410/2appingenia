from __future__ import annotations

from typing import Any


def _collect_items_by_status(results: list[dict[str, object]], statuses: set[str]) -> list[dict[str, object]]:
    return [result for result in results if str(result.get("statut")) in statuses]


def _dedup(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if str(item).strip()))


def _field_value(field: dict[str, Any] | None, default: str = "A completer") -> str:
    if not isinstance(field, dict):
        return default
    value = str(field.get("value", "")).strip()
    if not value or value.lower() == "non detecte" or value.lower() == "non detectee":
        return default
    return value


def _field_source(field: dict[str, Any] | None) -> str:
    if not isinstance(field, dict):
        return ""
    return str(field.get("source_document", "")).strip()


def _join_field_values(items: list[dict[str, Any]] | None, default: str = "A completer") -> str:
    if not items:
        return default
    values = _dedup([str(item.get("value", "")).strip() for item in items if str(item.get("value", "")).strip()])
    return " | ".join(values) if values else default


def _infer_call_requirements(wf3_analysis: dict[str, object]) -> dict[str, Any]:
    results = list(wf3_analysis.get("resultats_criteres", []))
    combined = " ".join(
        f"{result.get('libelle', '')} {result.get('detail', '')} {result.get('action_requise', '')} {result.get('justification', '')}"
        for result in results
    ).lower()
    return {
        "budget_required": any(keyword in combined for keyword in {"budget", "financement", "cofinancement", "plan de financement"}),
        "planning_required": any(keyword in combined for keyword in {"planning", "calendrier", "chronogramme"}),
        "pieces_required": any(keyword in combined for keyword in {"piece", "pièce", "annexe", "depot", "dépôt"}),
        "structure_budget_required": any(
            keyword in combined
            for keyword in {
                "budget structure",
                "budget de structure",
                "compte de resultat",
                "compte de résultat",
                "previsionnel 2025",
                "prévisionnel 2025",
                "structure porteuse",
                "charges de structure",
            }
        ),
    }


def build_report_structured(wf3_analysis: dict[str, object]) -> dict[str, object]:
    results = list(wf3_analysis.get("resultats_criteres", []))
    valid_items = _collect_items_by_status(results, {"valide"})
    confirm_items = _collect_items_by_status(results, {"a_confirmer"})
    missing_items = _collect_items_by_status(results, {"manquant", "non_valide"})

    return {
        "type_rapport": "preremplissage",
        "format_export": "markdown",
        "resume_executif": wf3_analysis.get("resume_executif", ""),
        "statut_eligibilite": wf3_analysis.get("statut_eligibilite", "a confirmer"),
        "score_global": wf3_analysis.get("score_global", 0),
        "niveau_confiance": wf3_analysis.get("niveau_confiance", "moyen"),
        "points_valides": _dedup([str(item.get("libelle", "")) for item in valid_items[:8]]),
        "points_a_confirmer": _dedup([str(item.get("libelle", "")) for item in confirm_items[:8]]),
        "points_bloquants": _dedup([str(item.get("libelle", "")) for item in missing_items[:8]]),
        "pieces_manquantes": _dedup([
            str(item.get("action_requise", ""))
            for item in missing_items[:8]
            if "piece" in str(item.get("libelle", "")).lower() or "piece" in str(item.get("action_requise", "")).lower()
        ]),
        "recommandations": _dedup([str(item.get("action_requise", "")) for item in missing_items[:10]]),
    }


def build_report_markdown(wf3_analysis: dict[str, object], report_structured: dict[str, object]) -> str:
    lines = [
        "# Rapport de pre-analyse",
        "",
        f"**Statut** : {report_structured.get('statut_eligibilite', 'a confirmer')}",
        f"**Score global** : {report_structured.get('score_global', 0)}/100",
        f"**Niveau de confiance** : {report_structured.get('niveau_confiance', 'moyen')}",
        "",
        "## Resume executif",
        str(report_structured.get("resume_executif", "")),
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

    return [
        {
            "onglet": "Structure",
            "nom_champ": "Nom de la structure",
            "valeur": _field_value(profil_client.get("nom_structure")),
            "source": _field_source(profil_client.get("nom_structure")),
        },
        {
            "onglet": "Structure",
            "nom_champ": "Forme juridique",
            "valeur": _field_value(profil_client.get("forme_juridique")),
            "source": _field_source(profil_client.get("forme_juridique")),
        },
        {
            "onglet": "Structure",
            "nom_champ": "SIRET",
            "valeur": _field_value(profil_client.get("siret")),
            "source": _field_source(profil_client.get("siret")),
        },
        {
            "onglet": "Contact",
            "nom_champ": "Email",
            "valeur": _field_value(profil_client.get("email")),
            "source": _field_source(profil_client.get("email")),
        },
        {
            "onglet": "Contact",
            "nom_champ": "Telephone",
            "valeur": _field_value(profil_client.get("telephone")),
            "source": _field_source(profil_client.get("telephone")),
        },
        {
            "onglet": "Projet",
            "nom_champ": "Titre du projet",
            "valeur": _field_value(donnees_projet.get("titre_projet")),
            "source": _field_source(donnees_projet.get("titre_projet")),
        },
        {
            "onglet": "Projet",
            "nom_champ": "Montant du projet",
            "valeur": _field_value(donnees_projet.get("montant_detecte")),
            "source": _field_source(donnees_projet.get("montant_detecte")),
        },
        {
            "onglet": "Projet",
            "nom_champ": "Dates du projet",
            "valeur": _join_field_values(donnees_projet.get("dates_detectees", [])),
            "source": _field_source(donnees_projet.get("titre_projet")),
        },
        {
            "onglet": "Projet",
            "nom_champ": "Elements du projet",
            "valeur": _join_field_values(donnees_projet.get("elements_detectes", [])),
            "source": _field_source(donnees_projet.get("titre_projet")),
        },
    ]


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
            "nom": "Aides territoriales et associatives",
            "tags": ["association", "territorial", "public", "beneficiaire"],
            "justification": "Pertinent pour des projets associatifs ancrés localement ou a impact territorial.",
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


def build_project_presentation_sections(wf2b_structured: dict[str, object], wf3_analysis: dict[str, object]) -> list[dict[str, str]]:
    profil_client = wf2b_structured.get("profil_client", {})
    donnees_projet = wf2b_structured.get("donnees_projet", {})
    requirements = _infer_call_requirements(wf3_analysis)
    missing_actions = _dedup([
        str(item.get("action_requise", ""))
        for item in wf3_analysis.get("resultats_criteres", [])
        if str(item.get("statut")) in {"a_confirmer", "manquant", "non_valide"}
    ])

    structure_name = _field_value(profil_client.get("nom_structure"))
    legal_form = _field_value(profil_client.get("forme_juridique"))
    activities = _join_field_values(profil_client.get("activites", []))
    title = _field_value(donnees_projet.get("titre_projet"))
    project_elements = _join_field_values(donnees_projet.get("elements_detectes", []))
    project_dates = _join_field_values(donnees_projet.get("dates_detectees", []))
    project_amount = _field_value(donnees_projet.get("montant_detecte"))

    sections = [
        {
            "section": "1. Resume du projet",
            "statut": "partiel" if title != "A completer" else "a_completer",
            "contenu": (
                f"Projet : {title}\n"
                f"Resume initial : {wf3_analysis.get('resume_executif', 'A completer')}\n"
                "A retravailler dans la forme attendue par l'appel a projet."
            ),
        },
        {
            "section": "2. Presentation de la structure porteuse",
            "statut": "partiel" if structure_name != "A completer" else "a_completer",
            "contenu": (
                f"Structure : {structure_name}\n"
                f"Forme juridique : {legal_form}\n"
                f"Activites / experience : {activities}\n"
                "Completer avec l'historique, les references et la capacite a porter le projet."
            ),
        },
        {
            "section": "3. Description detaillee du projet",
            "statut": "partiel" if project_elements != "A completer" else "a_completer",
            "contenu": (
                f"Titre / intitule : {title}\n"
                f"Elements detectes : {project_elements}\n"
                "A transformer en texte redige : contexte, besoin, objectifs, actions prevues, livrables."
            ),
        },
        {
            "section": "4. Publics, territoire et beneficiaires",
            "statut": "a_completer",
            "contenu": (
                "Preciser les publics vises, le territoire concerne, le nombre de beneficiaires et l'impact attendu. "
                "Cette section doit reprendre les attendus explicites de l'appel a projet."
            ),
        },
        {
            "section": "5. Methodologie, calendrier et mise en oeuvre",
            "statut": "partiel" if requirements["planning_required"] or project_dates != "A completer" else "a_completer",
            "contenu": (
                f"Dates / jalons detectes : {project_dates}\n"
                "A structurer en phasage : preparation, mise en oeuvre, suivi, evaluation, livrables."
            ),
        },
        {
            "section": "6. Moyens mobilises et partenariats",
            "statut": "a_completer",
            "contenu": (
                "Decrire les moyens humains, techniques, eventuels prestataires et partenariats. "
                "Verifier les pieces exigees et les criteres techniques de l'appel."
            ),
        },
        {
            "section": "7. Budget et plan de financement",
            "statut": "partiel" if requirements["budget_required"] or project_amount != "A completer" else "a_completer",
            "contenu": (
                f"Montant detecte : {project_amount}\n"
                "Le budget doit etre ventile en charges et produits, conforme a la trame demandee."
            ),
        },
        {
            "section": "8. Pieces et points a completer",
            "statut": "a_completer" if missing_actions else "partiel",
            "contenu": " | ".join(missing_actions[:8]) if missing_actions else "Verifier les annexes et justificatifs demandes dans l'appel.",
        },
    ]
    return sections


def build_project_presentation_markdown(sections: list[dict[str, str]]) -> str:
    lines = ["# Trame de presentation du projet", ""]
    for section in sections:
        lines.append(f"## {section['section']}")
        lines.append(f"_Statut : {section['statut']}_")
        lines.append("")
        lines.append(section["contenu"])
        lines.append("")
    return "\n".join(lines)


def build_project_budget_template(wf2b_structured: dict[str, object], wf3_analysis: dict[str, object]) -> dict[str, Any]:
    donnees_projet = wf2b_structured.get("donnees_projet", {})
    amount = _field_value(donnees_projet.get("montant_detecte"))
    requirements = _infer_call_requirements(wf3_analysis)

    charges = [
        {"poste": "Charges de personnel affectees au projet", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Prestations externes / intervenants", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Communication / diffusion", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Deplacements / missions", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Location / materiel / technique", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Frais administratifs lies au projet", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Autres charges du projet", "montant_previsionnel": "", "commentaire": "A completer"},
    ]
    produits = [
        {"poste": "Subvention sollicitee", "montant_previsionnel": amount if amount != "A completer" else "", "commentaire": "Verifier si ce montant correspond bien a l'aide demandee"},
        {"poste": "Autofinancement", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Autres subventions publiques", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Partenariats / financements prives", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Recettes propres du projet", "montant_previsionnel": "", "commentaire": "A completer"},
        {"poste": "Autres produits", "montant_previsionnel": "", "commentaire": "A completer"},
    ]

    notes = [
        "Trame budgetaire a reprendre dans le format comptable demande par l'appel a projet.",
        "Verifier l'equilibre Charges = Produits.",
    ]
    if requirements["budget_required"]:
        notes.append("L'appel a projet mentionne des attentes budgetaires explicites.")

    return {
        "titre": "Budget previsionnel du projet",
        "colonnes": ["Charges", "Montant previsionnel", "Produits", "Montant previsionnel"],
        "charges": charges,
        "produits": produits,
        "notes": notes,
    }


def build_project_budget_markdown(budget: dict[str, Any]) -> str:
    lines = [
        f"# {budget.get('titre', 'Budget previsionnel du projet')}",
        "",
        "| Charges | Montant previsionnel | Produits | Montant previsionnel |",
        "| --- | ---: | --- | ---: |",
    ]

    charges = list(budget.get("charges", []))
    produits = list(budget.get("produits", []))
    max_len = max(len(charges), len(produits))
    for index in range(max_len):
        charge = charges[index] if index < len(charges) else {"poste": "", "montant_previsionnel": ""}
        produit = produits[index] if index < len(produits) else {"poste": "", "montant_previsionnel": ""}
        lines.append(
            f"| {charge.get('poste', '')} | {charge.get('montant_previsionnel', '')} | "
            f"{produit.get('poste', '')} | {produit.get('montant_previsionnel', '')} |"
        )

    lines.extend(["", "## Notes"])
    for note in budget.get("notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines)


def build_structure_budget_template(wf2b_structured: dict[str, object], wf3_analysis: dict[str, object]) -> dict[str, Any] | None:
    requirements = _infer_call_requirements(wf3_analysis)
    if not requirements["structure_budget_required"]:
        return None

    return {
        "titre": "Budget previsionnel de structure",
        "colonnes": ["Charges de structure", "Montant previsionnel", "Produits de structure", "Montant previsionnel"],
        "charges": [
            {"poste": "Personnel permanent", "montant_previsionnel": "", "commentaire": "A completer"},
            {"poste": "Charges sociales", "montant_previsionnel": "", "commentaire": "A completer"},
            {"poste": "Loyers / fluides / assurances", "montant_previsionnel": "", "commentaire": "A completer"},
            {"poste": "Fonctionnement general", "montant_previsionnel": "", "commentaire": "A completer"},
            {"poste": "Autres charges de structure", "montant_previsionnel": "", "commentaire": "A completer"},
        ],
        "produits": [
            {"poste": "Subventions de fonctionnement", "montant_previsionnel": "", "commentaire": "A completer"},
            {"poste": "Recettes propres", "montant_previsionnel": "", "commentaire": "A completer"},
            {"poste": "Prestations / ventes", "montant_previsionnel": "", "commentaire": "A completer"},
            {"poste": "Autres produits", "montant_previsionnel": "", "commentaire": "A completer"},
        ],
        "notes": [
            "A produire seulement si le financeur demande un budget de structure ou un previsionnel de la structure porteuse.",
            "Verifier la coherence entre budget projet et budget structure.",
        ],
    }


def build_completion_checklist(wf3_analysis: dict[str, object], wf2b_structured: dict[str, object]) -> list[dict[str, str]]:
    results = list(wf3_analysis.get("resultats_criteres", []))
    checklist: list[dict[str, str]] = []

    for item in results:
        if str(item.get("statut")) in {"a_confirmer", "manquant", "non_valide"}:
            checklist.append(
                {
                    "bloc": str(item.get("bloc_cible", "mixte")),
                    "element": str(item.get("libelle", "Element a completer")),
                    "action": str(item.get("action_requise", "A verifier")),
                    "source": str(item.get("source_document", "")),
                }
            )

    if not checklist:
        checklist.append(
            {
                "bloc": "mixte",
                "element": "Relecture finale",
                "action": "Verifier les formulations, les chiffres et la coherence du dossier final",
                "source": "",
            }
        )

    return checklist[:12]


def build_wf4_outputs(
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
) -> dict[str, object]:
    report_structured = build_report_structured(wf3_analysis)
    report_markdown = build_report_markdown(wf3_analysis, report_structured)
    prefill_fields = build_prefill_fields(wf2b_structured)
    suggestions = build_local_suggestions(wf2b_structured, wf3_analysis)

    project_presentation_sections = build_project_presentation_sections(wf2b_structured, wf3_analysis)
    project_presentation_markdown = build_project_presentation_markdown(project_presentation_sections)
    project_budget = build_project_budget_template(wf2b_structured, wf3_analysis)
    project_budget_markdown = build_project_budget_markdown(project_budget)
    structure_budget = build_structure_budget_template(wf2b_structured, wf3_analysis)
    structure_budget_markdown = build_project_budget_markdown(structure_budget) if structure_budget else ""
    completion_checklist = build_completion_checklist(wf3_analysis, wf2b_structured)

    return {
        "rapport_structured": report_structured,
        "rapport_markdown": report_markdown,
        "champs_preremplissage": prefill_fields,
        "suggestions": suggestions,
        "livrables": {
            "presentation_projet": {
                "sections": project_presentation_sections,
                "markdown": project_presentation_markdown,
            },
            "budget_projet": {
                "structured": project_budget,
                "markdown": project_budget_markdown,
            },
            "budget_structure": {
                "required": structure_budget is not None,
                "structured": structure_budget,
                "markdown": structure_budget_markdown,
            },
            "points_a_completer": completion_checklist,
        },
    }
