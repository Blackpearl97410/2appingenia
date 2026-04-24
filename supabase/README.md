# Supabase local

Ce dossier prepare la future base locale du projet `AAP Ingenia / Subly`.

Contenu :

- `migrations/` : schema SQL versionne
- `seed.sql` : jeu de donnees minimal pour un premier cas de test
- `config.toml` : configuration locale Supabase CLI

Etat actuel :

- le schema V3 du dossier `contexte/` a ete converti en migration locale
- un seed de demonstration a ete prepare
- le pont Python vers Supabase est pret via `app/services/supabase_bridge.py`
- la stack locale n'a pas ete demarree ici car l'environnement ne contient pas encore `npx` ni Docker

Sequence cible quand l'environnement sera complet :

```bash
npx supabase init
npx supabase start
npx supabase db reset
```

Variables a configurer dans `.env` :

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_PROJECT_REF`
- `SUPABASE_STORAGE_BUCKET`
