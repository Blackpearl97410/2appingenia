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

## Branchement sur un projet Supabase distant

Pour ce projet, la separation utile est la suivante :

- l'application Python utilise :
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY` si besoin d'ecritures privilegiees
  - `SUPABASE_PROJECT_REF`
- le CLI Supabase utilise :
  - `supabase login`
  - `supabase link --project-ref ...`
  - le mot de passe de la base Postgres distante si on veut pousser / tirer le schema

L'application Python n'utilise pas directement le mot de passe Postgres.

### Valeurs deja connues

```text
SUPABASE_URL=https://iqkggmbnvcblfsufvqgc.supabase.co
SUPABASE_PROJECT_REF=iqkggmbnvcblfsufvqgc
```

### Ce qu'il manque encore

- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- le mot de passe Postgres du projet

### Sequence recommandee

1. Installer le CLI Supabase
2. Se connecter :

```bash
supabase login
```

3. Lier le repo local au projet distant :

```bash
supabase link --project-ref iqkggmbnvcblfsufvqgc
```

4. Completer ensuite le fichier `.env` avec les cles API du projet

5. Optionnel ensuite seulement :

```bash
supabase db push
```

ou

```bash
supabase db pull
```

suivant que l'on veut pousser la migration locale vers le distant ou recuperer l'etat du distant.
