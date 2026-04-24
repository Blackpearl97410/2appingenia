from __future__ import annotations

from app.services.llm_client import call_anthropic_message, parse_json_response
from app.services.wf2 import VALID_CATEGORIES, VALID_CONFIDENCE, VALID_DOMAINS, extract_document_payloads


WF2A_SYSTEM_PROMPT = f"""
Tu es un analyste expert en financement public.
Ta mission est d'extraire les criteres d'un dossier de financement sous forme de JSON structure.

Regles :
- ne deduis pas ce qui n'est pas explicite
- cite toujours le document source et un extrait de texte
- retourne entre 5 et 30 criteres si possible
- privilegie les criteres bloquants et obligatoires
- utilise uniquement ces categories : {", ".join(sorted(VALID_CATEGORIES))}
- utilise uniquement ces domaines : {", ".join(sorted(VALID_DOMAINS))}
- utilise uniquement ces niveaux de confiance : {", ".join(sorted(VALID_CONFIDENCE))}
- reponds uniquement avec du JSON brut, sans markdown

Format attendu :
{{
  "criteres": [
    {{
      "categorie": "obligatoire",
      "domaine": "administratif",
      "libelle": "Nom court du critere",
      "detail": "detail exact",
      "source_document": "nom_fichier.ext",
      "source_texte": "extrait exact",
      "est_piece_exigee": false,
      "est_critere_eliminatoire": false,
      "niveau_confiance": "moyen",
      "necessite_validation": true
    }}
  ],
  "metadata": {{
    "type_dossier_detecte": "aap",
    "financeur_detecte": "nom ou null",
    "montant_max_detecte": "texte ou null",
    "date_limite_detectee": "texte ou null",
    "nb_criteres_extraits": 0
  }}
}}
""".strip()


def build_wf2a_user_prompt(dossier_files) -> str:
    payloads = extract_document_payloads(dossier_files)
    document_blocks = []
    for payload in payloads:
        text = payload["text"].strip()[:80000]
        if not text:
            continue
        document_blocks.append(
            f"===== DOCUMENT: {payload['document_name']} =====\n{text}"
        )
    combined = "\n\n".join(document_blocks)
    return (
        "Analyse les documents ci-dessous et retourne le JSON demandé.\n\n"
        f"{combined}"
    )


def request_wf2a_llm_payload(dossier_files) -> dict[str, object]:
    user_prompt = build_wf2a_user_prompt(dossier_files)
    llm_result = call_anthropic_message(WF2A_SYSTEM_PROMPT, user_prompt, max_tokens=6000)

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
