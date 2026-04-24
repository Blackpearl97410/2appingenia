# Memoire Projet

## Objet

Ce fichier sert de memo de travail pour reprendre rapidement le projet sans relire toute la conversation.

Il resume :
- ce qui a ete construit ;
- ce qui a ete corrige ;
- les limites actuelles ;
- les prochaines etapes recommandees.

## Contexte produit

Le projet vise un back-office interne d'analyse de dossiers de financement public, aligne sur la logique `Subly` decrite dans `contexte/# CLAUDE.md`.

Les grands attendus confirms :
- 3 types de documents : `dossier`, `client`, `projet`
- pipeline cible : `WF1 -> WF2a -> WF2b -> WF3 -> WF4`
- 4 sorties metier finales :
  - score d'eligibilite
  - rapport structure
  - pre-remplissage
  - suggestions alternatives

## Etat actuel du prototype

Le prototype actuel est une application `Streamlit` dans `streamlit_app.py`.

Elle permet deja :
- upload multi-fichiers par bloc `dossier`, `client`, `projet`
- lecture de fichiers `txt`, `md`, `csv`, `xlsx`, `docx`, `pdf`
- affichage des metadonnees simples
- normalisation des contenus en texte/markdown
- synthese par bloc
- synthese globale inter-blocs
- extraction locale `WF2a`
- extraction locale `WF2b`
- pont local de donnees comparables entre `WF2a` et `WF2b`
- premier `WF3 local`

## Ce qui a ete fait

### Interface

- Creation d'une interface Streamlit stable et deployable sur Streamlit Cloud
- Passage d'un upload unique a 3 blocs distincts :
  - `Documents dossier`
  - `Documents client`
  - `Documents projet`
- Passage d'un upload unitaire a un upload multiple par bloc
- Ajout d'un recapitulatif global des fichiers charges

### Formats pris en charge

- `txt`
- `md`
- `csv`
- `xlsx`
- `docx`
- `pdf`

### Normalisation

- `docx` -> texte + markdown
- `xlsx` -> CSV par feuille + source normalisee globale du classeur
- `csv` -> tableau + markdown simple
- `txt` / `md` -> texte normalise
- `pdf` -> texte extrait quand lisible

### Refactoring architecture

Avancee majeure ajoutee ensuite :
- debut du vrai allegement de `streamlit_app.py` sans casser l'app
- extraction des parseurs dans `app/services/parsers.py`
- extraction des metadonnees et helpers documentaires dans `app/services/metadata.py`
- extraction des fonctions de normalisation dans `app/services/normalizers.py`
- `streamlit_app.py` continue de piloter l'interface mais s'appuie deja sur ces modules

Point important :
- la dette architecturale n'est pas encore resolue completement
- mais le refactoring progressif a commence sans reintroduire la fragilite du debut

### Intelligence documentaire locale

- metadonnees simples detectees :
  - titre probable
  - type probable
  - date detectee
  - montant detecte
  - organisme detecte
- synthese metier par bloc
- statut de completude par bloc :
  - `vide`
  - `partiel`
  - `suffisant`
- synthese globale inter-blocs
- pre-score global simple
- actions recommandees par bloc

### WF2a local

Section dediee dans l'interface :
- extraction de premiers criteres dossier
- structure actuelle des criteres :
  - `categorie`
  - `domaine`
  - `libelle`
  - `detail`

Avancee majeure ajoutee ensuite :
- refonte de `WF2a` pour une sortie preparee pour un futur LLM
- chaque critere structure contient maintenant :
  - `categorie`
  - `domaine`
  - `libelle`
  - `detail`
  - `source_document`
  - `source_texte`
  - `est_piece_exigee`
  - `est_critere_eliminatoire`
  - `niveau_confiance`
  - `necessite_validation`
- ajout d'une metadata `WF2a` :
  - type dossier detecte
  - financeur detecte
  - montant max detecte
  - date limite detectee
  - nombre de criteres extraits

Limite :
- extraction encore heuristique
- mais schema de sortie beaucoup plus proche de la cible LLM / table `criteres`

### WF2b local

Section dediee dans l'interface :

Profil client :
- forme juridique
- siret
- email
- telephone
- activites detectees

Donnees projet :
- titre projet
- montant detecte
- dates detectees
- elements detectes

Avancee majeure ajoutee ensuite :
- refonte de `WF2b` en structure preparee pour LLM :
  - `profil_client`
  - `donnees_projet`
  - `metadata`
- chaque champ principal peut maintenant porter :
  - `value`
  - `source_document`
  - `source_texte`
  - `niveau_confiance`
  - `necessite_validation`

Limite :
- la logique d'extraction reste heuristique
- mais le contrat de donnees est maintenant beaucoup plus stable pour la suite

### Pont WF2a / WF2b

Section dediee dans l'interface :
- `type_structure_requise`
- `date_limite_dossier`
- `montant_dossier`
- `conditions_dossier`
- `type_structure_client`
- `identite_client`
- `montant_projet`
- `dates_projet`
- `elements_projet`

Ce pont a ete ajoute parce que `WF2a` et `WF2b` seuls n'etaient pas suffisants pour un futur `WF3`.

Avancee majeure ajoutee ensuite :
- widget de completion manuelle des donnees manquantes du pont
- correction manuelle possible avant le `WF3 local`
- le `WF3` peut maintenant s'appuyer sur les donnees detectees puis reajustees par l'utilisateur
- widget devenu contextuel selon les pieces detectees :
  - reglement / appel / formulaire
  - statuts / references / presentation
  - budget / planning / projet
- champs proposes plus fins selon les documents charges
- le pont est maintenant alimente a partir des nouvelles sorties structurees `WF2a` et `WF2b`

### WF3 local

Ajoute dans l'interface :
- comparaison locale entre `dossier`, `client`, `projet`
- sortie :
  - `compatible`
  - `a confirmer`
  - `partiellement compatible`
  - `non compatible`
- score local sur 100
- justifications
- manques a combler

Avancee majeure ajoutee ensuite :
- controles fins affiches dans l'interface :
  - `structure`
  - `calendrier`
  - `budget`
  - `conditions`
  - `capacite`
- detail de comparaison plus fin base sur :
  - type de structure
  - dates et planning
  - montants et mots-cles budgetaires
  - conditions / pieces dossier
  - qualite du profil client et des elements projet
- integration d'un pont global de contexte documentaire et de fiabilite
- reorganisation UX de la page upload :
  - `Diagnostic prioritaire`
  - `Extractions detaillees`
  - `Ponts et completions`
- objectif de cette reorganisation :
  - garder la pertinence gagnee
  - reduire la friction visuelle et la densite de lecture

Limite :
- logique encore heuristique
- pas encore un vrai matching critere par critere conforme au schema cible `analyses` / `resultats_criteres`

## Corrections importantes deja faites

### Deploiement Streamlit

Problemes rencontres :
- confusion entre `requirements.txt` et `streamlit_app.py`
- boucle de deploiement Streamlit Cloud
- structure `app/` correcte mais trop fragile pour les premiers tests cloud

Corrections :
- retour a un `streamlit_app.py` autonome et stable
- verification des dependances dans `requirements.txt`

### PDF

Probleme :
- certains PDF faisaient planter l'app (`PdfReadError`, `Root object`)

Correction :
- ajout d'une lecture defensive
- si un PDF est illisible, l'app affiche une erreur locale mais ne plante plus tout le bloc

### Excel / Markdown

Probleme :
- `pandas.to_markdown()` necessitait `tabulate`
- plantage sur Streamlit Cloud

Correction :
- remplacement par une generation manuelle du tableau markdown

### Multi-fichiers

Probleme :
- un nouveau fichier remplaçait l'ancien dans un bloc

Correction :
- `accept_multiple_files=True`
- traitement fichier par fichier
- recapitulatif multi-documents

### Synthese partielle

Probleme :
- la synthese de bloc reprenait partiellement les informations
- certains fichiers etaient relus depuis des objets upload consommes

Correction :
- relecture des fichiers a partir des `bytes`
- parseurs memoire :
  - texte
  - csv
  - excel
  - pdf
  - docx

### Excel multi-feuilles

Probleme :
- l'interface donnait l'impression qu'une seule feuille etait prise en compte

Correction :
- affichage de toutes les feuilles dans des blocs repliables
- source normalisee du classeur complet

### Feuilles informatives Excel

Probleme :
- certaines feuilles comme `Lisez-moi` polluaient la lecture metier

Correction :
- classification simple :
  - feuilles `informatives`
  - feuilles `metier`
- priorite donnee aux feuilles metier

## Ce qui est encore mal fait ou incomplet

### Globalement

- le prototype reste un `WF1 enrichi + pre-WF2/WF3`, pas encore le produit final
- les sorties ne sont pas encore celles du vrai Subly complet

### WF2

- `WF2a` a ete remonte d'un cran :
  - criteres structures
  - `source_document`
  - `source_texte`
  - `niveau_confiance`
  - `necessite_validation`
  - contrat de donnees plus stable pour un futur LLM
- `WF2b` sort maintenant :
  - `profil_client`
  - `donnees_projet`
  - champs structures avec valeur, source, confiance et validation
- limite restante :
  - l'extraction reste encore heuristique
  - les categories / domaines ne sont pas encore verifies par un vrai moteur semantique ou LLM

### LLM direct Python

Avancee majeure ajoutee ensuite :
- ajout de `app/services/llm_client.py`
- ajout de `app/services/wf2_llm.py`
- choix confirme : pas de `n8n` pour l'instant
- strategie retenue :
  - appels directs Python vers Claude API
  - cible prioritaire : `WF2a`
  - heuristiques locales gardees en secours
  - pas de blocage applicatif si la cle API est absente

Fonctionnalites deja en place :
- lecture de configuration via variables d'environnement :
  - `ANTHROPIC_API_KEY`
  - `ANTHROPIC_MODEL`
  - `ANTHROPIC_MAX_TOKENS`
  - `ANTHROPIC_TEMPERATURE`
- creation defensive du client LLM
- page `LLM` dans l'interface
- test de preparation `WF2a` sur les documents du smoke-test
- echec propre si la configuration n'est pas encore presente

Tests deja verifies :
- `python3 -m py_compile` OK apres ajout de la couche LLM
- import reel de `streamlit_app.py` OK dans `.venv`
- `request_wf2a_llm_payload()` retourne proprement :
  - `ok = False`
  - `error = client_llm_non_configure`
  tant que la cle API n'est pas configuree

Point de vigilance :
- le prompt `WF2a` est pret, mais aucun appel reel ne doit etre considere comme valide tant qu'une vraie cle et des tests sur cas reels n'ont pas ete faits

### Pont

- le pont local reste utile
- il sert maintenant aussi de surcouche de correction manuelle pour reinjecter les donnees dans `WF2`
- la completion manuelle peut creer ou completer certains criteres et champs structurants
- vigilance :
  - utile pour debloquer un dossier
  - ne doit pas devenir le coeur du raisonnement final

### WF3

- `WF3` local est maintenant structure critere par critere dans `app/services/wf3.py`
- sorties disponibles :
  - `score_global`
  - `statut_eligibilite`
  - `niveau_confiance`
  - `sous_scores`
  - `resultats_criteres`
  - `counts`
  - `resume_executif`
- chaque ligne de resultat contient :
  - critere
  - bloc cible
  - statut
  - score partiel
  - justification
  - ecart
  - action requise
  - donnee utilisee
  - source dossier
- limite restante :
  - la logique de comparaison reste encore locale / heuristique
  - elle est preparee pour un futur LLM, mais ne le remplace pas encore

### WF4

- `WF4` local est maintenant implemente dans `app/services/wf4.py`
- sorties disponibles :
  - `rapport_structured`
  - `rapport_markdown`
  - `champs_preremplissage`
  - `suggestions`
- l'interface Streamlit expose maintenant un onglet `WF4 sorties`
- limite restante :
  - suggestions encore locales et simples
  - rapport utile pour prototype, pas encore equivalent a un rendu final client

## Decisions importantes a conserver

- garder les 3 blocs `dossier / client / projet`
- rester simple et lisible dans l'interface
- ne pas surconstruire trop vite
- faire des sorties de plus en plus structurees avant d'ajouter une IA complexe
- rester aligne avec `contexte/# CLAUDE.md`
- accepter d'ajouter de la logique seulement si elle augmente clairement la pertinence metier
- surveiller en permanence les points de friction inutiles dans l'UX et dans la lecture des resultats
- preferer une complexite masquee ou repliable plutot qu'un affichage dense par defaut
- distinguer :
  - friction utile = aide a mieux qualifier le dossier
  - friction inutile = ajoute des champs, couches ou sections sans gain clair pour la decision

## Point de vigilance UX / pertinence

Evaluation a conserver :
- ajout recent du pont global et des controles fins :
  - gain de pertinence estime : `8/10`
  - friction ajoutee estimee : `4/10`

Conclusion de travail :
- le bilan est positif tant que la complexite reste organisee
- ne pas retirer les ponts utiles, mais mieux hierarchiser leur affichage
- si une nouvelle brique augmente surtout la charge de lecture sans ameliorer une vraie decision, la reconsiderer
- pour la suite, optimiser d'abord la clarte de l'interface avant d'ajouter trop de nouvelles couches

## Prochaine etape recommandee

La prochaine vraie etape logique est :

### Etape suivante recommandee

Stabiliser et fiabiliser le pipeline `WF2 -> WF3 -> WF4` :

- tester avec plusieurs vrais dossiers
- corriger les cas limites de comparaison
- continuer a sortir de la logique de `streamlit_app.py` vers `app/services`
- activer ensuite une vraie extraction `WF2a` assistee par LLM sur quelques dossiers tests

## Derniere avancee majeure

- branchement complet du pipeline local :
  - `WF2 structure`
  - `pont complete`
  - `WF3 critere par critere`
  - `WF4 sorties`
- ajout d'un onglet `WF4 sorties` dans l'interface
- reinjection de la completion manuelle dans les structures `WF2`
- correction de compatibilite Python locale :
  - ajout de `from __future__ import annotations`
  - imports reellement testes dans `.venv`
- verification actuelle :
  - `python3 -m py_compile` OK
  - imports reels OK dans `.venv`
  - smoke-test `WF3/WF4` OK dans `.venv`

## Derniere avancee majeure

- integration de la base documentaire locale :
  - catalogue scanne sur le dossier `base de donnees appels d'offres et appels a projets vides`
  - `197` documents catalogues
  - snapshots ecrits dans `data/reference/document_catalog.csv` et `.json`
- ajout d'un smoke-test reel sur des documents du workspace :
  - script `scripts/smoke_test_real_documents.py`
  - sortie ecrite dans `data/samples/smoke_test_results.json`
  - resultat actuel :
    - statut `a confirmer`
    - score `68/100`
- preparation Supabase locale :
  - `supabase/config.toml`
  - migration `supabase/migrations/20260424_000001_subly_v3_init.sql`
  - migration `supabase/migrations/20260425_security_baseline.sql`
  - `supabase/seed.sql`
  - `.env.example`
  - pont Python `app/services/supabase_bridge.py`
  - `.env` local pre-rempli avec :
    - `SUPABASE_URL=https://iqkggmbnvcblfsufvqgc.supabase.co`
    - `SUPABASE_PROJECT_REF=iqkggmbnvcblfsufvqgc`
  - chargement automatique du `.env` via `app/services/env_loader.py`
- finition UI :
  - page `Base documentaire`
  - page `Supabase`
  - accueil mis a jour sur l'etat reel du prototype
- coherence contexte :
  - note ajoutee dans `docs/coherence_contexte.md`

## Avancee majeure suivante

- mise en place de la couche `LLM direct Python`
  - `app/services/llm_client.py`
  - `app/services/wf2_llm.py`
  - page `LLM` dans l'interface
  - dependance `anthropic` ajoutee
  - variables LLM ajoutees dans `.env.example`
- verification actuelle :
  - import reel de l'application OK
  - client LLM non configure -> comportement propre et attendu
  - pas de dependance `n8n` imposee a ce stade

## Derniere avancee majeure

- securite minimale Supabase activee
  - `RLS` active sur :
    - `clients`
    - `dossiers`
    - `documents`
    - `criteres`
    - `financements`
    - `analyses`
    - `resultats_criteres`
    - `rapports`
    - `champs_preremplissage`
    - `suggestions`
    - `journal`
  - bucket `subly-documents` cree en mode prive
  - `create_supabase_client()` prefere maintenant la `service_role_key` cote backend si elle est disponible
- verification reelle :
  - insertion d'un client test via `service_role`
  - lecture du meme client via `anon` => `[]`
  - nettoyage du client test
  - conclusion : l'acces public est bien bloque par `RLS`

## Derniere avancee majeure

- branchement d'une execution pilotee dans `streamlit_app.py`
  - bouton `Executer le pipeline`
  - choix :
    - `Preferer Claude API pour WF2/WF3`
    - `Persister les resultats dans Supabase`
  - resultat garde en memoire Streamlit pour les fichiers en cours
- ajout des services :
  - `app/services/wf2b_llm.py`
  - `app/services/wf3_llm.py`
  - `app/services/pipeline_runtime.py`
  - `app/services/persistence.py`
  - `app/services/bridge_completion.py`
- execution actuelle :
  - `WF2a` peut passer par Claude ou retomber en heuristique
  - `WF2b` peut passer par Claude ou retomber en heuristique
  - `WF3` peut passer par Claude ou retomber en heuristique
  - `WF4` reste derive de `WF3`
- persistance Supabase actuelle :
  - `clients`
  - `dossiers`
  - `documents` + upload Storage dans le bucket prive `subly-documents`
  - `criteres`
  - `analyses`
  - `resultats_criteres`
  - `rapports`
  - `champs_preremplissage`
  - `journal`
- smoke-test reel valide en mode `prefer_llm = False` :
  - `documents_count = 7`
  - `criteres_count = 12`
  - `resultats_count = 12`
  - `preremplissage_count = 9`
  - `suggestions_count = 0`

Points corriges pendant ce branchement :
- noms de fichiers Storage normalises en ASCII pour eviter les erreurs Supabase sur accents
- nettoyage des caracteres `\\x00` avant insertion SQL
- conservation du fallback heuristique si la cle Claude n'est pas configuree ou si la reponse JSON est invalide

## Seance du 2026-04-24

### Audit complet de l'architecture modulaire

- verification que les modules `app/services/` sont reellement importes et utilises par `streamlit_app.py`
- constat : refactoring **bien realise** — `parsers.py`, `metadata.py`, `normalizers.py` sont cables et actifs
- passage de 2 052 a 1 853 lignes dans `streamlit_app.py` grace aux extractions precedentes, sans duplication
- 47 fonctions restent encore dans `streamlit_app.py` (logique metier WF, scoring, UI pages) — migration future possible

### Verification et test des connexions live

Tests reels effectues dans `.venv` depuis la machine locale :

**Supabase Cloud :**
- client cree avec succes via `create_supabase_client()`
- ping reel sur `clients` : OK (0 lignes, tables vides = attendu)
- ping reel sur `dossiers` : OK
- warning SSL `LibreSSL 2.8.3` sur macOS : non bloquant, n'apparait pas sur Linux/Streamlit Cloud

**Anthropic Claude API :**
- modele : `claude-sonnet-4-20250514`
- appel reel : reponse `"OK."` en 2.89s
- tokens : 40 input / 5 output
- statut : operationnel

### Correctif securite

- **probleme identifie** : `SUPABASE_PROJECT_REF` s'affichait en clair dans l'UI Streamlit (`iqkggmbnvcblfsufvqgc`)
- **correction** : `describe_supabase_readiness()` retourne maintenant `"configure"` ou `"non configure"` a la place de la valeur reelle
- fichier corrige : `app/services/supabase_bridge.py` ligne 120
- audit complet : aucune cle hardcodee dans le code, aucun `eval/exec`, pas de `subprocess`, `.env` bien ignore par git

### Mise a jour du `.gitignore`

Ajouts critiques :
- `supabase/.temp/` — contenait `project-ref` et `organization_id` en clair (fichier `linked-project.json`)
- `.env.*` sauf `.env.example`
- `base de données appels d'offres et appels à projets vides/` — documents metier internes
- `contexte/` — documents de travail et fichiers sensibles
- patterns Python standards (`*.pyo`, `*.pyd`, `dist/`, `build/`, `.pytest_cache/`)

### Deploiement Streamlit Cloud

- application deployee sur Streamlit Cloud, accessible publiquement
- Python 3.14.4 sur le serveur cloud, `anthropic==0.97.0` et `python-dotenv==1.2.2` installes
- les secrets (cles API) ne sont **pas encore configures** dans Streamlit Cloud — a faire via Settings > Secrets
- une fois les secrets ajoutes, les pages Supabase et LLM afficheront le statut reel

### Mise a jour des pages Supabase et LLM dans l'interface

Pages completement recrites pour refleter l'etat reel du projet :

**Page Supabase :**
- banniere verte si les cles sont presentes, orange sinon
- suppression des mentions "manque Docker / CLI / npx" (non pertinentes en mode Cloud hosted)
- ajout d'un bouton "Tester la connexion Supabase" avec ping reel sur la table `clients`
- description claire de l'infrastructure : Cloud hosted, bucket prive, migrations disponibles

**Page LLM :**
- banniere verte si `ANTHROPIC_API_KEY` configuree, orange sinon
- ajout d'un bouton "Tester l'appel Claude API" avec appel reel et affichage tokens
- description claire de la strategie : appels directs Python, fallback heuristique, usage prevu par WF

## Point de vigilance actuel

**Connexions :**
- Supabase Cloud : operationnel localement — a valider sur Streamlit Cloud apres ajout des secrets
- Claude API : operationnelle localement — a valider sur Streamlit Cloud apres ajout des secrets
- Docker / CLI Supabase : non necessaires en mode Cloud hosted — plus un verrou

**IA / LLM :**
- les WF2a, WF2b, WF3 utilisent encore les heuristiques locales
- le branchement LLM reel est pret mais non active par defaut
- prochaine etape : valider les sorties WF2a/WF2b/WF3 en mode Claude reel sur plusieurs dossiers

**Securite :**
- `.gitignore` complet et a jour
- pas de secrets dans le code
- prochain sujet : policies RLS fines par `owner_id` (actuellement en mode `service_role` uniquement)

**Produit :**
- l'interface est deployee et fonctionnelle sans cles (fallback heuristique)
- afficher clairement quand les resultats viennent de Claude vs heuristique locale : non encore fait
- branchement complet pipeline vers Supabase Cloud : non encore teste depuis Streamlit Cloud

## Seance du 2026-04-24 (suite)

### Refactoring Option C — migration complete de streamlit_app.py

Objectif : sortir toute la logique hors de `streamlit_app.py`.

**Nouveau module `app/services/block_analysis.py` (1 084 lignes) :**
- zéro `st.*` — fonctions pures testables en isolation
- contient : labels, helpers pont, parsing documents, scoring blocs, WF3 local, bridge global
- fonctions cles extraites :
  - `summarize_criterion_match_label`, `summarize_readiness_label`, `summarize_prescore_label`, `summarize_risk_label`, `summarize_control_label`
  - `split_bridge_items`, `contains_any_keyword`, `apply_manual_completion`, `is_missing_bridge_value`
  - `choose_priority_value`, `format_loaded_documents_label`, `infer_block_document_context`
  - `get_dynamic_field_label`, `build_manual_fields_for_section`
  - `aggregate_block_text`, `collect_block_insights`, `build_block_normalized_text`, `build_upload_summary`, `build_files_signature`
  - `assess_block_completeness`, `evaluate_block_criteria`, `build_block_recommendations`, `compute_global_prescore`
  - `extract_wf2a_dossier_criteria`, `extract_wf2b_client_profile`, `extract_wf2b_project_data`, `build_comparable_bridge`
  - `build_global_context_bridge`, `build_global_cross_block_summary`
  - `compute_wf3_local` (version heuristique legacy conservee)

**Nouveau module `app/ui/pages.py` (1 302 lignes) — remplace le stub v0 :**
- contient toutes les fonctions `render_*` et `process_*`
- importe depuis `block_analysis` et tous les services
- fonctions cles :
  - `render_home`, `render_project`, `render_demo_data`, `render_document_catalog_page`, `render_supabase_page`, `render_llm_page`
  - `render_metadata`, `render_normalized_text`
  - `render_wf2a_dossier_section`, `render_wf2b_section`
  - `render_dynamic_manual_field`, `render_manual_completion_widget`, `render_bridge_section`
  - `render_wf3_section`, `render_wf4_section`
  - `render_global_summary`, `render_cross_block_summary`, `render_global_context_bridge`, `render_block_summary`
  - `process_uploaded_file`, `render_upload_block`, `render_upload`
  - `get_active_pipeline_outputs`, `store_pipeline_outputs`

**`streamlit_app.py` reduit a 53 lignes :**
- uniquement : `set_page_config` + `sidebar.radio` + dispatch vers `app/ui/pages`
- zéro logique metier

**Corrections faites en meme temps :**
- `app/services/wf4.py` : ajout de `_dedup()` via `dict.fromkeys()` pour eliminer les doublons dans `points_valides`, `points_a_confirmer`, `points_bloquants`, `recommandations`
- `app/services/persistence.py` : fix `APIError: duplicate key violates unique constraint "idx_preremplissage_generique"` — pattern select-then-update-or-insert pour les champs `est_generique = True` (Structure/Contact)
- `streamlit_app.py` : suppression du shadowing silencieux de `merge_completed_bridge_into_wf2` (108 lignes de code duplique supprimees)

**Verification :**
- `python3 -m py_compile` : OK sur les 3 fichiers
- compilations sans erreur : `block_analysis.py`, `pages.py`, `streamlit_app.py`

**Note design :**
- `docs/subly_ui_design.png` + `docs/subly_design_philosophy.md` : design de reference cree (Void Signal)
- le CSS custom dans Streamlit n'a pas encore ete implemente — etape future separee

## Etat reel du pipeline a ce stade

Le pipeline tourne mais reste **heuristique** sur WF2a/WF2b/WF3 par defaut.
Concretement, sur des documents charges par l'utilisateur :
- WF2a extrait des criteres par patterns textuels, pas par comprehension semantique
- WF2b detecte le profil client par regex, pas par LLM
- WF3 produit un score base sur la presence/absence de valeurs dans le pont
- WF4 genere un rapport a partir du WF3, mais reste trop generique

**La cle Claude API est configuree en local** et les modules LLM sont prets (`wf2_llm.py`, `wf2b_llm.py`, `wf3_llm.py`).
L'activation LLM reelle est la prochaine priorite metier.

## Evolution LLM multi-provider

Le projet ne depend plus uniquement d'Anthropic :
- `app/services/llm_client.py` supporte maintenant `anthropic` et `google`
- le provider actif est pilote par `LLM_PROVIDER`
- si `LLM_PROVIDER` est absent mais qu'une `GOOGLE_API_KEY` existe seule, Google peut devenir le provider par defaut
- `GOOGLE_MODEL` permet de viser `gemini-2.5-flash` par defaut
- si un modele Gemma est expose par le compte Google, il peut etre utilise via la meme variable `GOOGLE_MODEL`

**Point de vigilance :**
- l'integration Google est prete cote code et dependance (`google-genai`)
- elle a ete compilee et importee sans erreur
- le test API reel Google reste a faire des qu'une `GOOGLE_API_KEY` sera ajoutee dans `.env` ou dans les secrets Streamlit

## Evolution Mistral

Le projet supporte maintenant aussi `mistral` comme provider LLM :
- cle : `MISTRAL_API_KEY`
- variable de selection : `LLM_PROVIDER="mistral"`
- modele par defaut retenu : `mistral-small-2603` (Mistral Small 4)

Pourquoi ce choix :
- `Mistral Small 4` est documente comme modele courant sur la doc officielle Mistral
- `Ministral 8B` reste techniquement selectable via `MISTRAL_MODEL="ministral-8b-2410"`
- mais il est documente comme deprecie, donc il ne doit pas etre le choix par defaut

Etat de validation :
- dependance `mistralai` installee
- compilation Python OK
- instanciation du client Mistral OK
- appel API reel a faire quand une vraie `MISTRAL_API_KEY` sera ajoutee

## Fichiers importants a relire si besoin

- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/streamlit_app.py` — 53 lignes, routeur pur
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/ui/pages.py` — tout l'UI Streamlit
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/services/block_analysis.py` — logique pure, sans st.*
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/services/wf2_llm.py` — WF2a via Claude
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/services/wf2b_llm.py` — WF2b via Claude
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/services/wf3_llm.py` — WF3 via Claude
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/services/pipeline_runtime.py` — orchestrateur
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/services/persistence.py` — Supabase
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/requirements.txt`
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/services/supabase_bridge.py`
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/app/services/llm_client.py`
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/.env.example`
- `/Users/alexandrepaviel/Desktop/OF/application AAP ingénia/contexte/# CLAUDE.md`
