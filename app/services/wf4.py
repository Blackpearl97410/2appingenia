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


def _split_joined_values(value: str) -> list[str]:
    if not value or value == "A completer":
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def _joined_value_or_placeholder(value: str) -> str:
    return value if value and value != "A completer" else "A_COMPLETER"


def _has_concrete_value(value: str) -> bool:
    normalized = str(value or "").strip()
    return normalized not in {"", "A completer", "A_COMPLETER", "Non detecte", "Non detectee"}


def _build_fact_sentence(label: str, value: str) -> str:
    if not _has_concrete_value(value):
        return ""
    return f"{label} : {value}."


def _build_missing_section_message(section_focus: str, source_document: str = "") -> str:
    source_text = f" Source principale : {source_document}." if source_document else ""
    return (
        f"A_COMPLETER. Les informations necessaires pour la section `{section_focus}` n'ont pas ete extraites de maniere suffisamment fiable depuis le dossier actuel."
        + source_text
        + " Cette partie ne doit pas etre meublee generiquement : elle doit etre reprise a partir du contenu reel du dossier ou completee manuellement."
    )


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


def _collect_budget_signals(wf3_analysis: dict[str, object]) -> dict[str, list[str]]:
    results = list(wf3_analysis.get("resultats_criteres", []))
    budget_related = []
    budget_actions = []
    required_pieces = []
    for result in results:
        label = str(result.get("libelle", "")).strip()
        action = str(result.get("action_requise", "")).strip()
        justification = str(result.get("justification", "")).strip()
        combined = f"{label} {action} {justification}".lower()
        if any(keyword in combined for keyword in {"budget", "financement", "cofinancement", "autofinancement", "devis", "plan de financement"}):
            if label:
                budget_related.append(label)
            if action:
                budget_actions.append(action)
        if any(keyword in combined for keyword in {"piece", "pièce", "devis", "annexe", "justificatif"}):
            if label:
                required_pieces.append(label)
            if action:
                required_pieces.append(action)
    return {
        "budget_related": _dedup(budget_related),
        "budget_actions": _dedup(budget_actions),
        "required_pieces": _dedup(required_pieces),
    }


def _build_budget_comment(*parts: str) -> str:
    return " | ".join(part.strip() for part in parts if str(part).strip())


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
    structure_source = _field_source(profil_client.get("nom_structure"))
    activities = _join_field_values(profil_client.get("activites", []))
    territory_implantation = _field_value(profil_client.get("territoire_implantation"))
    references = _join_field_values(profil_client.get("historique_references", []))
    capacities = _join_field_values(profil_client.get("capacites_porteuses", []))
    title = _field_value(donnees_projet.get("titre_projet"))
    project_title_source = _field_source(donnees_projet.get("titre_projet"))
    project_elements = _join_field_values(donnees_projet.get("elements_detectes", []))
    project_dates = _join_field_values(donnees_projet.get("dates_detectees", []))
    project_amount = _field_value(donnees_projet.get("montant_detecte"))
    context_needs = _join_field_values(donnees_projet.get("contexte_besoin", []))
    objectifs = _join_field_values(donnees_projet.get("objectifs", []))
    actions = _join_field_values(donnees_projet.get("actions_prevues", []))
    publics = _join_field_values(donnees_projet.get("publics_cibles", []))
    territoire = _join_field_values(donnees_projet.get("territoire_concerne", []))
    partnerships = _join_field_values(donnees_projet.get("partenariats", []))
    moyens = _join_field_values(donnees_projet.get("moyens_humains_techniques", []))
    livrables = _join_field_values(donnees_projet.get("livrables_prevus", []))
    cofinancements = _join_field_values(donnees_projet.get("cofinancements", []))

    pieces_justificatifs = [
        str(item.get("libelle", "")).strip()
        for item in wf3_analysis.get("resultats_criteres", [])
        if "piece" in str(item.get("libelle", "")).lower() or "annexe" in str(item.get("libelle", "")).lower()
    ]

    resume_lines = [
        f"Le projet **{title}** est porte par **{structure_name}**, {legal_form},"
        + (f" implantee sur **{territory_implantation}**." if territory_implantation != "A completer" else "."),
    ]
    if context_needs != "A completer":
        resume_lines.append(f"Il repond a un besoin ou contexte identifie : {context_needs}.")
    if objectifs != "A completer":
        resume_lines.append(f"Les objectifs actuellement documentes sont les suivants : {objectifs}.")
    if actions != "A completer":
        resume_lines.append(f"Les actions prevues a ce stade comprennent : {actions}.")
    if publics != "A completer" or territoire != "A completer":
        resume_lines.append(
            f"Le projet vise prioritairement {publics if publics != 'A completer' else 'A_COMPLETER'}"
            f" sur le territoire {territoire if territoire != 'A completer' else 'A_COMPLETER'}."
        )
    if project_amount != "A completer":
        resume_lines.append(
            f"Le budget actuellement repere autour de **{project_amount}** devra etre confirme et ventile selon la trame attendue."
        )
    if missing_actions:
        resume_lines.append("Plusieurs points restent a consolider avant depot : " + " | ".join(missing_actions[:4]) + ".")

    if not _has_concrete_value(context_needs) and not _has_concrete_value(objectifs) and not _has_concrete_value(actions):
        resume_lines.append(_build_missing_section_message("resume du projet", project_title_source))

    structure_parts = [
        _build_fact_sentence("Structure porteuse detectee", structure_name),
        _build_fact_sentence("Forme juridique", legal_form),
        _build_fact_sentence("Implantation", territory_implantation),
        _build_fact_sentence("Activites reperees", activities),
        _build_fact_sentence("References reperees", references),
        _build_fact_sentence("Capacites reperees", capacities),
    ]
    structure_text = "\n\n".join(part for part in structure_parts if part)
    if not structure_text:
        structure_text = _build_missing_section_message("presentation de la structure porteuse", structure_source)

    contexte_parts = [
        _build_fact_sentence("Titre projet detecte", title),
        _build_fact_sentence("Contexte / besoin repere", context_needs),
        _build_fact_sentence("Elements projet reperes", project_elements),
        _build_fact_sentence("Objectifs reperes", objectifs),
    ]
    contexte_text = "\n\n".join(part for part in contexte_parts if part)
    if not contexte_text:
        contexte_text = _build_missing_section_message("contexte, besoin et description detaillee du projet", project_title_source)

    objectifs_text = _build_fact_sentence("Objectifs reperes", objectifs)
    if not objectifs_text:
        objectifs_text = _build_missing_section_message("objectifs du projet", project_title_source)

    actions_text = _build_fact_sentence("Actions reperees", actions)
    if not actions_text:
        actions_text = _build_missing_section_message("description des actions prevues", project_title_source)

    publics_parts = [
        _build_fact_sentence("Publics cibles reperes", publics),
        _build_fact_sentence("Territoire repere", territoire),
    ]
    publics_text = "\n\n".join(part for part in publics_parts if part)
    if not publics_text:
        publics_text = _build_missing_section_message("publics cibles, beneficiaires et territoire", project_title_source)

    methodologie_parts = [
        _build_fact_sentence("Dates / jalons reperes", project_dates),
        _build_fact_sentence("Etapes ou actions reperees", actions),
    ]
    methodologie_text = "\n\n".join(part for part in methodologie_parts if part)
    if not methodologie_text:
        methodologie_text = _build_missing_section_message("methodologie, calendrier et mise en oeuvre", project_title_source)

    moyens_parts = [
        _build_fact_sentence("Moyens humains ou techniques reperes", moyens),
        _build_fact_sentence("Partenariats reperes", partnerships),
    ]
    moyens_text = "\n\n".join(part for part in moyens_parts if part)
    if not moyens_text:
        moyens_text = _build_missing_section_message("moyens mobilises et partenariats", project_title_source)

    budget_parts = [
        _build_fact_sentence("Montant repere", project_amount),
        _build_fact_sentence("Cofinancements reperes", cofinancements),
        _build_fact_sentence("Livrables reperes", livrables),
    ]
    budget_text = "\n\n".join(part for part in budget_parts if part)
    if not budget_text:
        budget_text = _build_missing_section_message("livrables, budget et plan de financement", project_title_source)

    sections = [
        {
            "section": "1. Resume du projet",
            "statut": "partiel" if title != "A completer" else "a_completer",
            "contenu": "\n\n".join(resume_lines),
        },
        {
            "section": "2. Presentation de la structure porteuse",
            "statut": "partiel" if structure_name != "A completer" else "a_completer",
            "contenu": structure_text,
        },
        {
            "section": "3. Contexte, besoin et description detaillee du projet",
            "statut": "partiel" if project_elements != "A completer" or context_needs != "A completer" else "a_completer",
            "contenu": contexte_text,
        },
        {
            "section": "4. Objectifs du projet",
            "statut": "partiel" if objectifs != "A completer" else "a_completer",
            "contenu": objectifs_text,
        },
        {
            "section": "5. Description des actions prevues",
            "statut": "partiel" if actions != "A completer" else "a_completer",
            "contenu": actions_text,
        },
        {
            "section": "6. Publics cibles, beneficiaires et territoire",
            "statut": "partiel" if publics != "A completer" or territoire != "A completer" else "a_completer",
            "contenu": publics_text,
        },
        {
            "section": "7. Methodologie, calendrier et mise en oeuvre",
            "statut": "partiel" if requirements["planning_required"] or project_dates != "A completer" or actions != "A completer" else "a_completer",
            "contenu": methodologie_text,
        },
        {
            "section": "8. Moyens mobilises et partenariats",
            "statut": "partiel" if moyens != "A completer" or partnerships != "A completer" else "a_completer",
            "contenu": moyens_text,
        },
        {
            "section": "9. Livrables, budget et plan de financement",
            "statut": "partiel" if requirements["budget_required"] or project_amount != "A completer" or livrables != "A completer" else "a_completer",
            "contenu": budget_text,
        },
        {
            "section": "10. Pieces et points a completer",
            "statut": "a_completer" if missing_actions or pieces_justificatifs else "partiel",
            "contenu": (
                "Points d'attention identifies : "
                + (" | ".join(missing_actions[:8]) if missing_actions else "Aucun point critique remonte.")
                + "\n\nPieces et justificatifs a verifier : "
                + (" | ".join(pieces_justificatifs[:8]) if pieces_justificatifs else "A_PRECISER")
                + "\n\nCette section doit servir de checklist de finalisation du dossier. Elle doit permettre de distinguer les informations a confirmer, les annexes a joindre, les justificatifs a retrouver et les arbitrages encore necessaires avant depot."
            ),
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
    cofinancements = _join_field_values(donnees_projet.get("cofinancements", []), default="")
    actions = _join_field_values(donnees_projet.get("actions_prevues", []), default="")
    moyens = _join_field_values(donnees_projet.get("moyens_humains_techniques", []), default="")
    publics = _join_field_values(donnees_projet.get("publics_cibles", []), default="")
    livrables = _join_field_values(donnees_projet.get("livrables_prevus", []), default="")
    requirements = _infer_call_requirements(wf3_analysis)
    budget_signals = _collect_budget_signals(wf3_analysis)
    action_items = _split_joined_values(actions)
    means_items = _split_joined_values(moyens)
    cofinancement_items = _split_joined_values(cofinancements)

    charges = [
        {
            "poste": "1.1 Coordination, administration et gestion du projet",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": _build_budget_comment(means_items[0] if means_items else "", "Temps de coordination, gestion, suivi administratif"),
        },
        {
            "poste": "1.2 Ressources humaines artistiques, techniques ou pedagogiques",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": _build_budget_comment(action_items[0] if action_items else "", "Intervenants, artistes, techniciens, formateurs"),
        },
        {
            "poste": "1.3 Prestations externes et sous-traitance",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": _build_budget_comment(action_items[1] if len(action_items) > 1 else "", "A documenter avec devis si requis"),
        },
        {
            "poste": "1.4 Materiel, equipements et outils techniques",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": _build_budget_comment(means_items[1] if len(means_items) > 1 else "", "Achats ou locations techniques lies au projet"),
        },
        {
            "poste": "1.5 Communication, diffusion et valorisation",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": _build_budget_comment(publics if publics != "A completer" else "", "Supports, diffusion, mediation, mobilisation des publics"),
        },
        {
            "poste": "1.6 Deplacements, missions, logistique et accueil",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": "Transports, repas, hebergement, locations ponctuelles, accueil publics/intervenants",
        },
        {
            "poste": "1.7 Evaluation, suivi, livrables et restitution",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": _build_budget_comment(livrables if livrables != "A completer" else "", "Evaluation, bilan, captation, restitution, reporting"),
        },
        {
            "poste": "1.8 Frais indirects ou administratifs imputes au projet",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": "Verifier si les frais de structure sont autorises ou plafonnes par l'appel",
        },
        {
            "poste": "1.9 Documentation, capitalisation et valorisation finale",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": _build_budget_comment(livrables if livrables != "A completer" else "", "Edition, restitution, publication, trace finale du projet"),
        },
    ]
    produits = [
        {
            "poste": "2.1 Subvention sollicitee au titre de l'appel",
            "montant_previsionnel": amount if amount != "A completer" else "A_COMPLETER",
            "commentaire": "Verifier que ce montant correspond bien a la subvention demandee et non au budget global",
        },
        {
            "poste": "2.2 Autofinancement / apport de la structure",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": cofinancement_items[0] if cofinancement_items else "Verifier le niveau minimum d'autofinancement requis",
        },
        {
            "poste": "2.3 Cofinancements publics",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": cofinancement_items[1] if len(cofinancement_items) > 1 else cofinancements or "A completer",
        },
        {
            "poste": "2.4 Partenariats prives, mecenat ou sponsoring",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": cofinancement_items[2] if len(cofinancement_items) > 2 else "A completer",
        },
        {
            "poste": "2.5 Recettes propres du projet",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": "Billetterie, ventes, inscriptions, prestations, contribution des beneficiaires si pertinent",
        },
        {
            "poste": "2.6 Autres produits affectes au projet",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": "Autres concours ou valorisations a confirmer",
        },
        {
            "poste": "2.7 Valorisation en nature ou contributions volontaires",
            "montant_previsionnel": "A_COMPLETER",
            "commentaire": "A utiliser seulement si ce mode de valorisation est accepte par le financeur",
        },
    ]

    notes = [
        "Trame budgetaire a reprendre dans le format comptable demande par l'appel a projet.",
        "Verifier l'equilibre Charges = Produits.",
        "Verifier que la subvention sollicitee, l'autofinancement et les autres financements sont distingues clairement.",
    ]
    if requirements["budget_required"]:
        notes.append("L'appel a projet mentionne des attentes budgetaires explicites.")
    if budget_signals["budget_related"]:
        notes.append("Contraintes ou attentes budgetaires detectees : " + " | ".join(budget_signals["budget_related"][:6]))
    if budget_signals["budget_actions"]:
        notes.append("Actions budgetaires a traiter : " + " | ".join(budget_signals["budget_actions"][:6]))
    if budget_signals["required_pieces"]:
        notes.append("Pieces / justificatifs budgetaires a verifier : " + " | ".join(budget_signals["required_pieces"][:6]))
    if amount != "A completer":
        notes.append(
            "Montant repere dans les sources : "
            + amount
            + ". Verifier s'il s'agit du budget total, de la subvention demandee ou d'un cofinancement."
        )
    if cofinancements:
        notes.append("Cofinancements reperes : " + cofinancements)
    notes.append("Ajouter ou supprimer des lignes selon la trame exacte du financeur, les devis disponibles et la logique reelle du projet.")

    return {
        "titre": "Budget previsionnel du projet",
        "colonnes": ["Charges", "Montant previsionnel", "Produits", "Montant previsionnel"],
        "charges": charges,
        "produits": produits,
        "notes": notes,
    }


def build_project_budget_markdown(budget: dict[str, Any]) -> str:
    metadata = budget.get("metadata", {}) if isinstance(budget.get("metadata", {}), dict) else {}
    lines = [f"# {budget.get('titre', 'Budget previsionnel du projet')}", ""]

    description = str(metadata.get("description", "")).strip()
    synthese = str(metadata.get("synthese_financements", "")).strip()
    statut = str(metadata.get("statut", "")).strip()
    periode = metadata.get("periode", {}) if isinstance(metadata.get("periode", {}), dict) else {}
    financeur = metadata.get("financeur_principal", {}) if isinstance(metadata.get("financeur_principal", {}), dict) else {}
    structure = metadata.get("structure_porteuse", {}) if isinstance(metadata.get("structure_porteuse", {}), dict) else {}

    if description:
        lines.extend([description, ""])
    if synthese:
        lines.extend([f"**Synthese financements** : {synthese}", ""])
    if statut:
        lines.append(f"**Statut budgetaire** : {statut}")
    if isinstance(periode, dict) and (periode.get("debut") or periode.get("fin")):
        lines.append(f"**Periode** : {periode.get('debut', 'A_COMPLETER')} -> {periode.get('fin', 'A_COMPLETER')}")
    if isinstance(financeur, dict) and financeur:
        financeur_bits = [str(financeur.get("nom", "")).strip(), str(financeur.get("type", "")).strip()]
        if str(financeur.get("taux_max", "")).strip():
            financeur_bits.append(f"taux max {financeur.get('taux_max')}")
        if str(financeur.get("plafond", "")).strip():
            financeur_bits.append(f"plafond {financeur.get('plafond')}")
        lines.append("**Financeur principal** : " + " | ".join(bit for bit in financeur_bits if bit))
    if isinstance(structure, dict) and structure:
        structure_bits = [str(structure.get("nom", "")).strip(), str(structure.get("forme_juridique", "")).strip()]
        if str(structure.get("territoire", "")).strip():
            structure_bits.append(str(structure.get("territoire", "")).strip())
        lines.append("**Structure porteuse** : " + " | ".join(bit for bit in structure_bits if bit))
    if len(lines) > 2:
        lines.append("")

    lines.extend(
        [
            "| Section charge | Charges | Montant previsionnel | Section produit | Produits | Montant previsionnel |",
            "| --- | --- | ---: | --- | --- | ---: |",
        ]
    )

    charges = list(budget.get("charges", []))
    produits = list(budget.get("produits", []))
    max_len = max(len(charges), len(produits))
    for index in range(max_len):
        charge = charges[index] if index < len(charges) else {"poste": "", "montant_previsionnel": ""}
        produit = produits[index] if index < len(produits) else {"poste": "", "montant_previsionnel": ""}
        lines.append(
            f"| {charge.get('section', '') or charge.get('sous_section', '')} | "
            f"{charge.get('poste', '')} | {charge.get('montant_previsionnel', '')} | "
            f"{produit.get('section', '') or produit.get('sous_section', '')} | "
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

    profil_client = wf2b_structured.get("profil_client", {})
    capacities = _join_field_values(profil_client.get("capacites_porteuses", []), default="")
    activities = _join_field_values(profil_client.get("activites", []), default="")
    implantation = _field_value(profil_client.get("territoire_implantation"))
    references = _join_field_values(profil_client.get("historique_references", []), default="")
    budget_signals = _collect_budget_signals(wf3_analysis)

    return {
        "titre": "Budget previsionnel de structure",
        "colonnes": ["Charges de structure", "Montant previsionnel", "Produits de structure", "Montant previsionnel"],
        "charges": [
            {"poste": "1.1 Personnel permanent et encadrement", "montant_previsionnel": "A_COMPLETER", "commentaire": _build_budget_comment(capacities, "Direction, coordination, administration") or "A completer"},
            {"poste": "1.2 Charges sociales et taxes liees a l'emploi", "montant_previsionnel": "A_COMPLETER", "commentaire": "A completer"},
            {"poste": "1.3 Loyers, fluides, assurances et frais fixes", "montant_previsionnel": "A_COMPLETER", "commentaire": implantation if implantation != "A completer" else "A completer"},
            {"poste": "1.4 Fonctionnement courant et maintenance", "montant_previsionnel": "A_COMPLETER", "commentaire": activities or "A completer"},
            {"poste": "1.5 Equipements, amortissements ou renouvellements", "montant_previsionnel": "A_COMPLETER", "commentaire": capacities or "A completer"},
            {"poste": "1.6 Communication institutionnelle et vie associative", "montant_previsionnel": "A_COMPLETER", "commentaire": references or "A completer"},
            {"poste": "1.7 Autres charges de structure", "montant_previsionnel": "A_COMPLETER", "commentaire": "A completer"},
        ],
        "produits": [
            {"poste": "2.1 Subventions de fonctionnement", "montant_previsionnel": "A_COMPLETER", "commentaire": "A completer"},
            {"poste": "2.2 Recettes propres et cotisations", "montant_previsionnel": "A_COMPLETER", "commentaire": "A completer"},
            {"poste": "2.3 Prestations, ventes ou productions", "montant_previsionnel": "A_COMPLETER", "commentaire": activities or "A completer"},
            {"poste": "2.4 Partenariats, mecenat ou apports prives", "montant_previsionnel": "A_COMPLETER", "commentaire": "A completer"},
            {"poste": "2.5 Reports, reserves ou fonds associatifs mobilises", "montant_previsionnel": "A_COMPLETER", "commentaire": "A completer"},
            {"poste": "2.6 Autres produits de structure", "montant_previsionnel": "A_COMPLETER", "commentaire": "A completer"},
        ],
        "notes": [
            "A produire seulement si le financeur demande un budget de structure ou un previsionnel de la structure porteuse.",
            "Verifier la coherence entre budget projet et budget structure.",
            "Dissocier clairement les charges / produits de structure de ceux du projet finance.",
            "Faire apparaitre ici les charges fixes, ressources recurrentes et moyens permanents de la structure.",
            "Ne pas dupliquer les depenses specifiquement imputees au budget projet.",
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
