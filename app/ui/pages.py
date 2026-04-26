from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from datetime import datetime
import platform
import subprocess

import pandas as pd
import streamlit as st

try:
    from streamlit_extras.add_vertical_space import add_vertical_space
except ModuleNotFoundError:
    def add_vertical_space(lines: int = 1) -> None:
        for _ in range(max(0, int(lines))):
            st.write("")

from app.services.block_analysis import (
    apply_manual_completion,
    assess_block_completeness,
    build_block_normalized_text,
    build_block_recommendations,
    build_comparable_bridge,
    build_files_signature,
    build_global_context_bridge,
    build_global_cross_block_summary,
    build_manual_fields_for_section,
    build_upload_summary,
    collect_block_insights,
    evaluate_block_criteria,
    format_loaded_documents_label,
    get_dynamic_field_label,
    infer_block_document_context,
    is_missing_bridge_value,
    split_display_items,
    summarize_criterion_match_label,
    summarize_prescore_label,
    summarize_readiness_label,
    summarize_risk_label,
)
from app.services.bridge_completion import merge_completed_bridge_into_wf2
from app.services.client_manager import create_client, list_clients
from app.services.data_loader import (
    load_document_catalog,
    load_smoke_test_results,
    load_swot_data as load_demo_data,
)
from app.services.document_catalog import build_smoke_test_case
from app.services.llm_client import (
    call_llm_message,
    describe_llm_readiness,
    get_configured_providers,
    get_model_options,
    load_llm_settings,
)
from app.services.metadata import extract_table_metadata, extract_text_metadata
from app.services.normalizers import dataframe_to_markdown, filter_business_sheets, workbook_to_markdown
from app.services.parsers import (
    get_uploaded_bytes,
    get_uploaded_suffix,
    parse_csv_bytes,
    parse_docx_bytes,
    parse_excel_bytes,
    parse_pdf_bytes,
    parse_text_bytes,
)
from app.services.persistence import persist_pipeline_outputs
from app.services.pipeline_runtime import resolve_pipeline_outputs
from app.services.supabase_bridge import describe_supabase_readiness
from app.services.wf2 import (
    build_bridge_from_wf2,
    extract_wf2a_structured,
    extract_wf2b_structured,
    summarize_wf2b_client_profile,
    summarize_wf2b_project_data,
)
from app.services.wf2_llm import request_wf2a_llm_payload
from app.services.wf3 import build_wf3_analysis
from app.services.wf4 import (
    build_project_budget_markdown,
    build_project_presentation_markdown,
    build_wf4_outputs,
)


# ── Session state helpers ─────────────────────────────────────────────────────

PIPELINE_SCHEMA_VERSION = "2026-04-25-wf4-v2"
EXPORT_DIR = Path("/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/exports")


def get_active_pipeline_outputs(signature: str) -> dict[str, object] | None:
    stored_signature = st.session_state.get("pipeline_signature")
    stored_version = st.session_state.get("pipeline_schema_version")
    if stored_signature != signature or stored_version != PIPELINE_SCHEMA_VERSION:
        return None
    return st.session_state.get("pipeline_outputs")


def store_pipeline_outputs(
    signature: str,
    outputs: dict[str, object],
    persistence: dict[str, object] | None = None,
) -> None:
    st.session_state["pipeline_signature"] = signature
    st.session_state["pipeline_schema_version"] = PIPELINE_SCHEMA_VERSION
    st.session_state["pipeline_outputs"] = outputs
    st.session_state["pipeline_persistence"] = persistence or {}
    st.session_state["pipeline_last_error"] = ""


def _clear_editable_wf4_state(signature: str) -> None:
    prefixes = (
        f"edit_presentation_status_{signature}_",
        f"edit_presentation_content_{signature}_",
        f"edit_budget_project_",
        f"edit_budget_structure_",
        f"edit_checklist_{signature}",
    )
    for key in list(st.session_state.keys()):
        if any(key.startswith(prefix) for prefix in prefixes):
            del st.session_state[key]


def get_editable_wf4(signature: str, wf4: dict[str, object]) -> dict[str, object]:
    stored_signature = st.session_state.get("editable_wf4_signature")
    if stored_signature != signature or "editable_wf4" not in st.session_state:
        st.session_state["editable_wf4_signature"] = signature
        st.session_state["editable_wf4"] = deepcopy(wf4)
        _clear_editable_wf4_state(signature)
    return deepcopy(st.session_state["editable_wf4"])


def save_editable_wf4(signature: str, wf4: dict[str, object]) -> None:
    st.session_state["editable_wf4_signature"] = signature
    st.session_state["editable_wf4"] = deepcopy(wf4)


def write_local_export_files(signature: str, wf4: dict[str, object], pipeline_outputs: dict[str, object]) -> list[Path]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_signature = "".join(char for char in signature if char.isalnum())[:12] or "session"
    base = f"{timestamp}_{safe_signature}"

    livrables = wf4.get("livrables", {})
    presentation = livrables.get("presentation_projet", {})
    budget_projet = livrables.get("budget_projet", {})
    budget_structure = livrables.get("budget_structure", {})

    written_paths: list[Path] = []

    presentation_path = EXPORT_DIR / f"{base}_presentation_projet.md"
    presentation_path.write_text(str(presentation.get("markdown", "")), encoding="utf-8")
    written_paths.append(presentation_path)

    budget_project_md_path = EXPORT_DIR / f"{base}_budget_projet.md"
    budget_project_md_path.write_text(str(budget_projet.get("markdown", "")), encoding="utf-8")
    written_paths.append(budget_project_md_path)

    budget_project_csv_path = EXPORT_DIR / f"{base}_budget_projet.csv"
    _budget_to_dataframe(budget_projet.get("structured", {}) or {}).to_csv(budget_project_csv_path, index=False)
    written_paths.append(budget_project_csv_path)

    if isinstance(budget_structure, dict) and budget_structure.get("required"):
        budget_structure_md_path = EXPORT_DIR / f"{base}_budget_structure.md"
        budget_structure_md_path.write_text(str(budget_structure.get("markdown", "")), encoding="utf-8")
        written_paths.append(budget_structure_md_path)

        budget_structure_csv_path = EXPORT_DIR / f"{base}_budget_structure.csv"
        _budget_to_dataframe(budget_structure.get("structured", {}) or {}).to_csv(budget_structure_csv_path, index=False)
        written_paths.append(budget_structure_csv_path)

    json_path = EXPORT_DIR / f"{base}_resultat_pipeline.json"
    json_path.write_text(json.dumps({**pipeline_outputs, "wf4": wf4}, ensure_ascii=False, indent=2), encoding="utf-8")
    written_paths.append(json_path)

    return written_paths


def open_local_exports_dir() -> tuple[bool, str]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        system = platform.system().lower()
        if system == "darwin":
            subprocess.run(["open", str(EXPORT_DIR)], check=True)
        elif system == "windows":
            subprocess.run(["explorer", str(EXPORT_DIR)], check=True)
        else:
            subprocess.run(["xdg-open", str(EXPORT_DIR)], check=True)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def export_single_local_file(filename: str, content: str) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    target = EXPORT_DIR / filename
    target.write_text(content, encoding="utf-8")
    return target


def _budget_to_dataframe(structured_budget: dict[str, object]) -> pd.DataFrame:
    charges = list(structured_budget.get("charges", []))
    produits = list(structured_budget.get("produits", []))
    max_len = max(len(charges), len(produits)) if (charges or produits) else 0
    rows = []
    for index in range(max_len):
        charge = charges[index] if index < len(charges) else {}
        produit = produits[index] if index < len(produits) else {}
        rows.append(
            {
                "Section charges": charge.get("section", "") or charge.get("sous_section", ""),
                "Charges": charge.get("poste", ""),
                "Montant charges": charge.get("montant_previsionnel", ""),
                "Statut charges": charge.get("statut", ""),
                "Source charges": charge.get("source", ""),
                "Commentaire charges": charge.get("commentaire", ""),
                "Section produits": produit.get("section", "") or produit.get("sous_section", ""),
                "Produits": produit.get("poste", ""),
                "Montant produits": produit.get("montant_previsionnel", ""),
                "Statut produits": produit.get("statut", ""),
                "Source produits": produit.get("source", ""),
                "Commentaire produits": produit.get("commentaire", ""),
            }
        )
    return pd.DataFrame(rows)


# ── Shared display helpers ────────────────────────────────────────────────────

def render_metadata(metadata: dict[str, str], title: str = "Metadonnees detectees") -> None:
    st.markdown(f"### {title}")
    cols = st.columns(2)
    items = list(metadata.items())
    for index, (label, value) in enumerate(items):
        cols[index % 2].write(f"**{label}** : {value}")


def render_normalized_text(content: str, filename: str, *, expanded: bool = False, section_title: str = "Source normalisee") -> None:
    with st.expander(section_title, expanded=expanded):
        st.text_area("Contenu normalise", content[:5000], height=260)
        st.download_button(
            "Telecharger la source normalisee",
            data=content,
            file_name=f"{Path(filename).stem}_normalise.md",
            mime="text/markdown",
        )


# ── Static pages ──────────────────────────────────────────────────────────────

def render_home() -> None:
    catalog = load_document_catalog()
    base_doc_count = len(catalog) if not catalog.empty else 0

    st.title("AAP Ingenia")
    st.caption("Back-office local de pre-analyse documentaire aligne sur les workflows Subly")

    add_vertical_space(1)

    col1, col2, col3 = st.columns(3)
    col1.metric("Statut", "WF1 a WF4 locaux")
    col2.metric("Mode", "Prototype metier")
    col3.metric("Base documentaire", f"{base_doc_count} docs")

    add_vertical_space(1)

    st.markdown(
        """
        Cette version sert maintenant a valider un vrai flux local :

        - ingestion dossier / client / projet ;
        - extraction structuree `WF2a` et `WF2b` ;
        - matching critere par critere `WF3` ;
        - sorties locales `WF4` : rapport, pre-remplissage et suggestions ;
        - preparation de la base documentaire et de Supabase.
        """
    )


def render_project() -> None:
    st.subheader("Ou en est le projet ?")
    st.markdown(
        """
        - Le cadrage produit et le schema cible sont deja poses dans `contexte/`
        - Les 4 sorties metier sont maintenant representees localement
        - La base documentaire locale est integree en catalogue
        - Le pont Supabase est prepare mais pas encore lance localement
        """
    )

    st.subheader("Cap actuel")
    st.write(
        "Stabiliser les cas reels, brancher Supabase, puis sortir progressivement la logique metier du gros fichier Streamlit."
    )


def render_demo_data() -> None:
    st.subheader("Donnees de demonstration")
    df = load_demo_data()

    if df.empty:
        st.warning("Le fichier de demonstration est introuvable.")
        return

    st.dataframe(df, use_container_width=True)

    first_row = df.iloc[0]
    st.markdown("### Resume")
    st.write(first_row.get("resume_executif", "Aucun resume disponible."))


def render_document_catalog_page() -> None:
    st.subheader("Base documentaire integree")
    st.write(
        "Cette vue recense les documents du dossier de base locale pour preparer l'ingestion, les cas de test et le futur seed Supabase."
    )

    catalog = load_document_catalog()
    if catalog.empty:
        st.warning("Aucun document de base n'a ete detecte.")
        return

    role_counts = catalog["role_workflow_recommande"].value_counts()
    family_counts = catalog["famille_documentaire"].value_counts()
    ext_counts = catalog["extension"].value_counts()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Documents", str(len(catalog)))
    col2.metric("Extensions", str(catalog["extension"].nunique()))
    col3.metric("Familles", str(catalog["famille_documentaire"].nunique()))
    col4.metric("Roles recommandes", str(catalog["role_workflow_recommande"].nunique()))

    add_vertical_space(1)

    st.markdown("### Lecture rapide")
    st.write("**Repartition par role recommande**")
    for role, count in role_counts.items():
        st.write(f"- {role} : {count}")
    st.write("**Top familles documentaires**")
    for family, count in family_counts.head(8).items():
        st.write(f"- {family} : {count}")

    with st.expander("Voir le detail du catalogue", expanded=False):
        st.dataframe(catalog, use_container_width=True)
        st.write("**Top extensions**")
        for extension, count in ext_counts.items():
            st.write(f"- {extension} : {count}")

    smoke_case = build_smoke_test_case()
    with st.expander("Jeu de test documentaire retenu", expanded=False):
        st.write("**Dossier**")
        for item in smoke_case["dossier"]:
            st.write(f"- {item.name}")
        st.write("**Client**")
        for item in smoke_case["client"]:
            st.write(f"- {item.name}")
        st.write("**Projet**")
        for item in smoke_case["projet"]:
            st.write(f"- {item.name}")

    smoke_results = load_smoke_test_results()
    if smoke_results:
        wf3 = smoke_results.get("wf3", {})
        st.markdown("### Resultat du smoke-test reel")
        render_metadata({
            "Statut": wf3.get("statut_eligibilite", "inconnu"),
            "Score": f"{wf3.get('score_global', 0)}/100",
            "Confiance": wf3.get("niveau_confiance", "inconnue"),
            "Resume": wf3.get("resume_executif", "Aucun"),
        })


def render_supabase_page() -> None:
    st.subheader("Connexion Supabase")

    readiness = describe_supabase_readiness()
    is_configured = readiness.get("SUPABASE_URL") == "configuree" and readiness.get("SUPABASE_ANON_KEY") == "configuree"

    if is_configured:
        st.success("Supabase Cloud connecte — toutes les cles sont configurees.")
    else:
        st.warning("Cles Supabase non configurees. Ajoutez-les dans les secrets Streamlit ou dans le fichier `.env`.")

    render_metadata(readiness)

    st.markdown("### Infrastructure")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Mode deploiement**")
        st.write("Supabase Cloud (hosted) — pas besoin de Docker ni de CLI local")
        st.write("")
        st.write("**Schema BDD**")
        st.write("`supabase/migrations/` — pret a appliquer via le dashboard Supabase")
    with col2:
        st.write("**Storage**")
        st.write("Bucket `subly-documents` — prive, cree automatiquement au premier appel")
        st.write("")
        st.write("**Seed**")
        st.write("`supabase/seed.sql` — donnees de demonstration disponibles")

    if is_configured:
        st.markdown("### Test de connexion")
        if st.button("Tester la connexion Supabase", key="btn_test_supabase"):
            from app.services.supabase_bridge import create_supabase_client
            client = create_supabase_client()
            if client is None:
                st.error("Impossible de creer le client Supabase.")
            else:
                try:
                    resp = client.table("clients").select("id").limit(1).execute()
                    st.success(f"Connexion BDD OK — table `clients` accessible ({len(resp.data)} ligne(s))")
                except Exception as exc:
                    st.error(f"Connexion echouee : {exc}")


def render_llm_page() -> None:
    st.subheader("Connexion LLM")

    llm_info = describe_llm_readiness()
    anthropic_configured = llm_info.get("ANTHROPIC_API_KEY") == "configuree"
    google_configured = llm_info.get("GOOGLE_API_KEY") == "configuree"
    mistral_configured = llm_info.get("MISTRAL_API_KEY") == "configuree"
    is_configured = anthropic_configured or google_configured or mistral_configured

    if is_configured:
        st.success("Provider LLM configure et operationnel.")
    else:
        st.warning(
            "Aucune cle LLM configuree. Ajoutez `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` ou `MISTRAL_API_KEY` dans les secrets Streamlit ou dans le fichier `.env`."
        )

    render_metadata(llm_info)

    st.markdown("### Strategie d'integration")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Point d'entree**")
        st.write("`app/services/llm_client.py` — appels directs Python")
        st.write("")
        st.write("**Provider actif**")
        st.write(f"`{llm_info.get('Provider', 'anthropic')}`")
        st.write("")
        st.write("**Modele actif**")
        st.write(f"`{llm_info.get('Modele', 'gemini-2.5-flash')}`")
    with col2:
        st.write("**Fallback**")
        st.write("Heuristiques locales actives si la cle est absente — l'app ne plante jamais")
        st.write("")
        st.write("**Usage prevu**")
        st.write("WF2a (criteres), WF2b (profil client), WF3 (scoring), WF4 (rapport)")
        st.write("")
        st.write("**Providers supportes**")
        st.write("- Anthropic / Claude")
        st.write("- Google / Gemini")
        st.write("- Google / Gemma si le modele est expose par ton compte")
        st.write("- Mistral / Mistral Small 4")
        st.write("- Mistral / Ministral 8B si tu forces le nom de modele")

    if is_configured:
        st.markdown("### Test de connexion")
        if st.button("Tester l'appel LLM", key="btn_test_llm"):
            with st.spinner("Appel en cours..."):
                result = call_llm_message(
                    "Tu es un assistant de test. Reponds en une seule phrase courte.",
                    "Dis juste OK pour confirmer que tu fonctionnes."
                )
            if result.get("ok"):
                usage = result.get("usage", {})
                st.success(f"Le provider repond : *{result.get('text', '')}*")
                st.caption(
                    f"Provider : {result.get('provider')} — "
                    f"Modele : {result.get('model')} — "
                    f"{usage.get('input_tokens')} tokens entree / {usage.get('output_tokens')} tokens sortie"
                )
            else:
                st.error(f"Echec : {result.get('error')}")

    with st.expander("Configuration recommandee", expanded=False):
        st.write("**Anthropic**")
        st.code('ANTHROPIC_API_KEY=\"...\"', language="toml")
        st.write("**Google Gemini**")
        st.code('LLM_PROVIDER=\"google\"\nGOOGLE_API_KEY=\"...\"\nGOOGLE_MODEL=\"gemini-2.5-flash\"', language="toml")
        st.write("**Mistral**")
        st.code(
            'LLM_PROVIDER=\"mistral\"\n'
            'MISTRAL_API_KEY=\"...\"\n'
            'MISTRAL_MODEL=\"mistral-small-2603\"\n'
            'MISTRAL_AGENT_BUDGET_PROJET_ID=\"ag_xxx...\"',
            language="toml",
        )
        st.caption(
            "Pour Gemma, garde la meme integration Google. Si ton compte Google AI Studio ou Vertex expose un modele Gemma compatible API, il suffira de remplacer `GOOGLE_MODEL`. Pour Mistral, `mistral-small-2603` est le choix retenu et recommande ici. Si `MISTRAL_AGENT_BUDGET_PROJET_ID` est defini, la generation du budget projet WF4B passera par cet agent."
        )

    st.markdown("### Test de preparation WF2a")
    smoke_case = build_smoke_test_case()
    dossier_files = smoke_case["dossier"]

    if not dossier_files:
        st.info("Aucun document dossier de smoke-test n'est disponible.")
        return

    st.write("Documents dossier du test :")
    for item in dossier_files:
        st.write(f"- {item.name}")

    if st.button("Tester la preparation WF2a LLM", key="wf2a_llm_prepare"):
        result = request_wf2a_llm_payload(dossier_files)
        if not result.get("ok"):
            st.warning(f"WF2a LLM non execute : {result.get('error', 'erreur inconnue')}")
        else:
            payload = result.get("payload", {})
            metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
            criteres = payload.get("criteres", []) if isinstance(payload, dict) else []
            render_metadata({
                "Mode": str(result.get("mode", "llm_direct_python")),
                "Modele": str(result.get("model", "")),
                "Input tokens": str(result.get("usage", {}).get("input_tokens", "inconnu")),
                "Output tokens": str(result.get("usage", {}).get("output_tokens", "inconnu")),
                "Criteres retournes": str(len(criteres)),
            })
            if metadata:
                st.write("**Metadata retournee**")
                render_metadata({
                    "Type dossier": str(metadata.get("type_dossier_detecte", "inconnu")),
                    "Financeur": str(metadata.get("financeur_detecte", "inconnu")),
                    "Montant max": str(metadata.get("montant_max_detecte", "inconnu")),
                    "Date limite": str(metadata.get("date_limite_detectee", "inconnue")),
                })
            if criteres:
                with st.expander("Voir le payload JSON brut", expanded=False):
                    st.json(payload)


# ── WF2a section ──────────────────────────────────────────────────────────────

def render_wf2a_dossier_section(
    dossier_files,
    wf2a_structured: dict[str, object] | None = None,
    execution_meta: dict[str, object] | None = None,
) -> None:
    st.subheader("WF2a local - Extraction criteres dossier")

    if not dossier_files:
        st.info("Aucun document dossier charge pour lancer l'extraction WF2a locale.")
        return

    wf2a = wf2a_structured or extract_wf2a_structured(dossier_files)
    criteria = wf2a.get("criteres", [])
    metadata = wf2a.get("metadata", {})

    if not criteria:
        st.warning("Aucun critere explicite n'a ete detecte dans le bloc dossier.")
        return

    if execution_meta:
        st.caption(
            f"Moteur actif : {execution_meta.get('engine', 'heuristique_locale')}"
            + (" (fallback local)" if execution_meta.get("fallback_used") else "")
        )

    st.markdown("### Metadata WF2a")
    render_metadata({
        "Type dossier detecte": metadata.get("type_dossier_detecte", "autre"),
        "Financeur detecte": metadata.get("financeur_detecte", "Non detecte"),
        "Montant max detecte": metadata.get("montant_max_detecte", "Non detecte"),
        "Date limite detectee": metadata.get("date_limite_detectee", "Non detectee"),
        "Nombre de criteres": str(metadata.get("nb_criteres_extraits", 0)),
        "Mode extraction": metadata.get("mode_extraction", "inconnu"),
    })

    st.write(f"{len(criteria)} critere(s) detecte(s)")
    for index, criterion in enumerate(criteria, start=1):
        st.markdown(
            f"**{index}. {criterion['libelle']}**  \n"
            f"Categorie : `{criterion['categorie']}`  \n"
            f"Domaine : `{criterion['domaine']}`  \n"
            f"Detail : {criterion['detail']}  \n"
            f"Source document : `{criterion.get('source_document', 'inconnu')}`  \n"
            f"Niveau de confiance : `{criterion.get('niveau_confiance', 'moyen')}`  \n"
            f"Validation requise : `{criterion.get('necessite_validation', False)}`  \n"
            f"Source texte : {criterion.get('source_texte', '')[:220]}"
        )


# ── WF2b section ──────────────────────────────────────────────────────────────

def render_wf2b_section(
    client_files,
    project_files,
    wf2b_structured: dict[str, object] | None = None,
    execution_meta: dict[str, object] | None = None,
) -> None:
    st.subheader("WF2b local - Profil client et donnees projet")
    wf2b = wf2b_structured or extract_wf2b_structured(client_files, project_files)

    if execution_meta:
        st.caption(
            f"Moteur actif : {execution_meta.get('engine', 'heuristique_locale')}"
            + (" (fallback local)" if execution_meta.get("fallback_used") else "")
        )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Profil client")
        if not client_files:
            st.info("Aucun document client charge pour l'extraction WF2b locale.")
        else:
            render_metadata(summarize_wf2b_client_profile(wf2b))

    with col2:
        st.markdown("### Donnees projet")
        if not project_files:
            st.info("Aucun document projet charge pour l'extraction WF2b locale.")
        else:
            render_metadata(summarize_wf2b_project_data(wf2b))

    with st.expander("Voir la structure WF2b preparee pour un futur LLM", expanded=False):
        profil_client = wf2b.get("profil_client", {})
        donnees_projet = wf2b.get("donnees_projet", {})
        st.write("**Profil client structure**")
        render_metadata({
            "Nom structure": profil_client.get("nom_structure", {}).get("value", "Non detecte"),
            "Forme juridique": profil_client.get("forme_juridique", {}).get("value", "Non detectee"),
            "Source client": profil_client.get("forme_juridique", {}).get("source_document", ""),
            "Confiance forme juridique": profil_client.get("forme_juridique", {}).get("niveau_confiance", "moyen"),
        })
        st.write("**Donnees projet structurees**")
        render_metadata({
            "Titre projet": donnees_projet.get("titre_projet", {}).get("value", "Non detecte"),
            "Montant projet": donnees_projet.get("montant_detecte", {}).get("value", "Non detecte"),
            "Source projet": donnees_projet.get("titre_projet", {}).get("source_document", ""),
            "Confiance montant": donnees_projet.get("montant_detecte", {}).get("niveau_confiance", "moyen"),
        })


# ── Bridge / manual completion sections ──────────────────────────────────────

def render_dynamic_manual_field(
    input_key: str,
    field_type: str,
    base_label: str,
    source_label: str,
    key_suffix: str,
    height: int = 120,
) -> str:
    input_label = f"{base_label} a completer"
    help_text = f"Source concernee : {source_label}"

    if field_type == "text_area":
        return st.text_area(
            input_label,
            value="",
            key=f"manual_{input_key}_{key_suffix}",
            help=help_text,
            height=height,
            placeholder=f"Saisir {base_label.lower()}",
        )

    return st.text_input(
        input_label,
        value="",
        key=f"manual_{input_key}_{key_suffix}",
        help=help_text,
        placeholder=f"Saisir {base_label.lower()}",
    )


def render_manual_completion_widget(
    bridge: dict[str, str],
    dossier_files,
    client_files,
    project_files,
) -> dict[str, str]:
    st.markdown("### Completion manuelle des donnees manquantes")
    st.caption("Le widget s'adapte aux blocs charges et ne propose que les informations encore manquantes ou trop faibles pour le WF3 local.")

    overrides: dict[str, str] = {}
    sections = [
        ("Documents dossier", dossier_files),
        ("Documents client", client_files),
        ("Documents projet", project_files),
    ]

    displayed_fields = 0

    for section_title, section_files in sections:
        source_label = format_loaded_documents_label(section_files)
        context_tags = infer_block_document_context(section_files)
        fields = build_manual_fields_for_section(section_title, context_tags)
        missing_fields = [
            field for field in fields
            if is_missing_bridge_value(field[1], bridge.get(field[1], ""))
        ]

        if not missing_fields:
            continue

        displayed_fields += len(missing_fields)
        with st.expander(f"{section_title} a completer", expanded=True):
            st.caption(f"Documents charges : {source_label}")
            for input_key, target_key, field_type, base_label, key_suffix in missing_fields:
                dynamic_label = get_dynamic_field_label(section_title, target_key, context_tags)
                if input_key != target_key:
                    dynamic_label = base_label
                overrides[input_key] = render_dynamic_manual_field(
                    input_key,
                    field_type,
                    dynamic_label,
                    source_label,
                    key_suffix,
                )

    if displayed_fields == 0:
        st.success("Aucune donnee prioritaire ne semble manquer dans le pont actuel.")

    return apply_manual_completion(bridge, overrides)


def render_bridge_section(
    bridge: dict[str, str],
    dossier_files,
    client_files,
    project_files,
) -> dict[str, str]:
    st.subheader("Pont local - Donnees comparables WF2a/WF2b")
    render_metadata(bridge)
    st.divider()
    completed_bridge = render_manual_completion_widget(bridge, dossier_files, client_files, project_files)
    st.markdown("### Pont apres completion manuelle")
    render_metadata(completed_bridge)
    return completed_bridge


# ── WF3 section ───────────────────────────────────────────────────────────────

def render_wf3_section(
    dossier_files,
    client_files,
    project_files,
    bridge: dict[str, str] | None = None,
    global_bridge: dict[str, str] | None = None,
    pipeline_outputs: dict[str, object] | None = None,
) -> None:
    st.subheader("WF3 local - Matching dossier / client / projet")

    if not dossier_files or not client_files or not project_files:
        st.info("Le WF3 local demande des documents dans les 3 blocs : dossier, client et projet.")
        return

    wf2a_structured = pipeline_outputs.get("wf2a") if pipeline_outputs else extract_wf2a_structured(dossier_files)
    wf2b_structured = pipeline_outputs.get("wf2b") if pipeline_outputs else extract_wf2b_structured(client_files, project_files)

    if bridge is None:
        bridge = build_bridge_from_wf2(wf2a_structured, wf2b_structured)
    if global_bridge is None:
        fallback_block_files_map = {
            "Documents dossier": dossier_files,
            "Documents client": client_files,
            "Documents projet": project_files,
        }
        fallback_cross_summary = build_global_cross_block_summary(fallback_block_files_map)
        global_bridge = build_global_context_bridge(
            fallback_block_files_map,
            fallback_cross_summary,
            bridge,
        )

    if pipeline_outputs:
        wf3 = pipeline_outputs.get("wf3", {})
    else:
        completed_wf2a, completed_wf2b = merge_completed_bridge_into_wf2(
            wf2a_structured,
            wf2b_structured,
            bridge,
        )
        wf3 = build_wf3_analysis(
            completed_wf2a,
            completed_wf2b,
            global_context_bridge=global_bridge,
        )

    execution_meta = pipeline_outputs.get("execution", {}).get("wf3") if pipeline_outputs else None
    if execution_meta:
        st.caption(
            f"Moteur actif : {execution_meta.get('engine', 'heuristique_locale')}"
            + (" (fallback local)" if execution_meta.get("fallback_used") else "")
        )

    counts = wf3.get("counts", {})
    sous_scores = wf3.get("sous_scores", {})
    results = list(wf3.get("resultats_criteres", []))
    count_valide = counts.get("valide", 0)
    count_confirm = counts.get("a_confirmer", 0)
    count_missing = counts.get("manquant", 0)
    count_invalid = counts.get("non_valide", 0)
    prior_actions = []
    for result in results:
        if result.get("statut") in {"manquant", "non_valide", "a_confirmer"}:
            action = str(result.get("action_requise", "")).strip()
            if action and action not in prior_actions:
                prior_actions.append(action)

    col1, col2, col3 = st.columns(3)
    col1.metric("Statut", str(wf3.get("statut_eligibilite", "a confirmer")))
    col2.metric("Score global", f"{wf3.get('score_global', 0)}/100")
    col3.metric("Confiance", str(wf3.get("niveau_confiance", "moyen")))

    st.markdown("### Vue rapide")
    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
    quick_col1.metric("Criteres valides", str(count_valide))
    quick_col2.metric("A confirmer", str(count_confirm))
    quick_col3.metric("Manquants", str(count_missing))
    quick_col4.metric("Ecarts", str(count_invalid))

    st.markdown("### Sous-scores")
    score_col1, score_col2, score_col3, score_col4 = st.columns(4)
    score_col1.metric("Bloc client", f"{sous_scores.get('bloc_client', 0)}/100")
    score_col2.metric("Bloc projet", f"{sous_scores.get('bloc_projet', 0)}/100")
    score_col3.metric("Bloc mixte", f"{sous_scores.get('bloc_mixte', 0)}/100")
    score_col4.metric("Fiabilite doc", f"{sous_scores.get('fiabilite_documentaire', 0)}/100")

    st.markdown("### Contexte global integre")
    global_col1, global_col2, global_col3 = st.columns(3)
    global_col1.metric("Preparation", summarize_readiness_label(global_bridge.get("etat_global_documentaire", "inconnue")))
    global_col2.metric("Solidite", summarize_prescore_label(global_bridge.get("prescore_global_documentaire", "inconnue")))
    risk_value = "modere" if wf3.get("niveau_confiance") == "haut" else "moyen" if wf3.get("niveau_confiance") == "moyen" else "eleve"
    global_col3.metric("Risque", summarize_risk_label(risk_value))

    st.markdown("### Resume executif")
    st.write(str(wf3.get("resume_executif", "Aucun resume disponible.")))

    st.markdown("### Actions prioritaires")
    if prior_actions:
        for item in prior_actions[:8]:
            st.write(f"- {item}")
    else:
        st.write("- Aucune action prioritaire immediate")

    with st.expander("Voir le matching critere par critere", expanded=False):
        if not results:
            st.info("Aucun critere exploitable n'a ete produit par WF2a.")
        else:
            rows = []
            for result in results:
                rows.append({
                    "Critere": result.get("libelle", ""),
                    "Bloc": result.get("bloc_cible", ""),
                    "Statut": summarize_criterion_match_label(str(result.get("statut", ""))),
                    "Score": result.get("score", 0),
                    "Confiance": result.get("niveau_confiance", "moyen"),
                    "Source dossier": result.get("source_document", ""),
                    "Donnee utilisee": result.get("donnee_utilisee", ""),
                })
            st.dataframe(rows, use_container_width=True)

            for index, result in enumerate(results, start=1):
                st.markdown(
                    f"**{index}. {result.get('libelle', 'Critere')}**  \n"
                    f"Statut : `{summarize_criterion_match_label(str(result.get('statut', 'a_confirmer')))}`  \n"
                    f"Score : `{result.get('score', 0)}/100`  \n"
                    f"Bloc cible : `{result.get('bloc_cible', 'mixte')}`  \n"
                    f"Source dossier : `{result.get('source_document', 'inconnu')}`  \n"
                    f"Justification : {result.get('justification', 'Aucune')}  \n"
                    f"Action requise : {result.get('action_requise', 'Aucune')}  \n"
                    f"Donnee utilisee : {result.get('donnee_utilisee', 'Aucune')}  \n"
                    f"Ecart : {result.get('ecart', 'Aucun') or 'Aucun'}"
                )


# ── WF4 section ───────────────────────────────────────────────────────────────

def render_wf4_section(
    dossier_files,
    client_files,
    project_files,
    bridge: dict[str, str] | None = None,
    global_bridge: dict[str, str] | None = None,
    pipeline_outputs: dict[str, object] | None = None,
) -> None:
    st.subheader("WF4 local - Livrables de candidature")

    if not dossier_files or not client_files or not project_files:
        st.info("Le WF4 local demande un dossier, un client et un projet pour generer des sorties utiles.")
        return

    if pipeline_outputs:
        wf4_outputs = pipeline_outputs.get("wf4", {})
    else:
        wf2a_structured = extract_wf2a_structured(dossier_files)
        wf2b_structured = extract_wf2b_structured(client_files, project_files)
        if bridge is None:
            bridge = build_bridge_from_wf2(wf2a_structured, wf2b_structured)
        if global_bridge is None:
            fallback_block_files_map = {
                "Documents dossier": dossier_files,
                "Documents client": client_files,
                "Documents projet": project_files,
            }
            fallback_cross_summary = build_global_cross_block_summary(fallback_block_files_map)
            global_bridge = build_global_context_bridge(
                fallback_block_files_map,
                fallback_cross_summary,
                bridge,
            )

        completed_wf2a, completed_wf2b = merge_completed_bridge_into_wf2(
            wf2a_structured,
            wf2b_structured,
            bridge,
        )
        wf3_analysis = build_wf3_analysis(
            completed_wf2a,
            completed_wf2b,
            global_context_bridge=global_bridge,
        )
        wf4_outputs = build_wf4_outputs(completed_wf2b, wf3_analysis)

    execution_meta = pipeline_outputs.get("execution", {}) if pipeline_outputs else {}
    if execution_meta:
        st.caption(
            "Moteurs actifs : "
            f"WF2a={execution_meta.get('wf2a', {}).get('engine', 'heuristique_locale')}, "
            f"WF2b={execution_meta.get('wf2b', {}).get('engine', 'heuristique_locale')}, "
            f"WF3={execution_meta.get('wf3', {}).get('engine', 'heuristique_locale')}, "
            f"WF4={execution_meta.get('wf4', {}).get('engine', 'heuristique_locale')}"
        )

    rapport = wf4_outputs.get("rapport_structured", {})
    preremplissage = list(wf4_outputs.get("champs_preremplissage", []))
    suggestions = list(wf4_outputs.get("suggestions", []))
    livrables = wf4_outputs.get("livrables", {})
    presentation = livrables.get("presentation_projet", {})
    budget_projet = livrables.get("budget_projet", {})
    budget_structure = livrables.get("budget_structure", {})
    checklist = list(livrables.get("points_a_completer", []))

    col1, col2, col3 = st.columns(3)
    col1.metric("Statut dossier", str(rapport.get("statut_eligibilite", "a confirmer")))
    col2.metric("Sections presentation", str(len(presentation.get("sections", []))))
    col3.metric("Points a completer", str(len(checklist)))

    st.markdown("### 1. Document de presentation du projet")
    sections = list(presentation.get("sections", []))
    if sections:
        for section in sections:
            with st.expander(f"{section.get('section', 'Section')} · {section.get('statut', 'a_completer')}", expanded=False):
                st.write(section.get("contenu", ""))
        st.download_button(
            "Telecharger la trame de presentation",
            data=str(presentation.get("markdown", "")),
            file_name="presentation_projet.md",
            mime="text/markdown",
            key="download_presentation_projet",
        )
    else:
        st.info("Aucune trame de presentation disponible.")

    st.markdown("### 2. Budget previsionnel du projet")
    project_budget_structured = budget_projet.get("structured", {})
    if project_budget_structured:
        budget_rows = []
        charges = list(project_budget_structured.get("charges", []))
        produits = list(project_budget_structured.get("produits", []))
        max_len = max(len(charges), len(produits))
        for index in range(max_len):
            charge = charges[index] if index < len(charges) else {"poste": "", "montant_previsionnel": ""}
            produit = produits[index] if index < len(produits) else {"poste": "", "montant_previsionnel": ""}
            budget_rows.append({
                "Charges": charge.get("poste", ""),
                "Montant charges": charge.get("montant_previsionnel", ""),
                "Produits": produit.get("poste", ""),
                "Montant produits": produit.get("montant_previsionnel", ""),
            })
        st.dataframe(budget_rows, use_container_width=True)
        for note in project_budget_structured.get("notes", []):
            st.write(f"- {note}")
        st.download_button(
            "Telecharger la trame budget projet",
            data=str(budget_projet.get("markdown", "")),
            file_name="budget_projet.md",
            mime="text/markdown",
            key="download_budget_projet",
        )
    else:
        st.info("Aucune trame budget projet disponible.")

    st.markdown("### 3. Budget previsionnel de structure")
    if budget_structure.get("required") and budget_structure.get("structured"):
        structure_rows = []
        charges = list(budget_structure["structured"].get("charges", []))
        produits = list(budget_structure["structured"].get("produits", []))
        max_len = max(len(charges), len(produits))
        for index in range(max_len):
            charge = charges[index] if index < len(charges) else {"poste": "", "montant_previsionnel": ""}
            produit = produits[index] if index < len(produits) else {"poste": "", "montant_previsionnel": ""}
            structure_rows.append({
                "Charges structure": charge.get("poste", ""),
                "Montant charges": charge.get("montant_previsionnel", ""),
                "Produits structure": produit.get("poste", ""),
                "Montant produits": produit.get("montant_previsionnel", ""),
            })
        st.dataframe(structure_rows, use_container_width=True)
        for note in budget_structure["structured"].get("notes", []):
            st.write(f"- {note}")
        st.download_button(
            "Telecharger la trame budget structure",
            data=str(budget_structure.get("markdown", "")),
            file_name="budget_structure.md",
            mime="text/markdown",
            key="download_budget_structure",
        )
    else:
        st.info("Pas de budget structure requis detecte pour l'instant.")

    st.markdown("### 4. Points a completer")
    if checklist:
        st.dataframe(checklist, use_container_width=True)
    else:
        st.info("Aucun point de completion remonte.")

    with st.expander("Elements secondaires", expanded=False):
        st.markdown("#### Champs de pre-remplissage")
        if preremplissage:
            st.dataframe(preremplissage, use_container_width=True)
        else:
            st.info("Aucun champ de pre-remplissage disponible.")

        st.markdown("#### Suggestions alternatives")
        if suggestions:
            for index, suggestion in enumerate(suggestions, start=1):
                st.markdown(
                    f"**{index}. {suggestion.get('nom', 'Suggestion')}**  \n"
                    f"Pertinence : `{suggestion.get('score_pertinence', 0)}/100`  \n"
                    f"Justification : {suggestion.get('justification', 'Aucune justification')}"
                )
        else:
            st.info("Aucune suggestion alternative locale n'a ete detectee pour l'instant.")


def render_final_result_summary(pipeline_outputs: dict[str, object]) -> None:
    execution = pipeline_outputs.get("execution", {})
    wf3 = pipeline_outputs.get("wf3", {})
    wf4 = pipeline_outputs.get("wf4", {})
    pipeline_signature = str(st.session_state.get("pipeline_signature", "default"))
    editable_wf4 = get_editable_wf4(pipeline_signature, wf4)
    wf4 = editable_wf4
    rapport = wf4.get("rapport_structured", {})
    livrables = wf4.get("livrables", {})
    presentation = livrables.get("presentation_projet", {})
    budget_projet = livrables.get("budget_projet", {})
    budget_structure = livrables.get("budget_structure", {})
    checklist = list(livrables.get("points_a_completer", []))
    presentation_markdown = str(presentation.get("markdown", "") or wf4.get("rapport_markdown", ""))
    budget_projet_markdown = str(budget_projet.get("markdown", ""))
    budget_structure_markdown = str(budget_structure.get("markdown", ""))
    sections = list(presentation.get("sections", []))
    budget_projet_structured = budget_projet.get("structured", {})

    st.markdown("## Resultat final")
    wf4_engine = execution.get("wf4", {}).get("engine", "heuristique_locale")
    wf4_provider = execution.get("wf4", {}).get("provider", "")
    wf4_model = execution.get("wf4", {}).get("model", "")
    if wf4_provider or wf4_model:
        st.caption(
            f"WF4 : `{wf4_engine}`"
            + (f" · provider `{wf4_provider}`" if wf4_provider else "")
            + (f" · modele `{wf4_model}`" if wf4_model else "")
        )
    else:
        st.caption(f"WF4 : `{wf4_engine}`")

    reset_col, info_col = st.columns([1, 3])
    with reset_col:
        if st.button("Reinitialiser les editions", key=f"reset_edits_{pipeline_signature}"):
            st.session_state["editable_wf4"] = deepcopy(pipeline_outputs.get("wf4", {}))
            _clear_editable_wf4_state(pipeline_signature)
            st.rerun()
    with info_col:
        st.caption("Les modifications ci-dessous restent dans la session courante et alimentent les exports de cette page.")

    export_key = f"local_export_paths_{pipeline_signature}"
    export_error_key = f"local_export_error_{pipeline_signature}"
    if st.button("Exporter localement dans le dossier exports", key=f"export_local_{pipeline_signature}"):
        try:
            written_paths = write_local_export_files(pipeline_signature, wf4, pipeline_outputs)
            st.session_state[export_key] = [str(path) for path in written_paths]
            st.session_state[export_error_key] = ""
            opened, open_error = open_local_exports_dir()
            if not opened and open_error:
                st.session_state[export_error_key] = open_error
        except Exception as exc:  # noqa: BLE001
            st.session_state[export_key] = []
            st.session_state[export_error_key] = str(exc)
    if export_key in st.session_state:
        if st.session_state[export_key]:
            st.success("Exports locaux generes dans le dossier `exports/`.")
            st.caption(f"Dossier local : `{EXPORT_DIR}`")
            for raw_path in st.session_state[export_key]:
                path_obj = Path(raw_path)
                st.markdown(f"- `{path_obj.name}`")
            if st.session_state.get(export_error_key):
                st.warning(
                    "Les fichiers ont bien ete generes, mais l'ouverture automatique du dossier a echoue. "
                    f"Ouvre manuellement : `{EXPORT_DIR}`"
                )
        elif st.session_state.get(export_error_key):
            st.error(f"Echec de l'export local : {st.session_state[export_error_key]}")

    open_dir_key = f"open_exports_dir_{pipeline_signature}"
    if st.button("Ouvrir le dossier exports", key=open_dir_key):
        opened, open_error = open_local_exports_dir()
        if opened:
            st.success(f"Dossier ouvert : `{EXPORT_DIR}`")
        else:
            st.error(f"Impossible d'ouvrir automatiquement le dossier : {open_error}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sections presentation", str(len(sections)))
    col2.metric("Budget projet", "pret" if budget_projet_structured else "absent")
    col3.metric("Budget structure", "oui" if budget_structure.get("required") else "non")
    col4.metric("Points a completer", str(len(checklist)))

    st.markdown("### Sortie principale attendue")
    st.write(str(rapport.get("resume_executif", wf3.get("resume_executif", "Aucun resume disponible."))))

    st.markdown("### Livrables de candidature")
    liv_tab_1, liv_tab_2, liv_tab_3, liv_tab_4 = st.tabs([
        "Presentation projet",
        "Budget projet",
        "Budget structure",
        "Points a completer",
    ])

    with liv_tab_1:
        if sections:
            edited_sections = []
            status_options = ["redige", "partiel", "a_completer", "a_confirmer"]
            for index, section in enumerate(sections):
                title = str(section.get("section", "Section"))
                current_status = str(section.get("statut", "a_completer"))
                status_key = f"edit_presentation_status_{pipeline_signature}_{index}"
                content_key = f"edit_presentation_content_{pipeline_signature}_{index}"
                if status_key not in st.session_state:
                    st.session_state[status_key] = current_status if current_status in status_options else "partiel"
                if content_key not in st.session_state:
                    st.session_state[content_key] = str(section.get("contenu", ""))
                with st.expander(f"{title} · {st.session_state[status_key]}", expanded=False):
                    new_status = st.selectbox(
                        "Statut de la section",
                        options=status_options,
                        key=status_key,
                    )
                    new_content = st.text_area(
                        "Contenu de la section",
                        key=content_key,
                        height=260,
                    )
                    edited_sections.append(
                        {
                            "section": title,
                            "statut": new_status,
                            "contenu": new_content,
                        }
                    )
            presentation["sections"] = edited_sections
            presentation["markdown"] = build_project_presentation_markdown(edited_sections)
            presentation_markdown = str(presentation.get("markdown", ""))
        else:
            st.info("Aucune section de presentation n'a ete produite.")
        pres_dl_col1, pres_dl_col2 = st.columns(2)
        pres_dl_col1.download_button(
            "Telecharger la presentation projet",
            data=presentation_markdown,
            file_name="presentation_projet.md",
            mime="text/markdown",
            key="download_final_presentation",
        )
        if pres_dl_col2.button("Enregistrer la presentation dans exports", key=f"save_presentation_exports_{pipeline_signature}"):
            path = export_single_local_file("presentation_projet.md", presentation_markdown)
            st.success(f"Fichier enregistre : `{path}`")

    with liv_tab_2:
        charges = list(budget_projet_structured.get("charges", []))
        produits = list(budget_projet_structured.get("produits", []))
        if budget_projet_structured:
            budget_meta = budget_projet_structured.get("metadata", {}) if isinstance(budget_projet_structured.get("metadata", {}), dict) else {}
            financeur = budget_meta.get("financeur_principal", {}) if isinstance(budget_meta.get("financeur_principal", {}), dict) else {}
            periode = budget_meta.get("periode", {}) if isinstance(budget_meta.get("periode", {}), dict) else {}
            structure = budget_meta.get("structure_porteuse", {}) if isinstance(budget_meta.get("structure_porteuse", {}), dict) else {}
            meta_lines = []
            description = str(budget_meta.get("description", "")).strip()
            if description:
                meta_lines.append(description)
            synthese_financements = str(budget_meta.get("synthese_financements", "")).strip()
            if synthese_financements:
                meta_lines.append(f"Synthese financements : {synthese_financements}")
            if financeur:
                financeur_bits = [str(financeur.get("nom", "")).strip(), str(financeur.get("type", "")).strip()]
                if str(financeur.get("taux_max", "")).strip():
                    financeur_bits.append(f"taux max {financeur.get('taux_max')}")
                if str(financeur.get("plafond", "")).strip():
                    financeur_bits.append(f"plafond {financeur.get('plafond')}")
                meta_lines.append("Financeur principal : " + " | ".join(bit for bit in financeur_bits if bit))
            if periode and (periode.get("debut") or periode.get("fin")):
                meta_lines.append(f"Periode : {periode.get('debut', 'A_COMPLETER')} -> {periode.get('fin', 'A_COMPLETER')}")
            if structure:
                structure_bits = [str(structure.get("nom", "")).strip(), str(structure.get("forme_juridique", "")).strip()]
                if str(structure.get("territoire", "")).strip():
                    structure_bits.append(str(structure.get("territoire", "")).strip())
                meta_lines.append("Structure porteuse : " + " | ".join(bit for bit in structure_bits if bit))
            if meta_lines:
                st.markdown("#### Contexte budgetaire")
                for line in meta_lines:
                    st.write(f"- {line}")
            st.markdown("#### Charges")
            charges_df = pd.DataFrame(
                charges
                or [{"section": "", "sous_section": "", "poste": "", "montant_previsionnel": "", "commentaire": "", "statut": "", "source": ""}]
            )
            edited_charges = st.data_editor(
                charges_df,
                use_container_width=True,
                num_rows="dynamic",
                key=f"edit_budget_project_charges_{pipeline_signature}",
            )
            st.markdown("#### Produits")
            produits_df = pd.DataFrame(
                produits
                or [{"section": "", "sous_section": "", "poste": "", "montant_previsionnel": "", "commentaire": "", "statut": "", "source": ""}]
            )
            edited_produits = st.data_editor(
                produits_df,
                use_container_width=True,
                num_rows="dynamic",
                key=f"edit_budget_project_produits_{pipeline_signature}",
            )
            budget_projet_structured["charges"] = edited_charges.fillna("").to_dict("records")
            budget_projet_structured["produits"] = edited_produits.fillna("").to_dict("records")
            budget_projet["structured"] = budget_projet_structured
            budget_projet["markdown"] = build_project_budget_markdown(budget_projet_structured)
            notes = list(budget_projet_structured.get("notes", []))
            if notes:
                st.markdown("#### Notes budgetaires")
                for note in notes:
                    st.write(f"- {note}")
            budget_project_csv = _budget_to_dataframe(budget_projet_structured).to_csv(index=False)
        else:
            st.info("Aucune trame budget projet n'a ete produite.")
            budget_project_csv = ""
        budget_projet_markdown = str(budget_projet.get("markdown", ""))
        download_col1, download_col2 = st.columns(2)
        download_col1.download_button(
            "Telecharger la trame budget projet",
            data=budget_projet_markdown,
            file_name="budget_projet.md",
            mime="text/markdown",
            key="download_final_budget_projet",
        )
        download_col2.download_button(
            "Telecharger le budget projet en CSV",
            data=budget_project_csv,
            file_name="budget_projet.csv",
            mime="text/csv",
            key="download_final_budget_projet_csv",
        )
        budget_save_col1, budget_save_col2 = st.columns(2)
        if budget_save_col1.button("Enregistrer budget projet (.md)", key=f"save_budget_project_md_{pipeline_signature}"):
            path = export_single_local_file("budget_projet.md", budget_projet_markdown)
            st.success(f"Fichier enregistre : `{path}`")
        if budget_save_col2.button("Enregistrer budget projet (.csv)", key=f"save_budget_project_csv_{pipeline_signature}"):
            path = EXPORT_DIR / "budget_projet.csv"
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(budget_project_csv, encoding="utf-8")
            st.success(f"Fichier enregistre : `{path}`")

    with liv_tab_3:
        if budget_structure.get("required"):
            st.success("Un budget de structure semble requis par l'appel.")
            structure_structured = budget_structure.get("structured", {}) or {}
            if structure_structured:
                st.markdown("#### Charges de structure")
                structure_charges_df = pd.DataFrame(
                    list(structure_structured.get("charges", [])) or [{"poste": "", "montant_previsionnel": "", "commentaire": ""}]
                )
                edited_structure_charges = st.data_editor(
                    structure_charges_df,
                    use_container_width=True,
                    num_rows="dynamic",
                    key=f"edit_budget_structure_charges_{pipeline_signature}",
                )
                st.markdown("#### Produits de structure")
                structure_produits_df = pd.DataFrame(
                    list(structure_structured.get("produits", [])) or [{"poste": "", "montant_previsionnel": "", "commentaire": ""}]
                )
                edited_structure_produits = st.data_editor(
                    structure_produits_df,
                    use_container_width=True,
                    num_rows="dynamic",
                    key=f"edit_budget_structure_produits_{pipeline_signature}",
                )
                structure_structured["charges"] = edited_structure_charges.fillna("").to_dict("records")
                structure_structured["produits"] = edited_structure_produits.fillna("").to_dict("records")
                budget_structure["structured"] = structure_structured
                budget_structure["markdown"] = build_project_budget_markdown(structure_structured)
                budget_structure_markdown = str(budget_structure.get("markdown", ""))
                structure_notes = list(structure_structured.get("notes", []))
                if structure_notes:
                    st.markdown("#### Notes budget structure")
                    for note in structure_notes:
                        st.write(f"- {note}")
                structure_csv = _budget_to_dataframe(structure_structured).to_csv(index=False)
            else:
                structure_csv = ""
            if budget_structure_markdown:
                structure_dl_col1, structure_dl_col2 = st.columns(2)
                structure_dl_col1.download_button(
                    "Telecharger la trame budget structure",
                    data=budget_structure_markdown,
                    file_name="budget_structure.md",
                    mime="text/markdown",
                    key="download_final_budget_structure",
                )
                structure_dl_col2.download_button(
                    "Telecharger le budget structure en CSV",
                    data=structure_csv,
                    file_name="budget_structure.csv",
                    mime="text/csv",
                    key="download_final_budget_structure_csv",
                )
                structure_save_col1, structure_save_col2 = st.columns(2)
                if structure_save_col1.button("Enregistrer budget structure (.md)", key=f"save_budget_structure_md_{pipeline_signature}"):
                    path = export_single_local_file("budget_structure.md", budget_structure_markdown)
                    st.success(f"Fichier enregistre : `{path}`")
                if structure_save_col2.button("Enregistrer budget structure (.csv)", key=f"save_budget_structure_csv_{pipeline_signature}"):
                    path = EXPORT_DIR / "budget_structure.csv"
                    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
                    path.write_text(structure_csv, encoding="utf-8")
                    st.success(f"Fichier enregistre : `{path}`")
        else:
            st.info("Aucun budget de structure requis n'a ete detecte.")

    with liv_tab_4:
        if checklist:
            checklist_df = pd.DataFrame(checklist)
            edited_checklist = st.data_editor(
                checklist_df,
                use_container_width=True,
                num_rows="dynamic",
                key=f"edit_checklist_{pipeline_signature}",
            )
            livrables["points_a_completer"] = edited_checklist.fillna("").to_dict("records")
        else:
            st.info("Aucun point de completion remonte.")

    with st.expander("Analyse secondaire et traçabilite", expanded=False):
        meta1, meta2, meta3, meta4 = st.columns(4)
        meta1.metric("Statut", str(wf3.get("statut_eligibilite", "a confirmer")))
        meta2.metric("Score", f"{wf3.get('score_global', 0)}/100")
        meta3.metric("Provider", str(execution.get("llm_selection", {}).get("provider", "local") or "local"))
        meta4.metric("Modele", str(execution.get("llm_selection", {}).get("model", "heuristique") or "heuristique"))

        st.markdown("#### Points forts")
        for item in rapport.get("points_valides", [])[:5] or ["Aucun point fort clairement valide"]:
            st.write(f"- {item}")

        st.markdown("#### Points a confirmer")
        for item in rapport.get("points_a_confirmer", [])[:5] or ["Aucun point intermediaire majeur"]:
            st.write(f"- {item}")

        st.markdown("#### Points bloquants")
        for item in rapport.get("points_bloquants", [])[:5] or ["Aucun blocage majeur detecte"]:
            st.write(f"- {item}")

        st.markdown("#### Actions prioritaires")
        for item in rapport.get("recommandations", [])[:5] or ["Aucune action urgente"]:
            st.write(f"- {item}")

        st.download_button(
            "Telecharger la sortie JSON complete",
            data=json.dumps({**pipeline_outputs, "wf4": wf4}, ensure_ascii=False, indent=2),
            file_name="resultat_pipeline.json",
            mime="application/json",
            key="download_final_json",
        )

    save_editable_wf4(pipeline_signature, wf4)


# ── Global summary sections ───────────────────────────────────────────────────

def render_global_summary(summary_map: dict[str, list[dict[str, str]]]) -> None:
    st.subheader("Recapitulatif global")
    col1, col2, col3 = st.columns(3)

    loaded_count = sum(1 for value in summary_map.values() if value)
    col1.metric("Blocs complets", str(loaded_count))
    col2.metric("Blocs manquants", str(len(summary_map) - loaded_count))
    col3.metric("Documents charges", str(sum(len(value) for value in summary_map.values())))

    for block_name, infos in summary_map.items():
        if not infos:
            st.warning(f"{block_name} : aucun document charge")
        else:
            st.success(f"{block_name} : {len(infos)} document(s)")
            for info in infos:
                st.write(f"- {info['Nom']} | {info['Type']} | {info['Taille']}")


def render_cross_block_summary(summary: dict[str, str]) -> None:
    st.subheader("Synthese globale inter-blocs")

    col1, col2 = st.columns(2)
    col1.metric("Preparation", summarize_readiness_label(summary.get("Etat global", "inconnu")))
    col2.metric("Solidite", summarize_prescore_label(summary.get("Pre-score global", "inconnu")))

    st.markdown("### Lecture rapide")
    st.write(f"**Blocs disponibles** : {summary.get('Blocs disponibles', 'Aucun')}")
    st.write(f"**Blocs encore manquants** : {summary.get('Blocs manquants', 'Aucun')}")

    st.markdown("### Priorites retenues")
    st.write(f"- Date de reference : {summary.get('Date prioritaire', 'Aucune')}")
    st.write(f"- Organisme principal : {summary.get('Organisme prioritaire', 'Aucun')}")
    st.write(f"- Montant de reference : {summary.get('Montant prioritaire', 'Aucun')}")

    st.markdown("### Vigilances")
    control_items = split_display_items(summary.get("Controle simple", "Aucun"))
    issue_items = split_display_items(summary.get("Incoherences detectees", "Aucune"))
    if control_items:
        for item in control_items:
            st.write(f"- {item}")
    else:
        st.write("- aucun controle simple remonte")
    if issue_items:
        for item in issue_items:
            st.write(f"- {item}")
    else:
        st.write("- aucune incoherence simple detectee")

    st.markdown("### Actions par bloc")
    st.write(f"- Dossier : {summary.get('Action dossier', 'Aucune')}")
    st.write(f"- Client : {summary.get('Action client', 'Aucune')}")
    st.write(f"- Projet : {summary.get('Action projet', 'Aucune')}")

    with st.expander("Voir les details detectes par bloc", expanded=False):
        st.write(f"**Statut des blocs** : {summary.get('Statut des blocs', 'Aucun')}")
        st.write(f"**Criteres dossier** : {summary.get('Criteres dossier', 'Aucun')}")
        st.write(f"**Criteres client** : {summary.get('Criteres client', 'Aucun')}")
        st.write(f"**Criteres projet** : {summary.get('Criteres projet', 'Aucun')}")
        st.write(f"**Organismes par bloc** : {summary.get('Organismes par bloc', 'Aucun')}")
        st.write(f"**Dates par bloc** : {summary.get('Dates par bloc', 'Aucune')}")
        st.write(f"**Montants par bloc** : {summary.get('Montants par bloc', 'Aucun')}")


def render_global_context_bridge(global_bridge: dict[str, str]) -> None:
    st.subheader("Pont global - Contexte documentaire et fiabilite")

    col1, col2, col3 = st.columns(3)
    col1.metric("Preparation du dossier", summarize_readiness_label(global_bridge.get("etat_global_documentaire", "inconnue")))
    col2.metric("Solidite documentaire", summarize_prescore_label(global_bridge.get("prescore_global_documentaire", "inconnue")))
    col3.metric("Blocs exploites", global_bridge.get("blocs_disponibles", "Aucun"))

    st.markdown("### Lecture metier")
    st.write(f"**Etat de preparation** : {global_bridge.get('etat_global_documentaire', 'inconnu')}")
    st.write(f"**Points de vigilance avant analyse** : {global_bridge.get('incoherences_globales', 'Aucune')}")
    st.write(f"**Actions a traiter en priorite** : {global_bridge.get('actions_prealables', 'Aucune')}")

    st.markdown("### Qualite du socle documentaire")
    st.write(f"**Blocs encore manquants** : {global_bridge.get('blocs_manquants', 'Aucun')}")
    st.write(f"**Niveau des blocs** : {global_bridge.get('statut_blocs', 'Aucun')}")
    st.write(f"**Lecture transversale possible** : {global_bridge.get('controle_global', 'Aucun')}")

    st.markdown("### Signaux prioritaires retenus")
    st.write(f"**Date de reference la plus utile** : {global_bridge.get('priorite_date', 'Aucune')}")
    st.write(f"**Organisme le plus probable** : {global_bridge.get('priorite_organisme', 'Aucun')}")
    st.write(f"**Montant de reference** : {global_bridge.get('priorite_montant', 'Aucun')}")

    with st.expander("Voir la fiabilite par bloc", expanded=False):
        st.write(f"**Fiabilite du bloc dossier** : {global_bridge.get('fiabilite_dossier', 'Aucun')}")
        st.write(f"**Fiabilite du bloc client** : {global_bridge.get('fiabilite_client', 'Aucun')}")
        st.write(f"**Fiabilite du bloc projet** : {global_bridge.get('fiabilite_projet', 'Aucun')}")

    with st.expander("Voir la provenance et le contexte fin", expanded=False):
        st.write(f"**Provenance dossier** : {global_bridge.get('provenance_dossier', 'Aucune')}")
        st.write(f"**Provenance client** : {global_bridge.get('provenance_client', 'Aucune')}")
        st.write(f"**Provenance projet** : {global_bridge.get('provenance_projet', 'Aucune')}")
        st.write(f"**Mots-cles dossier** : {global_bridge.get('mots_cles_dossier', 'Aucun')}")
        st.write(f"**Mots-cles client** : {global_bridge.get('mots_cles_client', 'Aucun')}")
        st.write(f"**Mots-cles projet** : {global_bridge.get('mots_cles_projet', 'Aucun')}")
        st.write(f"**Resume pont metier** : {global_bridge.get('resume_pont_metier', 'Aucun')}")
        st.write(f"**Actions prealables** : {global_bridge.get('actions_prealables', 'Aucune')}")


# ── Block summary / upload sections ──────────────────────────────────────────

def render_block_summary(title: str, uploaded_files) -> None:
    st.markdown(f"## Synthese du bloc : {title}")

    type_counts: dict[str, int] = {}
    total_size = 0
    for uploaded_file in uploaded_files:
        suffix = get_uploaded_suffix(uploaded_file)
        type_counts[suffix] = type_counts.get(suffix, 0) + 1
        total_size += uploaded_file.size

    col1, col2, col3 = st.columns(3)
    col1.metric("Documents", str(len(uploaded_files)))
    col2.metric("Types detectes", str(len(type_counts)))
    col3.metric("Taille totale", f"{total_size} octets")

    st.write(
        "Repartition : "
        + ", ".join(f"`{file_type}` x {count}" for file_type, count in sorted(type_counts.items()))
    )
    with st.expander("Voir la synthese detaillee du bloc", expanded=False):
        render_metadata(assess_block_completeness(uploaded_files), title="Completude du bloc")
        render_metadata(collect_block_insights(uploaded_files), title="Signaux detectes dans le bloc")


def process_uploaded_file(uploaded_file, category_label: str, file_index: int) -> None:
    st.markdown(f"### {category_label} - fichier {file_index}")
    st.success("Document recu avec succes.")

    col1, col2 = st.columns(2)
    col1.write(f"Nom : `{uploaded_file.name}`")
    col2.write(f"Taille : `{uploaded_file.size}` octets")

    suffix = get_uploaded_suffix(uploaded_file)
    file_bytes = get_uploaded_bytes(uploaded_file)
    st.write(f"Type detecte : `{suffix}`")

    if suffix in {".txt", ".md"}:
        text_content = parse_text_bytes(file_bytes)
        with st.expander("Voir les metadonnees detectees", expanded=False):
            render_metadata(extract_text_metadata(text_content, uploaded_file.name))
        with st.expander("Voir l'apercu texte", expanded=False):
            st.text_area("Contenu detecte", text_content[:5000], height=250)
        render_normalized_text(text_content, uploaded_file.name, expanded=False)
        st.write("Etape suivante : nettoyer et structurer ce texte.")
        return

    if suffix == ".csv":
        dataframe = parse_csv_bytes(file_bytes)
        with st.expander("Voir les metadonnees detectees", expanded=False):
            render_metadata(extract_table_metadata(dataframe, uploaded_file.name))
        with st.expander("Voir l'apercu tabulaire", expanded=False):
            st.dataframe(dataframe, use_container_width=True)
        st.write(f"Nombre de lignes : `{len(dataframe)}`")
        st.write(f"Nombre de colonnes : `{len(dataframe.columns)}`")
        normalized_text = dataframe_to_markdown(dataframe, uploaded_file.name)
        render_normalized_text(normalized_text, uploaded_file.name, expanded=False)
        return

    if suffix == ".xlsx":
        workbook = parse_excel_bytes(file_bytes)
        sheet_names = list(workbook.keys())
        business_sheets, informative_sheets = filter_business_sheets(workbook)
        displayed_sheets = business_sheets if business_sheets else workbook

        st.markdown("### Feuilles detectees")
        st.write(", ".join(f"`{name}`" for name in sheet_names))
        if informative_sheets:
            st.info("Feuilles informatives detectees : " + ", ".join(f"`{name}`" for name in informative_sheets))

        first_sheet_name = next(iter(displayed_sheets.keys()))
        first_df = displayed_sheets[first_sheet_name]
        metadata = extract_table_metadata(first_df, uploaded_file.name)
        metadata["Nombre de feuilles"] = str(len(sheet_names))
        metadata["Feuilles metier"] = str(len(displayed_sheets))
        with st.expander("Voir les metadonnees detectees", expanded=False):
            render_metadata(metadata)

        with st.expander("Voir l'apercu Excel par feuille", expanded=False):
            for sheet_name, sheet_df in displayed_sheets.items():
                csv_content = sheet_df.to_csv(index=False)
                with st.expander(f"Feuille : {sheet_name}", expanded=False):
                    st.dataframe(sheet_df, use_container_width=True)
                    st.write(f"Lignes : `{len(sheet_df)}`")
                    st.write(f"Colonnes : `{len(sheet_df.columns)}`")
                    st.text_area(
                        f"CSV genere - {sheet_name}",
                        csv_content[:5000],
                        height=180,
                        key=f"csv_preview_{uploaded_file.name}_{sheet_name}",
                    )
                    st.download_button(
                        f"Telecharger {sheet_name} en CSV",
                        data=csv_content,
                        file_name=f"{Path(uploaded_file.name).stem}_{sheet_name}.csv",
                        mime="text/csv",
                        key=f"csv_download_{uploaded_file.name}_{sheet_name}",
                    )
        normalized_text = workbook_to_markdown(workbook, uploaded_file.name)
        render_normalized_text(normalized_text, uploaded_file.name, expanded=False)
        return

    if suffix == ".pdf":
        pdf_text, page_count, text_page_count, pdf_error = parse_pdf_bytes(file_bytes)

        if pdf_error:
            st.error(f"Lecture PDF impossible : {pdf_error}")
            st.write("Ce fichier peut etre corrompu, mal exporte, ou non conforme au format PDF attendu.")
            st.write("Le bloc continue a fonctionner, mais ce document n'est pas exploitable pour l'instant.")
            return

        if not pdf_text:
            st.warning("Le PDF a ete charge, mais aucun texte exploitable n'a ete detecte.")
            st.write("Il est possible que le document soit scanne ou image.")
            return

        with st.expander("Voir les metadonnees detectees", expanded=False):
            render_metadata(extract_text_metadata(pdf_text, uploaded_file.name))
        with st.expander("Voir l'apercu PDF", expanded=False):
            st.text_area("Texte detecte", pdf_text[:5000], height=300)
        st.write(f"Pages lues : `{page_count}`")
        st.write(f"Pages avec texte : `{text_page_count}`")
        render_normalized_text(pdf_text, uploaded_file.name, expanded=False)
        return

    if suffix == ".docx":
        text_content, markdown_content, paragraph_count = parse_docx_bytes(file_bytes)

        if not text_content:
            st.warning("Le document DOCX a ete charge, mais aucun texte exploitable n'a ete trouve.")
            return

        with st.expander("Voir les metadonnees detectees", expanded=False):
            render_metadata(extract_text_metadata(text_content, uploaded_file.name))
        with st.expander("Voir l'apercu DOCX", expanded=False):
            st.text_area("Texte detecte", text_content[:5000], height=300)
        st.write(f"Paragraphes detectes : `{paragraph_count}`")
        with st.expander("Voir la conversion Markdown", expanded=False):
            st.text_area("Markdown genere", markdown_content[:5000], height=260)
            st.download_button(
                "Telecharger en Markdown",
                data=markdown_content,
                file_name=f"{Path(uploaded_file.name).stem}.md",
                mime="text/markdown",
            )
        render_normalized_text(markdown_content, uploaded_file.name, expanded=False)
        return

    st.write("Etape suivante : lecture du contenu et extraction de texte.")


def render_upload_block(title: str, help_text: str, uploader_key: str):
    st.subheader(title)
    st.caption(help_text)
    uploaded_files = st.file_uploader(
        f"Depose un ou plusieurs documents pour : {title}",
        type=["pdf", "docx", "txt", "md", "csv", "xlsx"],
        key=uploader_key,
        accept_multiple_files=True,
    )

    if not uploaded_files:
        st.info("Aucun document charge pour ce bloc.")
        return []

    for index, uploaded_file in enumerate(uploaded_files, start=1):
        process_uploaded_file(uploaded_file, title, index)
        if index < len(uploaded_files):
            st.divider()

    st.divider()
    render_block_summary(title, uploaded_files)
    block_normalized_text = build_block_normalized_text(title, uploaded_files)
    render_normalized_text(
        block_normalized_text,
        title.replace(" ", "_").lower(),
        expanded=False,
        section_title="Source normalisee fusionnee du bloc",
    )

    return uploaded_files


def render_upload() -> None:
    st.subheader("Upload structure en 3 blocs")
    st.write(
        "Le flux metier repose sur trois types de documents distincts : dossier, client et projet."
    )

    summary_map = {}
    block_files_map = {}

    block_files_map["Documents dossier"] = render_upload_block(
        "Documents dossier",
        "Documents cibles a analyser : appel a projets, reglement, cahier des charges, cadre d'intervention.",
        "upload_dossier",
    )
    summary_map["Documents dossier"] = [
        build_upload_summary(uploaded_file) for uploaded_file in block_files_map["Documents dossier"]
    ]
    st.divider()
    block_files_map["Documents client"] = render_upload_block(
        "Documents client",
        "Documents qui decrivent la structure porteuse : presentation, statuts, references, plaquette.",
        "upload_client",
    )
    summary_map["Documents client"] = [
        build_upload_summary(uploaded_file) for uploaded_file in block_files_map["Documents client"]
    ]
    st.divider()
    block_files_map["Documents projet"] = render_upload_block(
        "Documents projet",
        "Documents qui decrivent l'action ou la demande : note d'intention, budget, description du projet.",
        "upload_projet",
    )
    summary_map["Documents projet"] = [
        build_upload_summary(uploaded_file) for uploaded_file in block_files_map["Documents projet"]
    ]
    st.divider()
    render_global_summary(summary_map)

    cross_summary = build_global_cross_block_summary(block_files_map)
    bridge = build_comparable_bridge(
        block_files_map["Documents dossier"],
        block_files_map["Documents client"],
        block_files_map["Documents projet"],
    )
    global_context_bridge = build_global_context_bridge(
        block_files_map,
        cross_summary,
        bridge,
    )
    files_signature = build_files_signature(block_files_map)
    active_pipeline_outputs = get_active_pipeline_outputs(files_signature)

    st.divider()
    diagnostic_tab, extraction_tab, bridge_tab, wf4_tab = st.tabs(
        ["Diagnostic prioritaire", "Extractions detaillees", "Ponts et completions", "WF4 sorties"]
    )

    with bridge_tab:
        with st.expander("Pont metier WF2a / WF2b", expanded=True):
            completed_bridge = render_bridge_section(
                bridge,
                block_files_map["Documents dossier"],
                block_files_map["Documents client"],
                block_files_map["Documents projet"],
            )
        with st.expander("Pont global - Contexte documentaire", expanded=False):
            render_global_context_bridge(global_context_bridge)

    st.divider()
    st.markdown("### Execution pilotee")
    llm_ready = describe_llm_readiness()
    supabase_ready = describe_supabase_readiness()
    use_llm_default = (
        llm_ready.get("ANTHROPIC_API_KEY") == "configuree"
        or llm_ready.get("GOOGLE_API_KEY") == "configuree"
        or llm_ready.get("MISTRAL_API_KEY") == "configuree"
    )
    persist_default = (
        supabase_ready.get("SUPABASE_URL") == "configuree"
        and supabase_ready.get("SUPABASE_SERVICE_ROLE_KEY") == "configuree"
    )
    col_exec_1, col_exec_2 = st.columns(2)
    prefer_llm = col_exec_1.checkbox(
        "Preferer un provider LLM pour WF2/WF3",
        value=use_llm_default,
        help="Utilise le provider LLM configure si une cle est presente, sinon repasse automatiquement sur l'heuristique locale.",
    )
    persist_supabase = col_exec_2.checkbox(
        "Persister les resultats dans Supabase",
        value=persist_default,
        help="Enregistre client, dossier, documents, criteres, analyse, resultats et rapport dans Supabase.",
    )

    selected_provider: str | None = None
    selected_model: str | None = None
    if prefer_llm:
        configured_providers = get_configured_providers()
        llm_settings = load_llm_settings()
        if configured_providers:
            st.markdown("#### Choix du moteur LLM")
            col_model_1, col_model_2 = st.columns(2)
            provider_index = configured_providers.index(llm_settings.provider) if llm_settings.provider in configured_providers else 0
            selected_provider = col_model_1.selectbox(
                "Provider LLM",
                options=configured_providers,
                index=provider_index,
                key="upload_llm_provider",
                help="Provider utilise pour cette execution du pipeline.",
            )
            suggested_models = get_model_options(selected_provider)
            default_model = load_llm_settings(provider_override=selected_provider).active_model
            model_choices = list(dict.fromkeys(suggested_models + [default_model, "Autre modele..."]))
            selected_model_option = col_model_2.selectbox(
                "Modele LLM",
                options=model_choices,
                index=model_choices.index(default_model) if default_model in model_choices else 0,
                key="upload_llm_model",
                help="Choisis un modele conseille ou saisis un nom exact personnalise.",
            )
            if selected_model_option == "Autre modele...":
                selected_model = st.text_input(
                    "Nom exact du modele",
                    value=default_model,
                    key="upload_llm_model_custom",
                    help="Nom exact expose par l'API du provider choisi.",
                ).strip()
            else:
                selected_model = selected_model_option
            st.caption(f"Execution LLM ciblee : `{selected_provider}` / `{selected_model or default_model}`")
        else:
            st.info("Aucun provider LLM configure. Le pipeline restera en heuristique locale.")

    selected_client_id: str | None = None
    if persist_supabase:
        st.markdown("#### Client a associer a ce dossier")
        existing_clients = list_clients()
        client_options = {c.label(): c.id for c in existing_clients}

        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            mode = st.radio(
                "Mode",
                ["Selectionner un client existant", "Creer un nouveau client"],
                horizontal=True,
                key="client_select_mode",
                label_visibility="collapsed",
            )

        if mode == "Selectionner un client existant":
            if client_options:
                chosen_label = st.selectbox(
                    "Client",
                    options=list(client_options.keys()),
                    key="client_selector",
                )
                selected_client_id = client_options[chosen_label]
                st.caption(f"ID : `{selected_client_id}`")
            else:
                st.info("Aucun client dans Supabase. Creez-en un ci-dessous.")
        else:
            with st.form("form_new_client", border=True):
                new_nom = st.text_input("Nom de la structure *", key="new_client_nom")
                col_f1, col_f2 = st.columns(2)
                new_forme = col_f1.text_input("Forme juridique", key="new_client_forme")
                new_secteur = col_f2.text_input("Secteur d'activite", key="new_client_secteur")
                col_f3, col_f4 = st.columns(2)
                new_email = col_f3.text_input("Email de contact", key="new_client_email")
                new_tel = col_f4.text_input("Telephone", key="new_client_tel")
                new_siret = st.text_input("SIRET (optionnel)", key="new_client_siret")
                submitted = st.form_submit_button("Creer ce client", type="primary")
                if submitted:
                    if not new_nom.strip():
                        st.error("Le nom de la structure est obligatoire.")
                    else:
                        created = create_client(
                            nom=new_nom,
                            forme_juridique=new_forme or None,
                            secteur_activite=new_secteur or None,
                            contact_email=new_email or None,
                            contact_telephone=new_tel or None,
                            siret=new_siret or None,
                        )
                        if created:
                            st.success(f"Client cree : **{created.nom}** (`{created.id}`).")
                            selected_client_id = created.id
                            st.rerun()
                        else:
                            st.error("Erreur lors de la creation du client dans Supabase.")

    if st.button("Executer le pipeline", key="execute_pipeline_button", type="primary"):
        st.session_state["pipeline_last_error"] = ""
        try:
            with st.spinner("Execution du pipeline en cours..."):
                pipeline_outputs = resolve_pipeline_outputs(
                    block_files_map["Documents dossier"],
                    block_files_map["Documents client"],
                    block_files_map["Documents projet"],
                    completed_bridge=completed_bridge,
                    global_context_bridge=global_context_bridge,
                    prefer_llm=prefer_llm,
                    llm_provider=selected_provider,
                    llm_model=selected_model,
                )
                persistence_result = None
                if persist_supabase:
                    persistence_result = persist_pipeline_outputs(
                        block_files_map["Documents dossier"],
                        block_files_map["Documents client"],
                        block_files_map["Documents projet"],
                        pipeline_outputs,
                        selected_client_id=selected_client_id,
                    )
            store_pipeline_outputs(files_signature, pipeline_outputs, persistence_result)
            active_pipeline_outputs = pipeline_outputs
        except Exception as exc:
            st.session_state["pipeline_last_error"] = f"{exc.__class__.__name__}: {exc}"
            st.error(
                "Le pipeline a rencontre une erreur avant de produire un resultat. "
                "Verifie le provider/modele choisi ou repasse temporairement en heuristique locale."
            )

    pipeline_last_error = st.session_state.get("pipeline_last_error", "")
    if pipeline_last_error:
        st.warning(f"Derniere erreur pipeline : {pipeline_last_error}")

    if active_pipeline_outputs:
        execution_meta = active_pipeline_outputs.get("execution", {})
        st.success("Derniere execution disponible pour les fichiers actuellement charges.")
        render_metadata({
            "WF2a": execution_meta.get("wf2a", {}).get("engine", "heuristique_locale"),
            "WF2b": execution_meta.get("wf2b", {}).get("engine", "heuristique_locale"),
            "WF3": execution_meta.get("wf3", {}).get("engine", "heuristique_locale"),
            "WF4": execution_meta.get("wf4", {}).get("engine", "heuristique_locale"),
            "Provider LLM": execution_meta.get("llm_selection", {}).get("provider", "defaut"),
            "Modele LLM": execution_meta.get("llm_selection", {}).get("model", "defaut"),
            "Agent budget projet": execution_meta.get("wf4", {}).get("budget_project_agent_id", "") or "non configure",
            "Fallback": "oui"
            if any(
                step.get("fallback_used")
                for step in execution_meta.values()
                if isinstance(step, dict)
            )
            else "non",
        })
        if execution_meta.get("wf4", {}).get("fallback_used"):
            st.warning(
                "WF4 est repasse en fallback heuristique sur cette execution. "
                "Le livrable affiche peut donc etre plus pauvre que prevu."
            )
        persistence_result = st.session_state.get("pipeline_persistence", {})
        if persistence_result:
            if persistence_result.get("ok"):
                st.caption(
                    f"Supabase : analyse {persistence_result.get('analyse_id')} enregistree, "
                    f"{persistence_result.get('documents_count', 0)} document(s), "
                    f"{persistence_result.get('criteres_count', 0)} critere(s)."
                )
            else:
                st.warning(f"Persistance Supabase non finalisee : {persistence_result.get('error', 'erreur inconnue')}")
        st.divider()
        render_final_result_summary(active_pipeline_outputs)
    else:
        st.info("Aucune execution pilotee en memoire pour les fichiers actuels. Les vues ci-dessous utilisent les sorties locales par defaut.")

    with diagnostic_tab:
        st.markdown("### Lecture prioritaire")
        render_cross_block_summary(cross_summary)
        st.divider()
        render_wf3_section(
            block_files_map["Documents dossier"],
            block_files_map["Documents client"],
            block_files_map["Documents projet"],
            bridge=completed_bridge,
            global_bridge=global_context_bridge,
            pipeline_outputs=active_pipeline_outputs,
        )

    with extraction_tab:
        with st.expander("WF2a local - Criteres dossier", expanded=True):
            render_wf2a_dossier_section(
                block_files_map["Documents dossier"],
                wf2a_structured=active_pipeline_outputs.get("wf2a") if active_pipeline_outputs else None,
                execution_meta=active_pipeline_outputs.get("execution", {}).get("wf2a") if active_pipeline_outputs else None,
            )
        with st.expander("WF2b local - Profil client et donnees projet", expanded=True):
            render_wf2b_section(
                block_files_map["Documents client"],
                block_files_map["Documents projet"],
                wf2b_structured=active_pipeline_outputs.get("wf2b") if active_pipeline_outputs else None,
                execution_meta=active_pipeline_outputs.get("execution", {}).get("wf2b") if active_pipeline_outputs else None,
            )

    with wf4_tab:
        render_wf4_section(
            block_files_map["Documents dossier"],
            block_files_map["Documents client"],
            block_files_map["Documents projet"],
            bridge=completed_bridge,
            global_bridge=global_context_bridge,
            pipeline_outputs=active_pipeline_outputs,
        )
