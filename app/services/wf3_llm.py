from __future__ import annotations

import json

from app.services.llm_client import call_anthropic_message, parse_json_response


WF3_SYSTEM_PROMPT = """
Tu es un analyste expert en financement public.
Ta mission est de comparer des criteres dossier a un profil client et a des donnees projet.

Regles :
- travaille critere par critere
- ne deduis pas au-dela des preuves fournies
- utilise uniquement ces statuts de ligne :
  - valide
  - a_confirmer
  - manquant
  - non_valide
- utilise uniquement ces statuts globaux :
  - compatible
  - a confirmer
  - partiellement compatible
  - non compatible
- utilise uniquement ces niveaux de confiance :
  - haut
  - moyen
  - bas
- reponds uniquement en JSON brut

Format attendu :
{
  "score_global": 0,
  "statut_eligibilite": "a confirmer",
  "niveau_confiance": "moyen",
  "sous_scores": {
    "bloc_client": 0,
    "bloc_projet": 0,
    "bloc_mixte": 0,
    "fiabilite_documentaire": 0
  },
  "resume_executif": "texte",
  "resultats_criteres": [
    {
      "critere_id": "critere_1",
      "libelle": "texte",
      "categorie": "obligatoire",
      "domaine": "administratif",
      "source_document": "nom.ext",
      "source_texte": "extrait exact",
      "bloc_cible": "client",
      "statut": "valide",
      "score": 90,
      "justification": "texte",
      "ecart": "",
      "action_requise": "texte",
      "donnee_utilisee": "texte",
      "niveau_confiance": "moyen",
      "necessite_validation": true
    }
  ]
}
""".strip()


def build_wf3_user_prompt(wf2a_structured: dict[str, object], wf2b_structured: dict[str, object], global_context_bridge: dict[str, str] | None = None) -> str:
    payload = {
        "wf2a": wf2a_structured,
        "wf2b": wf2b_structured,
        "contexte_global": global_context_bridge or {},
    }
    return (
        "Compare les donnees suivantes et retourne le JSON demande.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def request_wf3_llm_payload(
    wf2a_structured: dict[str, object],
    wf2b_structured: dict[str, object],
    global_context_bridge: dict[str, str] | None = None,
) -> dict[str, object]:
    user_prompt = build_wf3_user_prompt(wf2a_structured, wf2b_structured, global_context_bridge)
    llm_result = call_anthropic_message(WF3_SYSTEM_PROMPT, user_prompt, max_tokens=3000)

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
        "model": llm_result.get("model", ""),
    }
