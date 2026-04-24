from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.services.metadata import extract_text_metadata
from app.services.parsers import get_uploaded_bytes
from app.services.supabase_bridge import build_storage_path, create_supabase_client, ensure_private_documents_bucket, load_supabase_settings
from app.services.wf2 import extract_document_payloads
from app.services.client_manager import get_operator_id


def _sanitize_text(value: object) -> str:
    return str(value or "").replace("\x00", "").strip()


def _extract_first_numeric(value: str) -> float | None:
    if not value:
        return None
    cleaned = value.replace("\u202f", " ").replace("€", " ").replace("euros", " ").replace("euro", " ")
    cleaned = re.sub(r"[^0-9,.\s-]", "", cleaned)
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        return None
    cleaned = cleaned.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _map_analysis_status(value: str) -> str:
    mapping = {
        "compatible": "eligible",
        "a confirmer": "a_confirmer",
        "partiellement compatible": "partiel",
        "non compatible": "non_eligible",
    }
    return mapping.get(value, "a_confirmer")


def _normalize_type_financement(raw: str) -> str:
    """Normalise une valeur brute extraite vers les valeurs acceptées par le CHECK PostgreSQL."""
    VALID = {"marche_public", "subvention", "aap", "ami", "autre"}
    if not raw:
        return "autre"
    cleaned = raw.lower().strip()
    # correspondances directes
    if cleaned in VALID:
        return cleaned
    # correspondances par mots-clés
    if any(k in cleaned for k in ("marche", "marché", "public", "ao ", "appel d'offres")):
        return "marche_public"
    if any(k in cleaned for k in ("subvention", "aide", "grant")):
        return "subvention"
    if any(k in cleaned for k in ("aap", "appel à projet", "appel a projet")):
        return "aap"
    if any(k in cleaned for k in ("ami", "appel à manifestation", "appel a manifestation")):
        return "ami"
    return "autre"


def _normalize_niveau_confiance(raw: str) -> str:
    """Normalise vers haut/moyen/bas."""
    VALID = {"haut", "moyen", "bas"}
    cleaned = (raw or "").lower().strip()
    if cleaned in VALID:
        return cleaned
    if cleaned in ("high", "eleve", "élevé", "fort"):
        return "haut"
    if cleaned in ("low", "faible"):
        return "bas"
    return "moyen"


def _map_result_status(value: str) -> str:
    mapping = {
        "valide": "valide",
        "a_confirmer": "a_verifier",
        "manquant": "manquant",
        "non_valide": "non_valide",
        "partiel": "partiel",
    }
    return mapping.get(value, "a_verifier")


def _prefill_source(field: dict[str, Any]) -> str:
    onglet = str(field.get("onglet", "")).lower()
    if onglet in {"structure", "contact"}:
        return "profil_client"
    if onglet == "projet":
        return "extraction_projet"
    return "document"


def _upload_document_and_insert_record(client, bucket_name: str, uploaded_file, document_type: str, dossier_id: str | None, client_id: str | None) -> dict[str, Any]:
    document_id = str(uuid4())
    file_bytes = get_uploaded_bytes(uploaded_file)
    storage_path = build_storage_path(uploaded_file.name, document_type, document_id)
    client.storage.from_(bucket_name).upload(storage_path, file_bytes)

    payload = extract_document_payloads([uploaded_file])[0]
    text = _sanitize_text(payload.get("text", ""))
    metadata = extract_text_metadata(text, uploaded_file.name) if text else {}
    row = {
        "id": document_id,
        "dossier_id": dossier_id,
        "client_id": client_id,
        "nom_fichier": uploaded_file.name,
        "type_fichier": str(uploaded_file.name).split(".")[-1].lower() if "." in uploaded_file.name else "unknown",
        "taille_octets": len(file_bytes),
        "storage_path": storage_path,
        "type_document": document_type,
        "texte_resume": text[:500] if text else None,
        "structure_extraite_path": None,
        "texte_extrait_path": None,
        "extraction_statut": "termine",
        "description": _sanitize_text(metadata.get("Type probable", "")),
    }
    inserted = client.table("documents").insert(row).execute()
    return inserted.data[0]


def persist_pipeline_outputs(
    dossier_files,
    client_files,
    project_files,
    pipeline_outputs: dict[str, object],
    selected_client_id: str | None = None,
) -> dict[str, object]:
    ensure_private_documents_bucket()
    settings = load_supabase_settings()
    client = create_supabase_client(use_service_role=True)
    if client is None:
        return {"ok": False, "error": "client_supabase_non_configure"}

    try:
        return _persist_pipeline_outputs_inner(
            client, settings,
            dossier_files, client_files, project_files,
            pipeline_outputs,
            selected_client_id=selected_client_id,
        )
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def _persist_pipeline_outputs_inner(
    client, settings,
    dossier_files, client_files, project_files,
    pipeline_outputs,
    selected_client_id: str | None = None,
):
    operator_id = get_operator_id()
    wf2a = pipeline_outputs["wf2a"]
    wf2b = pipeline_outputs["wf2b"]
    wf3 = pipeline_outputs["wf3"]
    wf4 = pipeline_outputs["wf4"]
    execution = pipeline_outputs.get("execution", {})

    profil_client = wf2b.get("profil_client", {})
    donnees_projet = wf2b.get("donnees_projet", {})
    wf2a_metadata = wf2a.get("metadata", {})

    # ── Résolution du client ────────────────────────────────────────────────
    if selected_client_id:
        # Client explicitement choisi dans l'interface → on le récupère et on
        # enrichit ses données avec ce qu'on extrait des documents.
        existing_rows = client.table("clients").select("*").eq("id", selected_client_id).limit(1).execute().data
        if not existing_rows:
            raise ValueError(f"Client introuvable : {selected_client_id}")
        client_row = existing_rows[0]
        # Enrichissement optionnel (ne jamais écraser les valeurs déjà renseignées)
        update_payload: dict[str, object] = {}
        extracted_email = _sanitize_text(profil_client.get("email", {}).get("value", ""))
        extracted_tel = _sanitize_text(profil_client.get("telephone", {}).get("value", ""))
        if extracted_email and not client_row.get("contact_email"):
            update_payload["contact_email"] = extracted_email
        if extracted_tel and not client_row.get("contact_telephone"):
            update_payload["contact_telephone"] = extracted_tel
        if update_payload:
            client_row = client.table("clients").update(update_payload).eq("id", selected_client_id).execute().data[0]
    else:
        # Fallback : UPSERT par nom (comportement original, si pas de sélection)
        client_name = str(profil_client.get("nom_structure", {}).get("value", "")).strip() or "Client non identifie"
        client_payload = {
            "nom": client_name,
            "siret": _sanitize_text(profil_client.get("siret", {}).get("value", "")) or None,
            "forme_juridique": _sanitize_text(profil_client.get("forme_juridique", {}).get("value", "")) or None,
            "secteur_activite": ", ".join(
                _sanitize_text(item.get("value", "")) for item in profil_client.get("activites", []) if item.get("value")
            ) or None,
            "contact_email": _sanitize_text(profil_client.get("email", {}).get("value", "")) or None,
            "contact_telephone": _sanitize_text(profil_client.get("telephone", {}).get("value", "")) or None,
            "type_structure": _sanitize_text(profil_client.get("forme_juridique", {}).get("value", "")) or None,
            "owner_id": operator_id,
        }
        existing_clients = client.table("clients").select("*").eq("nom", client_name).eq("owner_id", operator_id).limit(1).execute().data
        if existing_clients:
            client_row = client.table("clients").update(client_payload).eq("id", existing_clients[0]["id"]).execute().data[0]
        else:
            client_row = client.table("clients").insert(client_payload).execute().data[0]

    dossier_title = _sanitize_text(donnees_projet.get("titre_projet", {}).get("value", ""))
    if not dossier_title or dossier_title == "Non detecte":
        dossier_title = dossier_files[0].name if dossier_files else "Dossier sans titre"
    dossier_payload = {
        "titre": dossier_title,
        "reference": None,
        "type_financement": _normalize_type_financement(
            _sanitize_text(wf2a_metadata.get("type_dossier_detecte", ""))
        ),
        "financeur": _sanitize_text(wf2a_metadata.get("financeur_detecte", "")) or None,
        "client_id": client_row["id"],
        "montant_max": _extract_first_numeric(_sanitize_text(wf2a_metadata.get("montant_max_detecte", ""))),
        "source_url": None,
        "owner_id": operator_id,
        "donnees_projet": {
            "titre_projet": _sanitize_text(donnees_projet.get("titre_projet", {}).get("value", "")),
            "montant_detecte": _sanitize_text(donnees_projet.get("montant_detecte", {}).get("value", "")),
            "dates_detectees": [_sanitize_text(item.get("value", "")) for item in donnees_projet.get("dates_detectees", [])],
            "elements_detectes": [_sanitize_text(item.get("value", "")) for item in donnees_projet.get("elements_detectes", [])],
        },
    }
    dossier_row = client.table("dossiers").insert(dossier_payload).execute().data[0]

    document_map: dict[str, str] = {}
    inserted_documents = []
    for uploaded_file in dossier_files:
        row = _upload_document_and_insert_record(client, settings.storage_bucket, uploaded_file, "dossier", dossier_row["id"], client_row["id"])
        document_map[uploaded_file.name] = row["id"]
        inserted_documents.append(row["id"])
    for uploaded_file in client_files:
        row = _upload_document_and_insert_record(client, settings.storage_bucket, uploaded_file, "client", None, client_row["id"])
        document_map[uploaded_file.name] = row["id"]
        inserted_documents.append(row["id"])
    for uploaded_file in project_files:
        row = _upload_document_and_insert_record(client, settings.storage_bucket, uploaded_file, "projet", dossier_row["id"], client_row["id"])
        document_map[uploaded_file.name] = row["id"]
        inserted_documents.append(row["id"])

    inserted_criteres = []
    criterion_id_map: dict[str, str] = {}
    VALID_CATEGORIES = {"obligatoire", "souhaitable", "bloquant", "interpretatif"}
    for index, criterion in enumerate(wf2a.get("criteres", []), start=1):
        raw_cat = _sanitize_text(criterion.get("categorie", "")).lower()
        categorie = raw_cat if raw_cat in VALID_CATEGORIES else "interpretatif"
        row = {
            "dossier_id": dossier_row["id"],
            "categorie": categorie,
            "domaine": _sanitize_text(criterion.get("domaine")),
            "libelle": _sanitize_text(criterion.get("libelle")),
            "detail": _sanitize_text(criterion.get("detail")),
            "source_document_id": document_map.get(str(criterion.get("source_document", ""))),
            "source_texte": _sanitize_text(criterion.get("source_texte")),
            "est_piece_exigee": bool(criterion.get("est_piece_exigee", False)),
            "est_critere_eliminatoire": bool(criterion.get("est_critere_eliminatoire", False)),
            "niveau_confiance": _normalize_niveau_confiance(str(criterion.get("niveau_confiance", ""))),
            "necessite_validation": bool(criterion.get("necessite_validation", False)),
            "ordre": index,
        }
        inserted = client.table("criteres").insert(row).execute().data[0]
        criterion_id_map[str(criterion.get("id_local", ""))] = inserted["id"]
        inserted_criteres.append(inserted["id"])

    rapport = wf4.get("rapport_structured", {})
    analysis_row = client.table("analyses").insert(
        {
            "dossier_id": dossier_row["id"],
            "client_id": client_row["id"],
            "score_global": int(wf3.get("score_global", 0) or 0),
            "statut_eligibilite": _map_analysis_status(str(wf3.get("statut_eligibilite", "a confirmer"))),
            "niveau_confiance": _normalize_niveau_confiance(str(wf3.get("niveau_confiance", ""))),
            "sous_scores": wf3.get("sous_scores", {}),
            "resume_executif": _sanitize_text(wf3.get("resume_executif", "")),
            "points_forts": [_sanitize_text(item) for item in list(rapport.get("points_valides", []))],
            "points_faibles": [_sanitize_text(item) for item in list(rapport.get("points_a_confirmer", []))],
            "elements_manquants": [_sanitize_text(item) for item in list(rapport.get("points_bloquants", []))],
            "documents_manquants": [_sanitize_text(item) for item in list(rapport.get("pieces_manquantes", []))],
            "recommandations": [_sanitize_text(item) for item in list(rapport.get("recommandations", []))],
            "statut_traitement": "termine",
            "modele_ia": "claude-sonnet-4-20250514" if any(
                step.get("engine") == "llm_direct_python" for step in execution.values() if isinstance(step, dict)
            ) else None,
            "prompt_version": "wf2-wf3-v1",
        }
    ).execute().data[0]

    inserted_results = []
    for result in wf3.get("resultats_criteres", []):
        critere_id = criterion_id_map.get(str(result.get("critere_id", "")))
        if not critere_id:
            continue
        row = client.table("resultats_criteres").insert(
            {
                "analyse_id": analysis_row["id"],
                "critere_id": critere_id,
                "statut": _map_result_status(str(result.get("statut", "a_confirmer"))),
                "score": int(result.get("score", 0) or 0),
                "justification": _sanitize_text(result.get("justification", "")),
                "donnee_client": _sanitize_text(result.get("donnee_utilisee", "")),
                "ecart": _sanitize_text(result.get("ecart", "")),
                "action_requise": _sanitize_text(result.get("action_requise", "")),
                "est_preremplissable": False,
                "valeur_preremplissage": None,
            }
        ).execute().data[0]
        inserted_results.append(row["id"])

    report_row = client.table("rapports").insert(
        {
            "analyse_id": analysis_row["id"],
            "type_rapport": rapport.get("type_rapport", "complet"),
            "contenu_json": rapport,
            "contenu_markdown": _sanitize_text(wf4.get("rapport_markdown", "")),
            "storage_path": None,
            "format_export": rapport.get("format_export", "markdown"),
            "version": 1,
        }
    ).execute().data[0]

    inserted_prefills = []
    for field in wf4.get("champs_preremplissage", []):
        is_generic = str(field.get("onglet", "")).lower() in {"structure", "contact"}
        nom_champ = _sanitize_text(field.get("nom_champ", ""))
        row_data = {
            "analyse_id": analysis_row["id"],
            "client_id": client_row["id"],
            "dossier_id": dossier_row["id"],
            "categorie": _sanitize_text(field.get("onglet", "Projet")),
            "nom_champ": nom_champ,
            "valeur": _sanitize_text(field.get("valeur", "")),
            "source": _prefill_source(field),
            "niveau_confiance": "moyen",
            "valide_par_humain": False,
            "est_generique": is_generic,
        }
        if is_generic and nom_champ:
            # Index unique partiel sur (client_id, nom_champ) WHERE est_generique = TRUE.
            # PostgREST ne résout pas les index partiels via on_conflict → select/update/insert.
            existing = (
                client.table("champs_preremplissage")
                .select("id")
                .eq("client_id", client_row["id"])
                .eq("nom_champ", nom_champ)
                .eq("est_generique", True)
                .limit(1)
                .execute()
                .data
            )
            if existing:
                row = (
                    client.table("champs_preremplissage")
                    .update(row_data)
                    .eq("id", existing[0]["id"])
                    .execute()
                    .data[0]
                )
            else:
                row = client.table("champs_preremplissage").insert(row_data).execute().data[0]
        else:
            row = client.table("champs_preremplissage").insert(row_data).execute().data[0]
        inserted_prefills.append(row["id"])

    financement_rows = client.table("financements").select("id,nom").in_("nom", [s.get("nom") for s in wf4.get("suggestions", []) if s.get("nom")]).execute().data
    financing_by_name = {row["nom"]: row["id"] for row in financement_rows}
    inserted_suggestions = []
    for index, suggestion in enumerate(wf4.get("suggestions", []), start=1):
        financement_id = financing_by_name.get(suggestion.get("nom", ""))
        if not financement_id:
            continue
        row = client.table("suggestions").insert(
            {
                "analyse_id": analysis_row["id"],
                "client_id": client_row["id"],
                "financement_id": financement_id,
                "score_pertinence": int(suggestion.get("score_pertinence", 0) or 0),
                "rang": index,
                "justification": _sanitize_text(suggestion.get("justification", "")),
            }
        ).execute().data[0]
        inserted_suggestions.append(row["id"])

    client.table("journal").insert(
        {
            "type_operation": "pipeline_wf1_wf4",
            "dossier_id": dossier_row["id"],
            "client_id": client_row["id"],
            "analyse_id": analysis_row["id"],
            "statut": "termine",
            "message": "Pipeline execute et persiste depuis Streamlit",
            "details": {
                "documents": len(inserted_documents),
                "criteres": len(inserted_criteres),
                "resultats": len(inserted_results),
                "rapport_id": report_row["id"],
                "preremplissage": len(inserted_prefills),
                "suggestions": len(inserted_suggestions),
                "execution": execution,
            },
        }
    ).execute()

    return {
        "ok": True,
        "client_id": client_row["id"],
        "dossier_id": dossier_row["id"],
        "analyse_id": analysis_row["id"],
        "rapport_id": report_row["id"],
        "documents_count": len(inserted_documents),
        "criteres_count": len(inserted_criteres),
        "resultats_count": len(inserted_results),
        "preremplissage_count": len(inserted_prefills),
        "suggestions_count": len(inserted_suggestions),
    }
