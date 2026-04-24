from __future__ import annotations

from app.services.llm_client import call_anthropic_message, parse_json_response
from app.services.wf2 import VALID_CONFIDENCE, extract_document_payloads


WF2B_SYSTEM_PROMPT = f"""
Tu es un analyste expert en financement public.
Ta mission est d'extraire un profil client et des donnees projet a partir de documents heterogenes.

Regles :
- ne deduis pas ce qui n'est pas explicite
- cite toujours un document source et un extrait de texte
- utilise uniquement ces niveaux de confiance : {", ".join(sorted(VALID_CONFIDENCE))}
- reponds uniquement avec du JSON brut, sans markdown

Format attendu :
{{
  "profil_client": {{
    "nom_structure": {{
      "value": "texte ou Non detecte",
      "source_document": "nom_fichier.ext",
      "source_texte": "extrait exact",
      "niveau_confiance": "moyen",
      "necessite_validation": true
    }},
    "forme_juridique": {{ "...": "..." }},
    "siret": {{ "...": "..." }},
    "email": {{ "...": "..." }},
    "telephone": {{ "...": "..." }},
    "activites": [
      {{
        "value": "activite detectee",
        "source_document": "nom_fichier.ext",
        "source_texte": "extrait exact",
        "niveau_confiance": "moyen",
        "necessite_validation": true
      }}
    ]
  }},
  "donnees_projet": {{
    "titre_projet": {{ "...": "..." }},
    "montant_detecte": {{ "...": "..." }},
    "dates_detectees": [
      {{
        "value": "date ou periode",
        "source_document": "nom_fichier.ext",
        "source_texte": "extrait exact",
        "niveau_confiance": "moyen",
        "necessite_validation": true
      }}
    ],
    "elements_detectes": [
      {{
        "value": "objectif, action, public, livrable ou budget",
        "source_document": "nom_fichier.ext",
        "source_texte": "extrait exact",
        "niveau_confiance": "moyen",
        "necessite_validation": true
      }}
    ]
  }},
  "metadata": {{
    "mode_extraction": "llm_direct_python",
    "documents_client_sources": ["a.ext"],
    "documents_projet_sources": ["b.ext"]
  }}
}}
""".strip()


def _format_payloads(title: str, uploaded_files) -> str:
    payloads = extract_document_payloads(uploaded_files)
    blocks = []
    for payload in payloads:
        text = payload["text"].strip()[:60000]
        if not text:
            continue
        blocks.append(f"===== {title} | DOCUMENT: {payload['document_name']} =====\n{text}")
    return "\n\n".join(blocks)


def build_wf2b_user_prompt(client_files, project_files) -> str:
    client_block = _format_payloads("CLIENT", client_files)
    project_block = _format_payloads("PROJET", project_files)
    return (
        "Analyse les documents ci-dessous et retourne le JSON demandé.\n\n"
        f"{client_block}\n\n{project_block}"
    ).strip()


def request_wf2b_llm_payload(client_files, project_files) -> dict[str, object]:
    user_prompt = build_wf2b_user_prompt(client_files, project_files)
    llm_result = call_anthropic_message(WF2B_SYSTEM_PROMPT, user_prompt, max_tokens=4000)

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
