-- ============================================================  
-- SUBLY MVP — Schéma de base de données Supabase (PostgreSQL)  
-- Version : 3.0  
-- Date : 2026-04-05  
-- Auteur : Architecture Alexandre PAVIEL  
-- ============================================================  
-- Changelog V2 → V3 (9 frictions pipeline résolues) :  
--   #16 Pipeline : ordre strict client → dossier → documents (workflow)  
--   #17 Pipeline : exécution séquentielle WF2a → WF2b → WF3 (workflow)  
--   #18 Profil client : écrasement direct, pas d'historique MVP  
--   #19 UX : UPSERT client par nom dans le workflow (pas de schema)  
--   #20 donnees_projet JSONB ajouté dans dossiers  
--   #21 Fusion WF2b + WF2c → pipeline 4 workflows au lieu de 5  
--   #22 CHECK sur rapports.type_rapport  
--   #23 CHECK sur rapports.format_export  
--   #24 CHECK sur champs_preremplissage.source  
--  
-- Historique complet :  
--   V1 → V2 : 15 corrections (frictions #1 à #15)  
--   V2 → V3 : 9 corrections (frictions #16 à #24)  
--   Total : 24 frictions identifiées et résolues  
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================  
-- 1. CLIENTS  
-- ============================================================

CREATE TABLE clients (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identification  
    nom TEXT NOT NULL,  
    siret TEXT,  
    numero_cnm TEXT,  
    forme_juridique TEXT,

    -- Localisation  
    adresse TEXT,  
    code_postal TEXT,  
    ville TEXT,  
    departement TEXT DEFAULT '974',  
    region TEXT DEFAULT 'La Réunion',

    -- Caractéristiques pour le matching  
    -- [FIX #1] Convention multi-valeur : valeurs séparées par virgule  
    -- Matching SQL : WHERE ',' || secteur_activite || ',' LIKE '%,culture,%'  
    secteur_activite TEXT,              -- ex: 'formation,culture,audio'  
    sous_secteur TEXT,                  -- ex: 'musique,audiovisuel'  
    type_structure TEXT,  
    -- [FIX #5] effectif : label TEXT + min/max INTEGER pour filtrage SQL  
    effectif TEXT,                      -- label affichage : '-5', '10-49', '250+'  
    effectif_min INTEGER,              -- ex: 10  
    effectif_max INTEGER,              -- ex: 49  
    date_creation DATE,  
    chiffre_affaires_annuel NUMERIC,

    -- Capacités / certifications  
    certifications TEXT[],  
    competences_cles TEXT[],  
    -- [FIX #12] references_marches : JSONB structuré au lieu de TEXT libre  
    -- Format : [{"titre":"...","financeur":"...","annee":2024,"montant":45000}]  
    references_marches JSONB,

    -- Contact  
    contact_nom TEXT,  
    contact_email TEXT,  
    contact_telephone TEXT,

    -- Métadonnées  
    notes TEXT,  
    tags TEXT[],  
    created_at TIMESTAMPTZ DEFAULT NOW(),  
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Futur multi-tenant  
    owner_id UUID  
);

CREATE INDEX idx_clients_departement ON clients(departement);  
CREATE INDEX idx_clients_secteur ON clients(secteur_activite);  
CREATE INDEX idx_clients_type ON clients(type_structure);

-- ============================================================  
-- 2. DOSSIERS  
-- ============================================================

CREATE TABLE dossiers (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identification  
    titre TEXT NOT NULL,  
    reference TEXT,  
    type_financement TEXT NOT NULL  
        CHECK (type_financement IN (                -- [FIX #10]  
            'marche_public','subvention','aap','ami','autre'  
        )),  
    financeur TEXT,

    -- [FIX #2] Lien direct dossier → client, sans passer par analyses  
    -- Nullable : un dossier peut exister sans client associé au départ  
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,

    -- [FIX #6] Auto-référence pour regrouper les lots d'un marché  
    -- NULL pour les dossiers simples (subventions, AAP non-lotis)  
    dossier_parent_id UUID REFERENCES dossiers(id) ON DELETE SET NULL,

    -- Dates  
    date_publication DATE,  
    date_limite_depot DATE,  
    date_debut_realisation DATE,  
    date_fin_realisation DATE,

    -- Montants  
    montant_max NUMERIC,  
    montant_min NUMERIC,  
    taux_intervention_max NUMERIC,

    -- Périmètre  
    secteurs_concernes TEXT[],  
    territoire TEXT,  
    zone_geographique TEXT,

    -- Statut  
    statut TEXT DEFAULT 'actif'  
        CHECK (statut IN (                          -- [FIX #10]  
            'actif','clos','en_cours','archive'  
        )),

    -- Métadonnées  
    source_url TEXT,  
    notes TEXT,  
    tags TEXT[],

    -- [FIX #20] Données projet extraites par WF2b (fusion client+projet)  
    -- Format : {"description":"...","budget_total":15000,"partenaires":["Mairie","DAC"],  
    --           "planning":"mars-juin 2026","objectifs":["diffusion","formation"]}  
    donnees_projet JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),  
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    owner_id UUID  
);

CREATE INDEX idx_dossiers_statut ON dossiers(statut);  
CREATE INDEX idx_dossiers_type ON dossiers(type_financement);  
CREATE INDEX idx_dossiers_date_limite ON dossiers(date_limite_depot);  
CREATE INDEX idx_dossiers_client ON dossiers(client_id);  
CREATE INDEX idx_dossiers_parent ON dossiers(dossier_parent_id);

-- ============================================================  
-- 3. DOCUMENTS  
-- ============================================================

CREATE TABLE documents (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Rattachement  
    -- [FIX #11] Pas de contrainte CHECK : les deux FK peuvent être NULL  
    -- Un document non rattaché a extraction_statut = 'non_rattache'  
    dossier_id UUID REFERENCES dossiers(id) ON DELETE SET NULL,  
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,

    -- Fichier  
    nom_fichier TEXT NOT NULL,  
    type_fichier TEXT NOT NULL,  
    taille_octets INTEGER,  
    storage_path TEXT NOT NULL,

    -- [FIX #15] Type de document pour le routage workflow  
    -- Détermine quel sous-workflow d'analyse est déclenché (WF2a/WF2b/WF2c)  
    type_document TEXT DEFAULT 'dossier'  
        CHECK (type_document IN ('dossier', 'client', 'projet')),

    -- Traitement  
    -- [FIX #9] est_scanné → est_scan (ASCII, pas d'accent)  
    est_scan BOOLEAN DEFAULT FALSE,

    -- [FIX #3] Texte extrait : résumé en BDD, complet dans Storage  
    texte_resume TEXT,                  -- 500 premiers chars (affichage NocoDB)  
    texte_extrait_path TEXT,            -- chemin Storage : extractions/{id}.txt

    -- [FIX #4] Structure Excel multi-onglets dans Storage  
    -- Chemin vers le JSON structuré : extractions/{id}_structure.json  
    structure_extraite_path TEXT,

    extraction_statut TEXT DEFAULT 'en_attente'  
        CHECK (extraction_statut IN (               -- [FIX #10]  
            'en_attente','en_cours','termine','erreur','non_rattache'  
        )),  
    extraction_date TIMESTAMPTZ,  
    extraction_erreur TEXT,

    -- Métadonnées  
    description TEXT,  
    created_at TIMESTAMPTZ DEFAULT NOW(),

    owner_id UUID  
);

CREATE INDEX idx_documents_dossier ON documents(dossier_id);  
CREATE INDEX idx_documents_client ON documents(client_id);  
CREATE INDEX idx_documents_statut ON documents(extraction_statut);  
CREATE INDEX idx_documents_type_doc ON documents(type_document);

-- ============================================================  
-- 4. CRITERES EXTRAITS  
-- ============================================================

CREATE TABLE criteres (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,

    categorie TEXT NOT NULL  
        CHECK (categorie IN (                       -- [FIX #10]  
            'obligatoire','souhaitable','bloquant','interpretatif'  
        )),  
    domaine TEXT,  
    libelle TEXT NOT NULL,  
    detail TEXT,

    source_document_id UUID REFERENCES documents(id),  
    source_texte TEXT,

    est_piece_exigee BOOLEAN DEFAULT FALSE,  
    est_critere_eliminatoire BOOLEAN DEFAULT FALSE,

    niveau_confiance TEXT DEFAULT 'moyen'  
        CHECK (niveau_confiance IN ('haut','moyen','bas')),  -- [FIX #10]  
    necessite_validation BOOLEAN DEFAULT TRUE,  
    valide_par_humain BOOLEAN DEFAULT FALSE,

    ordre INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),  
    owner_id UUID  
);

CREATE INDEX idx_criteres_dossier ON criteres(dossier_id);  
CREATE INDEX idx_criteres_categorie ON criteres(categorie);

-- ============================================================  
-- 5. ANALYSES  
-- ============================================================

CREATE TABLE analyses (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,  
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Score global  
    score_global INTEGER,  
    statut_eligibilite TEXT  
        CHECK (statut_eligibilite IN (              -- [FIX #10]  
            'eligible','a_confirmer','partiel','non_eligible'  
        )),  
    niveau_confiance TEXT  
        CHECK (niveau_confiance IN ('haut','moyen','bas')),  -- [FIX #10]

    -- Sous-scores par domaine (JSONB pour flexibilité)  
    sous_scores JSONB,

    -- Résumé IA  
    resume_executif TEXT,  
    points_forts TEXT[],  
    points_faibles TEXT[],  
    elements_manquants TEXT[],  
    documents_manquants TEXT[],  
    recommandations TEXT[],

    -- Versioning  
    version INTEGER DEFAULT 1,  
    analyse_precedente_id UUID REFERENCES analyses(id),

    -- Traitement  
    statut_traitement TEXT DEFAULT 'en_attente'  
        CHECK (statut_traitement IN (               -- [FIX #10]  
            'en_attente','en_cours','termine','erreur'  
        )),  
    duree_traitement_ms INTEGER,  
    modele_ia TEXT,  
    prompt_version TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),  
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    owner_id UUID,

    UNIQUE(dossier_id, client_id, version)  
);

CREATE INDEX idx_analyses_dossier ON analyses(dossier_id);  
CREATE INDEX idx_analyses_client ON analyses(client_id);  
CREATE INDEX idx_analyses_statut ON analyses(statut_eligibilite);

-- ============================================================  
-- 6. RESULTATS CRITERES  
-- ============================================================

CREATE TABLE resultats_criteres (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
    analyse_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,  
    critere_id UUID NOT NULL REFERENCES criteres(id) ON DELETE CASCADE,

    statut TEXT NOT NULL  
        CHECK (statut IN (                          -- [FIX #10]  
            'valide','non_valide','partiel','manquant','a_verifier'  
        )),  
    score INTEGER,  
    justification TEXT NOT NULL,

    donnee_client TEXT,  
    ecart TEXT,  
    action_requise TEXT,

    est_preremplissable BOOLEAN DEFAULT FALSE,  
    valeur_preremplissage TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),  
    owner_id UUID,

    UNIQUE(analyse_id, critere_id)  
);

CREATE INDEX idx_resultats_analyse ON resultats_criteres(analyse_id);

-- ============================================================  
-- 7. RAPPORTS  
-- ============================================================

CREATE TABLE rapports (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
    analyse_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,

    type_rapport TEXT DEFAULT 'eligibilite'  
        CHECK (type_rapport IN (                    -- [FIX #22]  
            'eligibilite','preremplissage','comparatif','complet'  
        )),  
    contenu_json JSONB,  
    contenu_markdown TEXT,

    storage_path TEXT,  
    format_export TEXT  
        CHECK (format_export IN (                   -- [FIX #23]  
            'markdown','docx','pdf','json'  
        )),

    version INTEGER DEFAULT 1,

    created_at TIMESTAMPTZ DEFAULT NOW(),  
    owner_id UUID  
);

CREATE INDEX idx_rapports_analyse ON rapports(analyse_id);

-- ============================================================  
-- 8. CHAMPS PREREMPLISSABLES  
-- ============================================================

CREATE TABLE champs_preremplissage (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
    analyse_id UUID REFERENCES analyses(id) ON DELETE CASCADE,  
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,  
    dossier_id UUID REFERENCES dossiers(id) ON DELETE SET NULL,

    categorie TEXT NOT NULL,  
    nom_champ TEXT NOT NULL,  
    valeur TEXT,

    source TEXT  
        CHECK (source IN (                          -- [FIX #24]  
            'profil_client','document','inference_ia',  
            'saisie_manuelle','extraction_projet'  
        )),  
    niveau_confiance TEXT DEFAULT 'moyen'  
        CHECK (niveau_confiance IN ('haut','moyen','bas')),  -- [FIX #10]  
    valide_par_humain BOOLEAN DEFAULT FALSE,

    est_generique BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),  
    updated_at TIMESTAMPTZ DEFAULT NOW(),  
    owner_id UUID  
);

CREATE INDEX idx_preremplissage_client ON champs_preremplissage(client_id);  
CREATE INDEX idx_preremplissage_analyse ON champs_preremplissage(analyse_id);  
CREATE INDEX idx_preremplissage_categorie ON champs_preremplissage(categorie);

-- [FIX #8] Unicité par client+champ pour les données génériques (SIRET, raison sociale...)  
-- Les champs spécifiques à un dossier (est_generique=FALSE) gardent leur cardinalité libre  
CREATE UNIQUE INDEX idx_preremplissage_generique  
    ON champs_preremplissage(client_id, nom_champ)  
    WHERE est_generique = TRUE;

-- ============================================================  
-- 9. FINANCEMENTS (veille aides-entreprises.fr + manuels)  
-- ============================================================

CREATE TABLE financements (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source  
    source TEXT NOT NULL,  
    id_externe TEXT,

    -- Contenu  
    nom TEXT NOT NULL,  
    objet TEXT,  
    operations_eligibles TEXT,  
    conditions TEXT,  
    montant TEXT,  
    beneficiaires TEXT,

    -- Classification  
    type_aide TEXT,  
    niveau TEXT,  
    domaine TEXT,

    -- Territoire  
    couverture_geo TEXT,  
    territoires_ids TEXT,  
    applicable_reunion BOOLEAN DEFAULT FALSE,  
    applicable_dom BOOLEAN DEFAULT FALSE,

    -- Profils éligibles (IDs source)  
    profils_ids TEXT,  
    projets_ids TEXT,

    -- [FIX #7] Critères structurés parsés par Claude lors de la sync  
    -- Permet le pré-filtre SQL au lieu de tout envoyer à Claude  
    -- Format : {"effectif_max":50,"secteurs":["culture"],"types_structures":["association"],...}  
    criteres_structures JSONB,

    -- Dates  
    date_fin DATE,  
    date_validation DATE,

    -- Financeur  
    financeur TEXT,  
    contact_info TEXT,

    -- Liens  
    url_source TEXT,  
    url_formulaire TEXT,

    -- Statut  
    statut TEXT DEFAULT 'actif'  
        CHECK (statut IN ('actif','inactif','clos')),  -- [FIX #10]

    -- Sync  
    derniere_sync TIMESTAMPTZ,  
    hash_contenu TEXT,  
    est_nouveau BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),  
    updated_at TIMESTAMPTZ DEFAULT NOW(),  
    owner_id UUID,

    UNIQUE(source, id_externe)  
);

CREATE INDEX idx_financements_reunion ON financements(applicable_reunion)  
    WHERE applicable_reunion = TRUE;  
CREATE INDEX idx_financements_statut ON financements(statut);  
CREATE INDEX idx_financements_type ON financements(type_aide);  
CREATE INDEX idx_financements_domaine ON financements(domaine);  
CREATE INDEX idx_financements_source ON financements(source);

-- [FIX #14] Index full-text — à activer au niveau 2 si nécessaire :  
-- CREATE INDEX idx_financements_fts ON financements  
--     USING GIN (to_tsvector('french',  
--         coalesce(nom,'') || ' ' || coalesce(objet,'') || ' ' || coalesce(conditions,'')  
--     ));

-- ============================================================  
-- 10. SUGGESTIONS  
-- ============================================================

CREATE TABLE suggestions (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
    analyse_id UUID REFERENCES analyses(id) ON DELETE CASCADE,  
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,  
    financement_id UUID NOT NULL REFERENCES financements(id) ON DELETE CASCADE,

    score_pertinence INTEGER,  
    rang INTEGER,  
    justification TEXT,

    statut TEXT DEFAULT 'proposee'  
        CHECK (statut IN (                          -- [FIX #10]  
            'proposee','consultee','retenue','ecartee'  
        )),

    created_at TIMESTAMPTZ DEFAULT NOW(),  
    owner_id UUID  
);

CREATE INDEX idx_suggestions_client ON suggestions(client_id);  
CREATE INDEX idx_suggestions_analyse ON suggestions(analyse_id);

-- ============================================================  
-- 11. JOURNAL  
-- ============================================================  
-- [FIX #13] Politique de purge : cron n8n mensuel  
-- DELETE FROM journal WHERE created_at < NOW() - INTERVAL '3 months';

CREATE TABLE journal (  
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    type_operation TEXT NOT NULL,  
    dossier_id UUID REFERENCES dossiers(id) ON DELETE SET NULL,  
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,  
    analyse_id UUID REFERENCES analyses(id) ON DELETE SET NULL,

    statut TEXT NOT NULL,  
    message TEXT,  
    details JSONB,

    tokens_input INTEGER,  
    tokens_output INTEGER,  
    cout_estime_euros NUMERIC(6,4),

    created_at TIMESTAMPTZ DEFAULT NOW()  
);

CREATE INDEX idx_journal_type ON journal(type_operation);  
CREATE INDEX idx_journal_date ON journal(created_at DESC);

-- ============================================================  
-- 12. TRIGGERS updated_at  
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()  
RETURNS TRIGGER AS $$  
BEGIN  
    NEW.updated_at = NOW();  
    RETURN NEW;  
END;  
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_clients_updated  
    BEFORE UPDATE ON clients  
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_dossiers_updated  
    BEFORE UPDATE ON dossiers  
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_analyses_updated  
    BEFORE UPDATE ON analyses  
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_preremplissage_updated  
    BEFORE UPDATE ON champs_preremplissage  
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_financements_updated  
    BEFORE UPDATE ON financements  
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================  
-- ESTIMATION STOCKAGE V3 (free tier Supabase : 500 Mo)  
-- ============================================================  
-- BDD (colonnes uniquement, textes dans Storage) :  
--   10 clients × 0.5 Ko             = 5 Ko  
--   15 dossiers/mois × 1.5 Ko       = 22 Ko/mois (inclut donnees_projet JSONB)  
--   50 docs × 0.3 Ko metadata       = 15 Ko/mois (texte complet dans Storage)  
--   500 critères × 0.5 Ko           = 250 Ko  
--   15 analyses × 5 Ko              = 75 Ko/mois  
--   300 résultats × 0.5 Ko          = 150 Ko/mois  
--   2300 financements × 3 Ko        = 6.9 Mo (inclut criteres_structures)  
--   Total mois 1 : ~8 Mo  
--   Total mois 12 : ~15 Mo  
--  
-- Storage (textes extraits + fichiers sources) :  
--   50 docs/mois × 50 Ko texte      = 2.5 Mo/mois  
--   50 docs/mois × 200 Ko fichier   = 10 Mo/mois  
--   Total mois 12 : ~150 Mo  
--   Free tier Storage : 1 Go → tient 6+ ans  
--  
-- Résultat : marge très confortable sur les deux free tiers.  
-- ============================================================

-- ============================================================  
-- PIPELINE V3 — 4 workflows (après fusion WF2b+WF2c)  
-- ============================================================  
-- Formulaire n8n (1 clic)  
--   → WF1 : Ingestion (upload Storage + extraction texte)  
--     → Séquence :  
--       → WF2a : Extraction critères dossier (→ table criteres)  
--       → WF2b : Extraction profil client + données projet (→ UPDATE clients + dossiers.donnees_projet)  
--     → WF3 : Matching + scoring (→ analyses + resultats_criteres)  
--       → WF4 : Rapport + préremplissage + suggestions (→ rapports + champs_preremplissage + suggestions)  
--  
-- WF5 (indépendant) : Sync hebdo aides-entreprises.fr (→ financements)  
--  
-- Budget estimé : ~4-5€ nouveau client, ~3€ client récurrent  
-- Total estimé : ~35-45€/mois pour 10 dossiers  
-- ============================================================
