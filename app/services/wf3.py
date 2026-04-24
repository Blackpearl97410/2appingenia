from __future__ import annotations

import re


def _join_values(items: list[dict[str, object]]) -> str:
    return " | ".join(str(item.get("value", "")).strip() for item in items if str(item.get("value", "")).strip())


def _criterion_weight(criterion: dict[str, object]) -> int:
    category = str(criterion.get("categorie", "souhaitable"))
    if category == "bloquant":
        return 3
    if category == "obligatoire":
        return 2
    return 1


def _criterion_expected_block(criterion: dict[str, object]) -> str:
    label = str(criterion.get("libelle", "")).lower()
    detail = str(criterion.get("detail", "")).lower()
    domain = str(criterion.get("domaine", "")).lower()
    combined = f"{label} {detail} {domain}"

    if any(keyword in combined for keyword in ["date", "planning", "calendrier"]):
        return "projet"
    if any(keyword in combined for keyword in ["montant", "budget", "depense", "financement"]):
        return "projet"
    if any(keyword in combined for keyword in ["association", "entreprise", "eligible", "eligibilite", "juridique"]):
        return "client"
    if any(keyword in combined for keyword in ["piece", "candidature", "formulaire"]):
        return "mixte"
    return "mixte"


def _criterion_evidence_bundle(wf2b_structured: dict[str, object]) -> dict[str, str]:
    profil_client = wf2b_structured.get("profil_client", {})
    donnees_projet = wf2b_structured.get("donnees_projet", {})

    client_activities = _join_values(profil_client.get("activites", []))
    project_dates = _join_values(donnees_projet.get("dates_detectees", []))
    project_elements = _join_values(donnees_projet.get("elements_detectes", []))

    return {
        "client_structure": str(profil_client.get("forme_juridique", {}).get("value", "Non detectee")),
        "client_identity": " | ".join(
            part for part in [
                str(profil_client.get("nom_structure", {}).get("value", "")),
                client_activities,
                str(profil_client.get("siret", {}).get("value", "")),
            ]
            if part and part not in {"Non detecte", "Aucune"}
        ) or "Aucune",
        "project_amount": str(donnees_projet.get("montant_detecte", {}).get("value", "Non detecte")),
        "project_dates": project_dates or "Aucune",
        "project_elements": project_elements or "Aucun",
        "project_title": str(donnees_projet.get("titre_projet", {}).get("value", "Non detecte")),
    }


def _contains_keyword(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _compare_criterion(
    criterion: dict[str, object],
    evidence: dict[str, str],
) -> dict[str, object]:
    label = str(criterion.get("libelle", ""))
    detail = str(criterion.get("detail", ""))
    category = str(criterion.get("categorie", "souhaitable"))
    source_document = str(criterion.get("source_document", ""))
    expected_block = _criterion_expected_block(criterion)
    combined = f"{label} {detail}".lower()

    statut = "a_confirmer"
    score = 50
    justification = "Critere present mais comparaison encore partielle."
    ecart = ""
    action = "Confirmer ce critere a partir des pieces chargees."
    used_data = ""

    if any(keyword in combined for keyword in ["association", "entreprise", "eligible", "eligibilite", "juridique"]):
        client_structure = evidence["client_structure"]
        used_data = client_structure
        if client_structure == "Non detectee":
            statut = "manquant"
            score = 20
            justification = "Le type de structure client n'a pas ete detecte."
            action = "Ajouter ou completer les statuts / documents client."
        elif "association" in combined and "association" in client_structure:
            statut = "valide"
            score = 100
            justification = "La forme juridique client correspond au critere d'eligibilite detecte."
            action = "Aucune action immediate."
        else:
            statut = "a_confirmer"
            score = 60
            justification = "Une forme juridique client existe mais la correspondance exacte reste a confirmer."
            action = "Verifier manuellement le critere d'eligibilite et la forme juridique."

    elif any(keyword in combined for keyword in ["date", "planning", "calendrier"]):
        used_data = evidence["project_dates"]
        if evidence["project_dates"] != "Aucune":
            statut = "valide"
            score = 90
            justification = "Le projet contient des dates ou un calendrier compatibles avec un controle futur."
            action = "Verifier l'alignement exact avec la date limite dossier."
        else:
            statut = "manquant"
            score = 15
            justification = "Aucune date projet exploitable n'a ete detectee."
            action = "Ajouter un planning ou des dates projet."

    elif any(keyword in combined for keyword in ["montant", "budget", "depense", "financement"]):
        used_data = evidence["project_amount"]
        if evidence["project_amount"] != "Non detecte":
            statut = "valide"
            score = 85
            justification = "Un montant projet ou budget a ete detecte."
            action = "Verifier la coherence avec le plafond ou l'enveloppe dossier."
        else:
            statut = "manquant"
            score = 20
            justification = "Aucun montant projet exploitable n'a ete detecte."
            action = "Ajouter un budget ou un plan de financement."

    elif any(keyword in combined for keyword in ["piece", "candidature", "formulaire"]):
        used_data = " | ".join(
            part for part in [evidence["client_identity"], evidence["project_elements"]] if part not in {"Aucune", "Aucun"}
        ) or "Aucune"
        if used_data != "Aucune":
            statut = "a_confirmer"
            score = 70
            justification = "Des pieces ou elements de reponse semblent disponibles, mais le controle reste partiel."
            action = "Verifier les pieces attendues une par une."
        else:
            statut = "manquant"
            score = 15
            justification = "Aucune preuve documentaire suffisante n'a ete detectee pour les pieces demandees."
            action = "Ajouter les pieces de candidature et les justificatifs."

    else:
        used_data = " | ".join(
            part for part in [evidence["client_identity"], evidence["project_elements"], evidence["project_title"]]
            if part not in {"Aucune", "Aucun", "Non detecte"}
        ) or "Aucune"
        if used_data != "Aucune":
            statut = "a_confirmer"
            score = 65
            justification = "Le dossier et les pieces chargees permettent un debut de comparaison, sans validation forte."
            action = "Verifier ce critere manuellement ou l'affiner avec un LLM."
        else:
            statut = "manquant"
            score = 20
            justification = "Aucune donnee exploitable n'a ete trouvee pour comparer ce critere."
            action = "Completer les documents client ou projet."

    if category == "bloquant" and statut == "manquant":
        statut = "non_valide"
        score = 0
        justification = "Critere bloquant sans preuve compatible dans les documents charges."
        action = "Traiter ce critere en priorite avant toute poursuite."

    if category == "interpretatif" and statut == "valide":
        statut = "a_confirmer"
        score = min(score, 75)
        justification = "Critere interpretatif : signal utile, mais validation humaine encore necessaire."
        action = "Confirmer ce point avant conclusion finale."

    if statut in {"manquant", "non_valide"}:
        ecart = detail or label

    return {
        "critere_id": criterion.get("id_local"),
        "libelle": label,
        "categorie": category,
        "domaine": criterion.get("domaine", "administratif"),
        "source_document": source_document,
        "source_texte": criterion.get("source_texte", ""),
        "bloc_cible": expected_block,
        "statut": statut,
        "score": score,
        "justification": justification,
        "ecart": ecart,
        "action_requise": action,
        "donnee_utilisee": used_data,
        "niveau_confiance": criterion.get("niveau_confiance", "moyen"),
        "necessite_validation": criterion.get("necessite_validation", False) or statut == "a_confirmer",
    }


def build_wf3_analysis(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    global_context_bridge: dict[str, str] | None = None,
) -> dict[str, object]:
    criteres = list(wf2a_structured.get("criteres", []))
    evidence = _criterion_evidence_bundle(wf2b_structured)
    results = [_compare_criterion(criterion, evidence) for criterion in criteres]

    total_weight = 0
    weighted_score = 0
    counts = {"valide": 0, "a_confirmer": 0, "manquant": 0, "non_valide": 0}

    for criterion, result in zip(criteres, results):
        weight = _criterion_weight(criterion)
        total_weight += weight
        weighted_score += int(result["score"]) * weight
        counts[result["statut"]] = counts.get(result["statut"], 0) + 1

    score_global = round(weighted_score / total_weight) if total_weight else 0

    global_bonus = 0
    niveau_confiance = "moyen"
    if global_context_bridge:
        etat_global = global_context_bridge.get("etat_global_documentaire", "")
        prescore_global = global_context_bridge.get("prescore_global_documentaire", "")
        incoherences = global_context_bridge.get("incoherences_globales", "Aucune")
        if "pret pour pre-analyse" in etat_global:
            global_bonus += 5
            niveau_confiance = "haut"
        elif "faible" in prescore_global.lower():
            global_bonus -= 5
            niveau_confiance = "bas"
        if incoherences != "Aucune incoherence simple detectee":
            global_bonus -= 10
            niveau_confiance = "bas"

    score_global = max(0, min(100, score_global + global_bonus))

    if counts["non_valide"] > 0:
        statut_eligibilite = "non compatible"
    elif score_global >= 75 and counts["manquant"] == 0:
        statut_eligibilite = "compatible"
    elif score_global >= 55:
        statut_eligibilite = "a confirmer"
    else:
        statut_eligibilite = "partiellement compatible"

    structure_scores = [result["score"] for result in results if result["bloc_cible"] == "client"]
    projet_scores = [result["score"] for result in results if result["bloc_cible"] == "projet"]
    mixte_scores = [result["score"] for result in results if result["bloc_cible"] == "mixte"]

    sous_scores = {
        "bloc_client": round(sum(structure_scores) / len(structure_scores)) if structure_scores else 0,
        "bloc_projet": round(sum(projet_scores) / len(projet_scores)) if projet_scores else 0,
        "bloc_mixte": round(sum(mixte_scores) / len(mixte_scores)) if mixte_scores else 0,
        "fiabilite_documentaire": 80 if niveau_confiance == "haut" else 55 if niveau_confiance == "moyen" else 30,
    }

    resume_executif = (
        f"Score global {score_global}/100. "
        f"Statut {statut_eligibilite}. "
        f"{counts['valide']} critere(s) valides, "
        f"{counts['a_confirmer']} a confirmer, "
        f"{counts['manquant']} manquant(s), "
        f"{counts['non_valide']} non valide(s)."
    )

    return {
        "score_global": score_global,
        "statut_eligibilite": statut_eligibilite,
        "niveau_confiance": niveau_confiance,
        "sous_scores": sous_scores,
        "resume_executif": resume_executif,
        "resultats_criteres": results,
        "counts": counts,
        "global_bonus": global_bonus,
    }
