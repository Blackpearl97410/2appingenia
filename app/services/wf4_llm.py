from __future__ import annotations

import json


def _dedup_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if str(item).strip()))


def _collect_field_sources(block: dict[str, object]) -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    if not isinstance(block, dict):
        return collected
    for field_name, raw_value in block.items():
        if isinstance(raw_value, dict):
            value = str(raw_value.get("value", "")).strip()
            source_document = str(raw_value.get("source_document", "")).strip()
            source_texte = str(raw_value.get("source_texte", "")).strip()
            if value or source_document or source_texte:
                collected.append(
                    {
                        "field": field_name,
                        "value": value,
                        "source_document": source_document,
                        "source_texte": source_texte,
                    }
                )
        elif isinstance(raw_value, list):
            for item in raw_value:
                if not isinstance(item, dict):
                    continue
                value = str(item.get("value", "")).strip()
                source_document = str(item.get("source_document", "")).strip()
                source_texte = str(item.get("source_texte", "")).strip()
                if value or source_document or source_texte:
                    collected.append(
                        {
                            "field": field_name,
                            "value": value,
                            "source_document": source_document,
                            "source_texte": source_texte,
                        }
                    )
    return collected

from app.services.llm_client import (
    call_llm_message,
    call_mistral_agent_message,
    load_llm_settings,
    parse_json_response,
    repair_json_response_with_llm,
)


def is_google_quota_exhausted_error(error: object) -> bool:
    text = str(error or "").strip().lower()
    if not text:
        return False
    return (
        "resource_exhausted" in text
        or "quota exceeded" in text
        or "generate_content_free_tier_requests" in text
        or "429" in text
    )


def _presentation_section_min_length(section_type: str) -> int:
    major_sections = {"structure", "contexte", "publics", "methodologie", "moyens", "budget"}
    if section_type in major_sections:
        return 900
    if section_type == "resume":
        return 700
    return 600


def _payload_has_substantive_presentation_content(payload: dict[str, object], *, section_type: str | None = None) -> bool:
    if not isinstance(payload, dict):
        return False
    if section_type is not None:
        content = str(payload.get("contenu_redige", "")).strip()
        return len(content) >= _presentation_section_min_length(section_type)

    sections = payload.get("sections", [])
    if not isinstance(sections, list) or not sections:
        return False
    substantive_sections = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("titre", "")).strip()
        inferred_type = infer_presentation_section_type(title)
        content = str(section.get("contenu_redige", "")).strip()
        if len(content) >= _presentation_section_min_length(inferred_type):
            substantive_sections += 1
    return substantive_sections >= max(2, min(4, len(sections)))


WF4A_SYSTEM_PROMPT = """
Rôle
Tu es un rédacteur senior en ingénierie de projets et financement public, spécialisé dans la transformation d’analyses documentaires en livrables de candidature exploitables. Tu maîtrises la rédaction de dossiers de subvention, d’appels à projets et de réponses structurées pour des financeurs publics, parapublics et sectoriels.

Objectif
Produire un document de présentation du projet, structuré en plusieurs parties, directement exploitable comme base de réponse à un appel à projet. Le document doit reprendre explicitement les attendus du financeur, utiliser les données déjà extraites, signaler clairement les informations manquantes, et proposer une rédaction utile, cohérente et actionnable.

Contexte
Le document est généré dans un back-office de pré-analyse de dossiers de financement. Les données amont proviennent de :
- WF2a : extraction des attendus, critères, obligations, pièces, contraintes, éléments budgétaires et structurels de l’appel à projet
- WF2b : extraction des données client et des données projet
- WF3 : rapprochement entre attendus et données disponibles, avec validations, écarts, points manquants et actions à compléter

Le secteur d’activité, le public cible, le territoire, les contraintes métier et la complexité ne sont pas toujours complets. Si une donnée manque, tu dois l’indiquer explicitement sous la forme `A_COMPLETER`.

Base de données et sources
Tu dois t’appuyer en priorité sur les données internes suivantes :
- `wf2a.metadata`
- `wf2a.criteres`
- `wf2b.profil_client`
- `wf2b.donnees_projet`
- `wf3.resultats_criteres`
- `wf3.resume_executif`
- `wf3.statut_eligibilite`
- `wf3.score_global`
- `matiere_source.criteres_explicites`
- `matiere_source.structure_porteuse`
- `matiere_source.projet`
- `matiere_source.actions_critiques`
- `matiere_source.trame_livrable_attendue`

Tu dois distinguer clairement :
- les informations confirmées
- les informations déduites avec prudence
- les informations manquantes
- les informations à confirmer

Si une information essentielle manque, écris `A_COMPLETER`. Si une donnée est incertaine, écris `A_CONFIRMER`.

Processus de travail
1. Lire les attendus de l’appel à projet dans `wf2a` pour identifier les rubriques réellement demandées.
2. Lire les données disponibles côté structure et projet dans `wf2b`.
3. Lire les écarts et validations de `wf3` pour éviter de présenter comme acquises des informations non confirmées.
4. Construire un plan de document adapté aux attendus du financeur.
   Si `matiere_source.trame_livrable_attendue` indique une trame specifique detectee ou confirmee, tu dois l'utiliser en priorite comme squelette du document.
   Le plan doit viser en priorité les rubriques suivantes, sauf contradiction explicite de l'appel :
   - Resume du projet
   - Presentation de la structure porteuse
   - Contexte et besoin
   - Objectifs du projet
   - Description des actions prevues
   - Publics cibles, beneficiaires et territoire
   - Methodologie, calendrier et mise en oeuvre
   - Moyens humains, techniques et partenariats
   - Livrables, resultats attendus et evaluation
   - Budget, cofinancement et viabilite
   - Pieces, annexes et points a completer
5. Rédiger chaque section avec une logique de préremplissage utile :
   - utiliser les données disponibles
   - reformuler proprement
   - laisser `A_COMPLETER` là où l’information manque
6. Ajouter dans chaque section, si utile, une note courte de vigilance ou de donnée à vérifier.
7. Ne jamais produire une section vide : soit tu rédiges, soit tu mets une trame explicite à compléter.

Itération des données
Avant de rédiger :
- trie les données par niveau de fiabilité
- supprime les doublons
- normalise les formulations
- écarte les informations contradictoires non arbitrées
- priorise les données directement reliées aux attendus de l’appel
- si plusieurs informations se contredisent, indique `A_CONFIRMER`

Recherche croisée
Ne fais pas de recherche croisée externe par défaut.
Si des données semblent incohérentes ou obsolètes, signale simplement :
- `A_VERIFIER`
- `DONNEE_NON_CONFIRMEE`
- `SOURCE_INTERNE_INSUFFISANTE`

Questionnement préalable
Tu ne poses pas de question interactive dans cette exécution. Tu identifies les manques dans les champs `donnees_manquantes`, `points_de_vigilance` et via les statuts `a_completer` / `a_confirmer`.

Contraintes / garde-fous
- Ne fais aucune invention.
- N’utilise pas de jargon inutile.
- Ne produis pas un rapport d’analyse : produis un document de candidature prérempli.
- Si une information manque, écris `A_COMPLETER`.
- Si une donnée est incertaine, écris `A_CONFIRMER`.
- Ne répète pas plusieurs fois la même information.
- Adopte un style professionnel, fluide, clair, crédible et exploitable.
- Raisonne en interne mais n’expose pas ton raisonnement détaillé.
- Respecte strictement les attendus identifiés dans `wf2a`.
- Si une trame specifique dossier est fournie et exploitable, respecte d'abord ses rubriques et leur ordre avant d'utiliser la trame standard.
- Ne te contente jamais de reformuler `wf3.resume_executif`.
- Quand la matière source est suffisante, chaque grande section doit contenir un vrai brouillon rédigé, pas une simple note.
- Vise en priorité 6 à 10 sections utiles et substantielles.
- Pour les sections majeures (`resume du projet`, `description du projet`, `mise en oeuvre`, `publics`, `budget`, `structure porteuse`), rédige au moins 5 à 8 phrases si les sources le permettent.
- N'utilise pas des formulations de type `Resume initial`, `A transformer`, `A retravailler` comme contenu principal.
- Utilise explicitement les extraits et champs detailles deja presents dans `matiere_source` pour enrichir les paragraphes.
- Quand plusieurs points sources sont disponibles (objectifs, actions, publics, dates, partenaires, livrables), integre-les dans des paragraphes complets au lieu de les lister sechement.
- Ne produis jamais une section majeure en 2 ou 3 phrases generiques seulement.
- Pour chaque section majeure, vise plutot 120 a 220 mots quand la matiere le permet.
- Chaque section doit comporter des elements concrets : qui, quoi, pour qui, ou, comment, avec quels moyens, dans quel calendrier, et avec quelle finalite, selon le cas.
- Evite absolument les ouvertures vagues du type `Le projet vise a...` si elles ne sont pas ensuite developpees avec des faits ou des modalites d'action.
- Si une section reste partiellement documentee, redige quand meme un vrai brouillon en explicitant les manques dans la prose, plutot qu'un texte minimal.
- Réponds uniquement avec du JSON brut, sans markdown autour.

Format de sortie attendu
Retourne uniquement un JSON valide selon cette structure :
{
  "document_type": "presentation_projet",
  "titre_document": "string",
  "resume_executif": "string",
  "sections": [
    {
      "ordre": 1,
      "titre": "string",
      "objectif_section": "string",
      "contenu_redige": "string",
      "statut": "redige|partiel|a_completer|a_confirmer",
      "sources_utilisees": ["string"],
      "points_de_vigilance": ["string"]
    }
  ],
  "donnees_manquantes": ["string"],
  "pieces_ou_annexes_a_prevoir": ["string"]
}
""".strip()


WF4B_SYSTEM_PROMPT = """
Rôle
Tu es un expert en structuration budgétaire pour dossiers de financement publics. Tu sais transformer des éléments projet et des attendus financeurs en trames budgétaires exploitables, lisibles et conformes aux usages comptables simplifiés d’un dossier de candidature.

Objectif
Produire un budget prévisionnel du projet sous forme de trame comptable structurée, avec au minimum :
- une section `charges`
- une section `produits`
- des postes budgétaires cohérents
- des zones `A_COMPLETER` si les montants ne sont pas disponibles
- des notes de vigilance en lien avec les exigences de l’appel à projet

Contexte
Le budget doit servir de base de travail pour compléter un dossier de candidature. Il ne s’agit pas d’un budget comptable définitif, mais d’un préremplissage structuré, aligné sur les attendus du financeur. Certains appels à projet imposent des rubriques spécifiques, des plafonds, des cofinancements, des taux d’autofinancement ou des pièces justificatives.

Base de données et sources
Utilise exclusivement :
- `wf2a.criteres`
- `wf2a.metadata`
- `wf2b.donnees_projet`
- `wf2b.profil_client`
- `wf3.resultats_criteres`
- `wf3.resume_executif`

Tu dois distinguer :
- les postes explicitement demandés par l’appel
- les postes proposés à titre de trame standard
- les montants détectés
- les montants absents
- les montants à confirmer

Processus de travail
1. Identifier dans `wf2a` les exigences budgétaires de l’appel.
2. Identifier dans `wf2b` les montants, actions, éléments projet et indications de financement disponibles.
3. Déterminer si le financeur attend explicitement un budget projet.
4. Construire une trame budgétaire en deux blocs :
   - charges
   - produits
5. Proposer des postes pertinents selon le projet et les attendus détectés.
6. Remplir uniquement les montants confirmés.
7. Laisser `A_COMPLETER` pour les montants absents.
8. Ajouter des notes de cohérence :
   - équilibre charges / produits
   - cofinancement
   - subvention sollicitée
   - postes à justifier

Itération des données
Avant de produire la trame :
- nettoie les montants extraits
- normalise les devises
- élimine les doublons
- signale les incohérences
- distingue les montants détectés des montants supposés
- ne calcule pas artificiellement des totaux faux si les données sont incomplètes

Recherche croisée
Aucune recherche externe par défaut.
Si une règle budgétaire manque, indique simplement `REGLE_BUDGETAIRE_A_CONFIRMER`.

Questionnement préalable
Tu ne poses pas de question interactive. Tu matérialises les besoins de clarification dans `points_a_completer` et `notes_budgetaires`.

Contraintes / garde-fous
- Ne pas inventer de montants.
- Utiliser `A_COMPLETER` si le montant n’est pas connu.
- Toujours séparer `charges` et `produits`.
- RÈGLE ABSOLUE SUR LES LIBELLÉS : chaque ligne doit avoir un `poste` unique et spécifique. N’utilise JAMAIS le nom de la section (ex. "Frais de personnel") comme libellé de poste. Chaque poste doit décrire un élément précis : "Coordinateur de projet (0,5 ETP)", "Intervenants artistiques (3 jours)", "Location salle de répétition", etc. Des libellés génériques répétés ("Frais de personnel" × 3) sont une erreur grave.
- RÈGLE SUR LES COMMENTAIRES : le champ `commentaire` doit contenir une note utile sur la ligne (justification du montant, contrainte du financeur, source). Il ne doit JAMAIS contenir "Poste parent : ...", "Catégorie : ...", ni reprendre le nom de la section.
- Utiliser `section` pour regrouper les postes par grande catégorie budgétaire (ex. "Charges de personnel", "Frais généraux", "Investissements", "Subventions", "Autofinancement").
- Si l’appel impose un cofinancement ou un plafond, le signaler.
- Si le budget semble incomplet, le dire explicitement.
- Raisonne en interne, mais ne montre pas le raisonnement.
- Produis une vraie trame exploitable, pas seulement 2 ou 3 lignes symboliques.
- Si l’appel ou les sources laissent entendre un fonctionnement classique, propose au minimum 6 lignes de charges et 4 lignes de produits.
- Réponds uniquement avec du JSON brut.

Format de sortie attendu
Retourne uniquement un JSON valide :
{
  "document_type": "budget_projet",
  "titre_document": "Budget previsionnel du projet",
  "budget_requis": true,
  "charges": [
    {
      "section": "Charges de personnel",
      "poste": "Coordinateur de projet (0,5 ETP sur 12 mois)",
      "montant_previsionnel": "18000",
      "statut": "confirme|a_completer|a_confirmer",
      "source": "string",
      "commentaire": "Note utile sur ce poste (justification, contrainte, source) — jamais le nom de la section"
    }
  ],
  "produits": [
    {
      "section": "Subventions publiques",
      "poste": "Subvention DRAC (demandée)",
      "montant_previsionnel": "string",
      "statut": "confirme|a_completer|a_confirmer",
      "source": "string",
      "commentaire": "string"
    }
  ],
  "totaux": {
    "charges": "string",
    "produits": "string",
    "equilibre": "ok|incomplet|a_confirmer"
  },
  "notes_budgetaires": ["string"],
  "points_a_completer": ["string"]
}
""".strip()


WF4C_SYSTEM_PROMPT = """
Rôle
Tu es un expert en préparation de pièces financières pour structures porteuses dans les dossiers de subvention et d’appels à projet.

Objectif
Déterminer si un budget prévisionnel de structure est requis par l’appel à projet. Si oui, produire une trame structurée distincte du budget projet, avec charges de structure et produits de structure. Si non, indiquer explicitement que ce livrable n’est pas requis.

Contexte
Certains appels à projet demandent non seulement un budget du projet, mais aussi un budget global de la structure porteuse, un compte de résultat prévisionnel, ou un prévisionnel annuel. Ce document doit rester séparé du budget projet.

Base de données et sources
Utilise uniquement :
- `wf2a.criteres`
- `wf2a.metadata`
- `wf2b.profil_client`
- `wf3.resultats_criteres`

Tu dois détecter :
- si le budget structure est explicitement demandé
- si des indices forts le rendent probable
- s’il manque encore une confirmation

Processus de travail
1. Parcourir les critères et obligations extraits de l’appel.
2. Identifier toute mention de budget structure, prévisionnel annuel, compte de résultat, budget global ou documents financiers de structure.
3. Si rien n’indique ce besoin, retourner `required = false`.
4. Si le besoin est explicite ou fortement probable, construire une trame distincte du budget projet.
5. Remplir uniquement ce qui est confirmé.
6. Laisser `A_COMPLETER` partout ailleurs.

Itération des données
- éliminer les doublons
- distinguer les obligations explicites des simples indices
- ne pas confondre budget projet et budget structure
- signaler tout manque de confirmation

Recherche croisée
Aucune recherche externe par défaut.
Si la mention est floue, utiliser `A_CONFIRMER`.

Questionnement préalable
Tu ne poses pas de question interactive. Si le besoin n’est pas entièrement établi, tu l’indiques dans `niveau_certitude`, `justification_requirement` et `points_a_completer`.

Contraintes / garde-fous
- Ne jamais confondre budget projet et budget structure.
- Si le besoin n’est pas clair, ne pas forcer artificiellement un budget structure.
- Si requis, fournir une trame exploitable.
- Si non requis, l’indiquer clairement.
- Raisonne en interne, sans exposer la chaîne de pensée.
- Réponds uniquement avec du JSON brut.

Format de sortie attendu
Retourne uniquement un JSON valide :
{
  "document_type": "budget_structure",
  "required": true,
  "niveau_certitude": "haut|moyen|bas",
  "justification_requirement": "string",
  "charges": [
    {
      "section": "Charges de personnel",
      "poste": "Libelle specifique et unique (ex: Directeur artistique 1 ETP)",
      "montant_previsionnel": "string",
      "statut": "confirme|a_completer|a_confirmer",
      "source": "string",
      "commentaire": "Note utile — jamais le nom de la section"
    }
  ],
  "produits": [
    {
      "section": "Subventions",
      "poste": "Libelle specifique et unique (ex: Subvention Region - fonctionnement)",
      "montant_previsionnel": "string",
      "statut": "confirme|a_completer|a_confirmer",
      "source": "string",
      "commentaire": "string"
    }
  ],
  "notes_budgetaires": ["string"],
  "points_a_completer": ["string"]
}
""".strip()


def _compress_wf3_for_wf4(wf3_analysis: dict[str, object]) -> dict[str, object]:
    """Compresse WF3 pour WF4 : garde uniquement les champs utiles à la rédaction.
    Supprime source_texte et donnee_utilisee (verbeux, déjà dans WF2a/WF2b).
    Réduit typiquement le payload de 30-50%.
    """
    resultats = []
    for item in wf3_analysis.get("resultats_criteres", []):
        if not isinstance(item, dict):
            continue
        resultats.append({
            "critere_id": str(item.get("critere_id", "")).strip(),
            "libelle": str(item.get("libelle", "")).strip(),
            "statut": str(item.get("statut", "")).strip(),
            "score": item.get("score", 0),
            "justification": str(item.get("justification", "")).strip(),
            "action_requise": str(item.get("action_requise", "")).strip(),
            "ecart": str(item.get("ecart", "")).strip(),
            "bloc_cible": str(item.get("bloc_cible", "")).strip(),
            "niveau_confiance": str(item.get("niveau_confiance", "")).strip(),
        })
    return {
        "score_global": wf3_analysis.get("score_global", 0),
        "statut_eligibilite": wf3_analysis.get("statut_eligibilite", ""),
        "niveau_confiance": wf3_analysis.get("niveau_confiance", ""),
        "resume_executif": wf3_analysis.get("resume_executif", ""),
        "sous_scores": wf3_analysis.get("sous_scores", {}),
        "resultats_criteres": resultats,
    }


def _compress_wf2a_for_wf4(wf2a_structured: dict[str, object]) -> dict[str, object]:
    """Compresse WF2a pour WF4 : supprime source_texte (long) des critères."""
    criteres = [
        {
            "libelle": str(item.get("libelle", "")).strip(),
            "detail": str(item.get("detail", "")).strip()[:300],  # tronque les details trop longs
            "categorie": str(item.get("categorie", "")).strip(),
            "domaine": str(item.get("domaine", "")).strip(),
            "est_critere_eliminatoire": bool(item.get("est_critere_eliminatoire", False)),
        }
        for item in wf2a_structured.get("criteres", [])
        if isinstance(item, dict)
    ]
    metadata = wf2a_structured.get("metadata", {})
    trame = {}
    if isinstance(metadata, dict):
        raw_trame = metadata.get("trame_livrable_attendue", {})
        if isinstance(raw_trame, dict) and (raw_trame.get("requise") or raw_trame.get("detectee")):
            trame = {
                "requise": bool(raw_trame.get("requise", False)),
                "confirmee": bool(raw_trame.get("confirmee", False)),
                "titre_trame": str(raw_trame.get("titre_trame", "")).strip(),
                "rubriques": [str(r).strip() for r in raw_trame.get("rubriques", []) if str(r).strip()],
            }
    return {
        "metadata": {
            "type_dossier_detecte": str(metadata.get("type_dossier_detecte", "")) if isinstance(metadata, dict) else "",
            "financeur_detecte": str(metadata.get("financeur_detecte", "")) if isinstance(metadata, dict) else "",
            "montant_max_detecte": str(metadata.get("montant_max_detecte", "")) if isinstance(metadata, dict) else "",
            "date_limite_detectee": str(metadata.get("date_limite_detectee", "")) if isinstance(metadata, dict) else "",
            "rubriques_attendues": list(metadata.get("rubriques_attendues", [])) if isinstance(metadata, dict) else [],
            "pieces_attendues": list(metadata.get("pieces_attendues", [])) if isinstance(metadata, dict) else [],
            "attentes_redactionnelles": list(metadata.get("attentes_redactionnelles", [])) if isinstance(metadata, dict) else [],
            "trame_livrable_attendue": trame,
        },
        "criteres": criteres,
    }


def _build_wf4_payload_dict(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
) -> dict[str, object]:
    wf2a_compressed = _compress_wf2a_for_wf4(wf2a_structured)
    criteres = wf2a_compressed["criteres"]

    structure_sources = _collect_field_sources(wf2b_structured.get("profil_client", {}))
    projet_sources = _collect_field_sources(wf2b_structured.get("donnees_projet", {}))
    critical_actions = _dedup_strings(
        [
            str(item.get("action_requise", "")).strip()
            for item in wf3_analysis.get("resultats_criteres", [])
            if isinstance(item, dict) and str(item.get("action_requise", "")).strip()
        ]
    )
    source_documents = _dedup_strings(
        [
            str(item.get("source_document", "")).strip()
            for item in wf2a_structured.get("criteres", [])
            if isinstance(item, dict) and str(item.get("source_document", "")).strip()
        ] + [e["source_document"] for e in structure_sources + projet_sources if e.get("source_document")]
    )

    return {
        "wf2a": wf2a_compressed,
        "wf2b": wf2b_structured,
        "wf3": _compress_wf3_for_wf4(wf3_analysis),
        "matiere_source": {
            "documents_sources": source_documents,
            "criteres_explicites": criteres,
            "structure_porteuse": structure_sources,
            "projet": projet_sources,
            "actions_critiques": critical_actions,
        },
    }


def _build_wf4_payload(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
) -> str:
    return json.dumps(
        _build_wf4_payload_dict(wf2a_structured, wf2b_structured, wf3_analysis),
        ensure_ascii=False,
        indent=2,
    )


def _looks_like_json_schema_payload(payload: dict[str, object]) -> bool:
    if not isinstance(payload, dict):
        return False
    schema_markers = {"type", "properties", "required", "title"}
    if schema_markers.issubset(set(payload.keys())):
        return True
    return False


WF4A_SECTION_SYSTEM_PROMPT = """
Rôle
Tu es un rédacteur senior en ingénierie de projets et financement public, spécialisé dans la rédaction de sections détaillées de dossiers de candidature à partir de matières documentaires déjà extraites.

Objectif
Rédiger une seule section de document de candidature, de manière plus développée, plus exploitable et plus précise qu'un simple résumé analytique. La section doit pouvoir être insérée telle quelle dans un document de présentation de projet.

Contexte
Tu reçois :
- le contexte global déjà extrait du dossier, du client et du projet
- une section cible avec son titre, son objectif, son contenu initial et son statut
- un type de section et des consignes métier spécifiques à cette section
- des attendus de l'appel à projet

Tu dois améliorer cette section sans inventer d'information. Si certaines données manquent, tu dois le signaler explicitement dans le texte avec `A_COMPLETER` ou `A_CONFIRMER`.

Base de données et sources
Tu t'appuies uniquement sur :
- `wf2a`
- `wf2b`
- `wf3`
- `matiere_source`
- `section_cible`

Tu privilégies les données internes fournies. Aucune recherche externe n'est autorisée dans cette tâche.

Processus de travail
1. Lire le titre et l'objectif de la section cible.
2. Lire le `section_type` et les `consignes_section` fournies dans les données d'entrée.
3. Identifier dans les données sources les éléments réellement pertinents pour cette section.
4. Réécrire la section sous forme d'un texte dense, fluide et exploitable.
5. Intégrer explicitement les données disponibles : objectifs, actions, publics, territoire, calendrier, moyens, partenaires, livrables, budget, contraintes, selon la section.
6. Respecter la logique attendue du type de section :
   - `resume` : vue d'ensemble concise mais rédigée, avec finalité du projet, public, territoire, temporalité et besoin
   - `structure` : crédibilité de la structure porteuse, compétences, ancrage, références et capacité de mise en œuvre
   - `contexte` : besoin, diagnostic, enjeux, problématique et réponse proposée
   - `actions` : contenu concret des actions, déroulé, activités prévues, logique d'intervention et articulation entre les temps du projet
   - `publics` : bénéficiaires, territoire, volume, ciblage et impact attendu
   - `methodologie` : déroulé opérationnel, phases, calendrier, gouvernance, suivi
   - `moyens` : équipe, partenaires, ressources techniques, répartition des rôles
   - `budget` : logique économique du projet, cohérence charges/produits, cofinancement, viabilité
   - `pieces` : points à compléter, annexes, justificatifs et validations requises
5. Si une information importante manque, l'indiquer proprement dans le texte.
6. Retourner une sortie courte mais substantielle : au moins un vrai paragraphe développé, voire plusieurs si la matière le permet.
7. Pour les sections majeures, viser un vrai brouillon exploitable de 2 a 4 paragraphes courts, pas un simple paragraphe d'ouverture.
8. Quand les sources sont partielles, utiliser les informations certaines pour decrire le cadre, puis faire apparaitre explicitement les points a completer.

Itération des données
Avant de rédiger :
- supprimer les doublons
- normaliser les formulations
- ne pas répéter mot pour mot le contenu initial
- conserver uniquement les éléments utiles à la section cible
- si une donnée est contradictoire, utiliser `A_CONFIRMER`

Recherche croisée
Pas de recherche croisée externe.

Questionnement préalable
Ne pose aucune question interactive. Si quelque chose manque, signale-le dans `points_de_vigilance` et dans le corps du texte.

Contraintes / garde-fous
- Ne fais aucune invention.
- N'utilise pas de phrases métacommentaires du type `A transformer`, `A retravailler`, `Resume initial`.
- Le texte doit ressembler à un brouillon de dossier, pas à une note interne.
- Garde un style professionnel, clair, rédigé et directement exploitable.
- Si la matière est riche, vise 8 à 12 phrases.
- Pour les sections `structure`, `contexte`, `publics`, `methodologie`, `moyens` et `budget`, vise en general 120 a 220 mots si les sources le permettent.
- Evite les sorties trop courtes : une section de 2 a 4 phrases sera consideree comme insuffisante si la matiere source contient deja plusieurs signaux exploitables.
- Evite les phrases télégraphiques de type `Titre : ...`, `Elements detectes : ...`, `Dates : ...` comme contenu principal.
- Pour les sections `contexte`, `methodologie`, `moyens` et `budget`, vise si possible 2 à 4 paragraphes courts plutôt qu'un bloc unique compact.
- Réponds uniquement avec du JSON brut.

Format de sortie attendu
{
  "titre": "string",
  "objectif_section": "string",
  "contenu_redige": "string",
  "statut": "redige|partiel|a_completer|a_confirmer",
  "sources_utilisees": ["string"],
  "points_de_vigilance": ["string"]
}
""".strip()


SECTION_TYPE_GUIDANCE = {
    "resume": {
        "keywords": ("resume",),
        "guidance": [
            "Produire une synthèse narrative du projet, pas une liste de constats.",
            "Inclure si possible le besoin traité, le public visé, le territoire, la durée, les actions principales et l'ambition globale.",
            "Le résultat doit pouvoir servir d'ouverture de dossier ou de note de synthèse.",
        ],
    },
    "structure": {
        "keywords": ("structure", "porteuse"),
        "guidance": [
            "Décrire la structure porteuse comme un acteur crédible : forme juridique, activité, ancrage territorial, références, équipe, capacités de gestion.",
            "Mettre en avant les éléments qui rassurent un financeur sur la capacité à porter le projet.",
            "Quand les références manquent, l'indiquer explicitement sans masquer le besoin de consolidation.",
        ],
    },
    "contexte": {
        "keywords": ("contexte", "besoin", "description"),
        "guidance": [
            "Décrire le problème ou besoin auquel répond le projet, puis la réponse proposée.",
            "Transformer les éléments détectés en texte rédigé avec logique de diagnostic et de justification.",
            "Faire ressortir les enjeux pour le territoire, le secteur ou les bénéficiaires.",
        ],
    },
    "actions": {
        "keywords": ("action", "actions prevues", "programme", "activite", "activites"),
        "guidance": [
            "Décrire concrètement les actions prévues, leur enchaînement, leur contenu et leur finalité.",
            "Faire apparaître ce qui sera réellement mis en oeuvre : ateliers, accompagnements, temps collectifs, production, diffusion, restitution, selon les sources.",
            "Éviter les formulations vagues : chaque paragraphe doit préciser ce qui sera fait, pour qui, comment et dans quel cadre.",
        ],
    },
    "publics": {
        "keywords": ("public", "beneficiaire", "territoire"),
        "guidance": [
            "Préciser qui sont les bénéficiaires, où se déroule le projet et quels effets sont attendus.",
            "Si possible, évoquer le ciblage, le volume, les modalités de mobilisation et la valeur pour le territoire.",
            "Si le volume ou les critères de ciblage manquent, écrire A_COMPLETER dans le texte de manière propre.",
        ],
    },
    "methodologie": {
        "keywords": ("methodologie", "mise en oeuvre", "calendrier"),
        "guidance": [
            "Décrire un déroulé opérationnel en phases ou étapes claires.",
            "Relier explicitement les dates, jalons, actions et séquences d'exécution.",
            "Faire apparaître préparation, réalisation, suivi, évaluation et restitution si les sources le permettent.",
        ],
    },
    "moyens": {
        "keywords": ("moyens", "partenariat"),
        "guidance": [
            "Décrire l'équipe mobilisée, les moyens techniques, les partenaires et la répartition des rôles.",
            "Mettre en avant les ressources concrètes qui rendent le projet faisable.",
            "Ne pas se limiter à citer des noms : expliquer à quoi servent ces moyens dans le projet.",
        ],
    },
    "budget": {
        "keywords": ("budget", "financement"),
        "guidance": [
            "Présenter la logique financière du projet : grandes charges, produits, cofinancement, subvention sollicitée, équilibre visé.",
            "Faire apparaître les contraintes de l'appel si elles sont détectées : plafond, taux, autofinancement, devis, justificatifs.",
            "Le texte doit accompagner la trame budget, pas répéter simplement des postes.",
        ],
    },
    "pieces": {
        "keywords": ("piece", "annexe", "completer"),
        "guidance": [
            "Transformer la liste des manques en checklist structurée et actionnable.",
            "Faire ressortir les pièces à produire, les validations à obtenir et les zones à confirmer.",
            "Le résultat doit aider à finaliser le dossier avant dépôt.",
        ],
    },
}


def infer_presentation_section_type(title: str) -> str:
    normalized = title.lower().strip()
    if "action" in normalized or "actions prevues" in normalized:
        return "actions"
    for section_type, config in SECTION_TYPE_GUIDANCE.items():
        if any(keyword in normalized for keyword in config["keywords"]):
            return section_type
    return "contexte"


def get_section_guidance(section_type: str) -> list[str]:
    config = SECTION_TYPE_GUIDANCE.get(section_type, {})
    return list(config.get("guidance", []))


def _resolve_wf4a_overrides(provider_override: str | None) -> tuple[str | None, str | None]:
    """Retourne (provider_override, model_override) optimisés pour WF4A.

    WF4A = structuration JSON de données déjà extraites.
    Pas besoin de raisonnement profond → on évite le mode thinking DeepSeek
    qui ajoute 3-4 min de réflexion pour aucun gain sur cette tâche.
    Priorité : Google (rapide) > DeepSeek non-thinking > provider par défaut.
    """
    if provider_override:
        # Respect du provider explicite, mais on désactive quand même le thinking DeepSeek
        if provider_override == "deepseek":
            return "deepseek", "deepseek-v4-pro-non-thinking"
        return provider_override, None

    google_settings = load_llm_settings(provider_override="google")
    if google_settings.is_configured:
        return "google", None

    # Provider actif = DeepSeek avec thinking → force non-thinking
    active_settings = load_llm_settings()
    if active_settings.provider == "deepseek":
        return "deepseek", "deepseek-v4-pro-non-thinking"

    return None, None


def wf4b_has_dedicated_agent() -> bool:
    mistral_settings = load_llm_settings(provider_override="mistral")
    return bool(mistral_settings.mistral_api_key and mistral_settings.mistral_budget_project_agent_id.strip())


def request_wf4a_llm_payload(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    wf4a_provider_override, wf4a_model_override = _resolve_wf4a_overrides(provider_override)
    # model_override explicite prime sur la résolution automatique non-thinking
    effective_model_override = model_override or wf4a_model_override
    llm_result = call_llm_message(
        WF4A_SYSTEM_PROMPT,
        _build_wf4_payload(wf2a_structured, wf2b_structured, wf3_analysis),
        max_tokens=8500,
        provider_override=wf4a_provider_override,
        model_override=effective_model_override,
    )
    if not llm_result.get("ok"):
        return {
            "ok": False,
            "error": llm_result.get("error", "llm_error"),
            "payload": None,
            "usage": llm_result.get("usage", {}),
            "provider": llm_result.get("provider", ""),
            "model": llm_result.get("model", ""),
            "quota_exhausted": is_google_quota_exhausted_error(llm_result.get("error", "")),
        }

    parsed_payload, parse_error = parse_json_response(str(llm_result.get("text", "")))
    repair_usage: dict[str, object] = {}
    repair_model = ""
    # JSON truncation (Unterminated string) cannot be fixed by repair — skip it to save 30-60s
    is_truncated = parse_error is not None and "Unterminated" in str(parse_error)
    if parse_error is not None and not is_truncated and not is_google_quota_exhausted_error(parse_error):
        repair_result = repair_json_response_with_llm(
            str(llm_result.get("text", "")),
            provider_override=wf4a_provider_override,
            model_override=effective_model_override,
        )
        if repair_result.get("ok") and isinstance(repair_result.get("payload"), dict):
            parsed_payload = repair_result["payload"]
            parse_error = None
        repair_usage = repair_result.get("usage", {}) if isinstance(repair_result.get("usage", {}), dict) else {}
        repair_model = str(repair_result.get("model", "")).strip()
    if parse_error is None and isinstance(parsed_payload, dict) and _looks_like_json_schema_payload(parsed_payload):
        parse_error = "schema_reproduit_au_lieu_des_donnees"
    if (
        parse_error is None
        and isinstance(parsed_payload, dict)
        and not _payload_has_substantive_presentation_content(parsed_payload)
    ) or is_truncated:
        retry_prompt = (
            _build_wf4_payload(wf2a_structured, wf2b_structured, wf3_analysis)
            + "\n\nConsigne renforcee : la premiere version etait trop succincte. "
            "Retourne un JSON final avec des sections plus developpees, plus concretes et plus exploitables. "
            "Pour chaque section majeure, vise plutot 120 a 220 mots si la matiere le permet, en paragraphes rediges et non en formule minimale."
        )
        retry_result = call_llm_message(
            WF4A_SYSTEM_PROMPT,
            retry_prompt,
            max_tokens=9500,
            provider_override=wf4a_provider_override,
            model_override=effective_model_override,
        )
        if retry_result.get("ok"):
            retry_payload, retry_error = parse_json_response(str(retry_result.get("text", "")))
            retry_is_truncated = retry_error is not None and "Unterminated" in str(retry_error)
            if retry_error is not None and not retry_is_truncated:
                repair_result = repair_json_response_with_llm(
                    str(retry_result.get("text", "")),
                    provider_override=wf4a_provider_override,
                    model_override=effective_model_override,
                )
                if repair_result.get("ok") and isinstance(repair_result.get("payload"), dict):
                    retry_payload = repair_result["payload"]
                    retry_error = None
            if retry_error is None and isinstance(retry_payload, dict) and _payload_has_substantive_presentation_content(retry_payload):
                parsed_payload = retry_payload
                llm_result = retry_result
                parse_error = None
                is_truncated = False

    return {
        "ok": parse_error is None and parsed_payload is not None,
        "error": parse_error,
        "payload": parsed_payload,
        "usage": {
            **(llm_result.get("usage", {}) if isinstance(llm_result.get("usage", {}), dict) else {}),
            **({"json_repair_model": repair_model} if repair_model else {}),
            **({"json_repair_used": True} if repair_usage or repair_model else {}),
        },
        "provider": llm_result.get("provider", ""),
        "model": llm_result.get("model", ""),
        "raw_text": llm_result.get("text", ""),
        "quota_exhausted": is_google_quota_exhausted_error(parse_error),
    }


def request_wf4b_llm_payload(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    payload_text = _build_wf4_payload(wf2a_structured, wf2b_structured, wf3_analysis)
    agent_settings = load_llm_settings(provider_override="mistral")
    budget_project_agent_id = agent_settings.mistral_budget_project_agent_id.strip()

    if agent_settings.mistral_api_key and budget_project_agent_id:
        agent_user_prompt = (
            "Produis uniquement les donnees finales du budget projet, conformes au schema JSON de l'agent. "
            "Ne recopie jamais le schema. Ne retourne jamais `type`, `properties`, `required` ou `title`.\n\n"
            f"BUNDLE:\n{payload_text}"
        )
        llm_result = call_mistral_agent_message(
            budget_project_agent_id,
            agent_user_prompt,
            max_tokens=5000,
            provider_override="mistral",
        )
    else:
        settings = load_llm_settings(provider_override=provider_override, model_override=model_override)
        llm_result = call_llm_message(
            WF4B_SYSTEM_PROMPT,
            payload_text,
            max_tokens=5000,
            provider_override=provider_override,
            model_override=model_override,
        )
    if not llm_result.get("ok"):
        return {
            "ok": False,
            "error": llm_result.get("error", "llm_error"),
            "payload": None,
            "usage": llm_result.get("usage", {}),
            "provider": llm_result.get("provider", ""),
            "model": llm_result.get("model", ""),
            "agent_id": budget_project_agent_id if budget_project_agent_id else "",
        }

    parsed_payload, parse_error = parse_json_response(str(llm_result.get("text", "")))
    if parse_error is not None:
        repair_result = repair_json_response_with_llm(
            str(llm_result.get("text", "")),
            provider_override=provider_override,
            model_override=model_override,
        )
        if repair_result.get("ok") and isinstance(repair_result.get("payload"), dict):
            parsed_payload = repair_result["payload"]
            parse_error = None
    return {
        "ok": parse_error is None and parsed_payload is not None,
        "error": parse_error,
        "payload": parsed_payload,
        "usage": llm_result.get("usage", {}),
        "provider": llm_result.get("provider", ""),
        "model": llm_result.get("model", ""),
        "raw_text": llm_result.get("text", ""),
        "agent_id": budget_project_agent_id if budget_project_agent_id else "",
    }


def request_wf4c_llm_payload(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    llm_result = call_llm_message(
        WF4C_SYSTEM_PROMPT,
        _build_wf4_payload(wf2a_structured, wf2b_structured, wf3_analysis),
        max_tokens=3500,
        provider_override=provider_override,
        model_override=model_override,
    )
    if not llm_result.get("ok"):
        return {
            "ok": False,
            "error": llm_result.get("error", "llm_error"),
            "payload": None,
            "usage": llm_result.get("usage", {}),
            "provider": llm_result.get("provider", ""),
            "model": llm_result.get("model", ""),
        }

    parsed_payload, parse_error = parse_json_response(str(llm_result.get("text", "")))
    if parse_error is not None:
        repair_result = repair_json_response_with_llm(
            str(llm_result.get("text", "")),
            provider_override=provider_override,
            model_override=model_override,
        )
        if repair_result.get("ok") and isinstance(repair_result.get("payload"), dict):
            parsed_payload = repair_result["payload"]
            parse_error = None
    return {
        "ok": parse_error is None and parsed_payload is not None,
        "error": parse_error,
        "payload": parsed_payload,
        "usage": llm_result.get("usage", {}),
        "provider": llm_result.get("provider", ""),
        "model": llm_result.get("model", ""),
        "raw_text": llm_result.get("text", ""),
    }


def request_wf4a_section_payload(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    wf3_analysis: dict[str, object],
    section_payload: dict[str, object],
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    wf4a_provider_override, wf4a_model_override = _resolve_wf4a_overrides(provider_override)
    effective_model_override = model_override or wf4a_model_override
    payload = _build_wf4_payload_dict(wf2a_structured, wf2b_structured, wf3_analysis)
    payload["section_cible"] = section_payload

    llm_result = call_llm_message(
        WF4A_SECTION_SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=False, indent=2),
        max_tokens=3200,
        provider_override=wf4a_provider_override,
        model_override=effective_model_override,
    )
    if not llm_result.get("ok"):
        return {
            "ok": False,
            "error": llm_result.get("error", "llm_error"),
            "payload": None,
            "usage": llm_result.get("usage", {}),
            "provider": llm_result.get("provider", ""),
            "model": llm_result.get("model", ""),
            "quota_exhausted": is_google_quota_exhausted_error(llm_result.get("error", "")),
        }

    parsed_payload, parse_error = parse_json_response(str(llm_result.get("text", "")))
    if parse_error is not None and not is_google_quota_exhausted_error(parse_error):
        repair_result = repair_json_response_with_llm(
            str(llm_result.get("text", "")),
            provider_override=wf4a_provider_override,
            model_override=effective_model_override,
        )
        if repair_result.get("ok") and isinstance(repair_result.get("payload"), dict):
            parsed_payload = repair_result["payload"]
            parse_error = None
    section_type = str(section_payload.get("section_type", "")).strip() or infer_presentation_section_type(
        str(section_payload.get("titre", "")).strip()
    )
    if (
        parse_error is None
        and isinstance(parsed_payload, dict)
        and not _payload_has_substantive_presentation_content(
            parsed_payload,
            section_type=section_type,
        )
    ):
        retry_payload = dict(payload)
        retry_payload["consigne_renforcee"] = (
            "La premiere version etait trop succincte. Developpe davantage cette section en 2 a 4 paragraphes courts, "
            "avec des elements concrets et exploitables. Si des informations manquent, signale-les dans la prose sans reduire la section a une formule minimale."
        )
        retry_result = call_llm_message(
            WF4A_SECTION_SYSTEM_PROMPT,
            json.dumps(retry_payload, ensure_ascii=False, indent=2),
            max_tokens=3600,
            provider_override=wf4a_provider_override,
            model_override=effective_model_override,
        )
        if retry_result.get("ok"):
            retry_parsed_payload, retry_parse_error = parse_json_response(str(retry_result.get("text", "")))
            if retry_parse_error is not None:
                repair_result = repair_json_response_with_llm(
                    str(retry_result.get("text", "")),
                    provider_override=wf4a_provider_override,
                    model_override=effective_model_override,
                )
                if repair_result.get("ok") and isinstance(repair_result.get("payload"), dict):
                    retry_parsed_payload = repair_result["payload"]
                    retry_parse_error = None
            if retry_parse_error is None and isinstance(retry_parsed_payload, dict) and _payload_has_substantive_presentation_content(
                retry_parsed_payload,
                section_type=section_type,
            ):
                parsed_payload = retry_parsed_payload
                llm_result = retry_result
                parse_error = None
    return {
        "ok": parse_error is None and parsed_payload is not None,
        "error": parse_error,
        "payload": parsed_payload,
        "usage": llm_result.get("usage", {}),
        "provider": llm_result.get("provider", ""),
        "model": llm_result.get("model", ""),
        "raw_text": llm_result.get("text", ""),
        "quota_exhausted": is_google_quota_exhausted_error(parse_error),
    }
