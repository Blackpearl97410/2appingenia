from __future__ import annotations

import json

from app.services.llm_client import call_llm_message, parse_json_response
from app.services.wf2 import summarize_wf2b_client_profile, summarize_wf2b_project_data


WF3_SYSTEM_PROMPT = """
Tu es un analyste expert en financement public.
Ta mission est de comparer critere par critere un dossier de financement (WF2a)
au profil client et aux donnees projet (WF2b), et de produire un scoring structure.

Regles strictes :
- travaille critere par critere, sans exception
- ne deduis pas au-dela des preuves textuelles fournies
- si une donnee est absente ou floue, note le critere "manquant" ou "a_confirmer"
- reponds uniquement en JSON brut, sans markdown ni commentaire

Statuts de ligne autorises (un seul par critere) :
  valide        → preuve claire et explicite dans les documents
  a_confirmer   → indice present mais incomplet ou ambigu
  manquant      → aucune donnee exploitable trouvee
  non_valide    → contradiction explicite ou critere bloquant non satisfait

Statuts globaux autorises :
  compatible            → score >= 75 et aucun critere non_valide ni manquant bloquant
  a confirmer           → score entre 50 et 74
  partiellement compatible → score entre 30 et 49
  non compatible        → score < 30 ou au moins un critere bloquant non_valide

Niveaux de confiance autorises : haut | moyen | bas

Regles de scoring par statut (respecter ces fourchettes) :
  valide        → score entre 80 et 100
  a_confirmer   → score entre 50 et 79
  manquant      → score entre 10 et 49
  non_valide    → score entre 0 et 9
  critere bloquant + non_valide → score = 0 obligatoirement

sous_scores : calculer la moyenne des scores de chaque groupe (client / projet / mixte).
fiabilite_documentaire : 80 si niveau_confiance=haut, 55 si moyen, 30 si bas.

Format JSON attendu :
{
  "score_global": 72,
  "statut_eligibilite": "a confirmer",
  "niveau_confiance": "moyen",
  "sous_scores": {
    "bloc_client": 85,
    "bloc_projet": 60,
    "bloc_mixte": 70,
    "fiabilite_documentaire": 55
  },
  "resume_executif": "Synthese en 2-3 phrases.",
  "resultats_criteres": [
    {
      "critere_id": "critere_1",
      "libelle": "Eligibilite association Loi 1901",
      "categorie": "obligatoire",
      "domaine": "administratif",
      "source_document": "cahier_des_charges.pdf",
      "source_texte": "Seules les associations declarees...",
      "bloc_cible": "client",
      "statut": "valide",
      "score": 95,
      "justification": "La structure est une association Loi 1901 declaree, critere pleinement satisfait.",
      "ecart": "",
      "action_requise": "Aucune action immediate.",
      "donnee_utilisee": "forme_juridique = association",
      "niveau_confiance": "haut",
      "necessite_validation": false
    }
  ]
}
""".strip()


def _compress_wf2b_for_wf3(wf2b_structured: dict[str, object]) -> dict[str, object]:
    """Compresse WF2b pour reduire les tokens envoyes au LLM WF3.
    Ne transmet que les valeurs utiles, pas les metadonnees internes.
    """
    profil = summarize_wf2b_client_profile(wf2b_structured)
    projet = summarize_wf2b_project_data(wf2b_structured)
    metadata = wf2b_structured.get("metadata", {})
    return {
        "profil_client": profil,
        "donnees_projet": projet,
        "documents_client": metadata.get("documents_client_sources", []),
        "documents_projet": metadata.get("documents_projet_sources", []),
    }


def _compress_wf2a_for_wf3(wf2a_structured: dict[str, object]) -> dict[str, object]:
    """Compresse WF2a : ne transmet que les champs utiles au matching WF3."""
    criteres = wf2a_structured.get("criteres", [])
    compressed_criteres = []
    for c in criteres:
        compressed_criteres.append({
            "critere_id": c.get("id_local", ""),
            "libelle": c.get("libelle", ""),
            "detail": c.get("detail", ""),
            "categorie": c.get("categorie", ""),
            "domaine": c.get("domaine", ""),
            "source_document": c.get("source_document", ""),
            "est_critere_eliminatoire": c.get("est_critere_eliminatoire", False),
        })
    metadata = wf2a_structured.get("metadata", {})
    return {
        "type_dossier": metadata.get("type_dossier_detecte", ""),
        "financeur": metadata.get("financeur_detecte", ""),
        "montant_max": metadata.get("montant_max_detecte", ""),
        "date_limite": metadata.get("date_limite_detectee", ""),
        "criteres": compressed_criteres,
    }


def build_wf3_user_prompt(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    global_context_bridge: dict[str, str] | None = None,
) -> str:
    compressed_wf2a = _compress_wf2a_for_wf3(wf2a_structured)
    compressed_wf2b = _compress_wf2b_for_wf3(wf2b_structured)

    nb_criteres = len(compressed_wf2a.get("criteres", []))
    payload = {
        "instruction": (
            f"Analyse les {nb_criteres} criteres du dossier ci-dessous "
            "et compare-les au profil client et aux donnees projet. "
            "Retourne le JSON demande avec un resultat pour chaque critere."
        ),
        "dossier_criteres": compressed_wf2a,
        "profil_client_et_projet": compressed_wf2b,
        "contexte_global": global_context_bridge or {},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def request_wf3_llm_payload(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    global_context_bridge: dict[str, str] | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    user_prompt = build_wf3_user_prompt(wf2a_structured, wf2b_structured, global_context_bridge)
    llm_result = call_llm_message(
        WF3_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=6000,
        provider_override=provider_override,
        model_override=model_override,
    )

    if not llm_result.get("ok"):
        return {
            "ok": False,
            "mode": "llm_direct_python",
            "error": llm_result.get("error", "llm_error"),
            "payload": None,
            "usage": llm_result.get("usage", {}),
        }

    parsed_payload, parse_error = parse_json_response(str(llm_result.get("text", "")))
    return {
        "ok": parse_error is None and parsed_payload is not None,
        "mode": "llm_direct_python",
        "error": parse_error,
        "payload": parsed_payload,
        "usage": llm_result.get("usage", {}),
        "raw_text": llm_result.get("text", ""),
        "provider": llm_result.get("provider", ""),
        "model": llm_result.get("model", ""),
    }
