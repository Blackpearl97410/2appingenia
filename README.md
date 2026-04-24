# AAP Ingenia

AAP Ingenia est un prototype de back-office pour analyser des appels a projets et appels d'offres, a partir d'une base documentaire et d'un futur pipeline d'IA documentaire.

Le projet est en phase de structuration. Le dossier `contexte/` contient les notes de cadrage, les schemas de donnees et les specifications produit deja prepares. Le dossier `base de donnees appels d'offres et appels a projets vides/` contient des documents de travail et de test, laisses de cote pour l'instant dans le developpement applicatif.

## Objectif du prototype

Le prototype actuel sert a :

- centraliser la vision du projet ;
- tester localement les workflows `WF1` a `WF4` ;
- integrer une base documentaire locale exploitable ;
- preparer `Supabase` et les futurs workflows IA ;
- amorcer des appels LLM directs depuis Python, sans dependre de `n8n` pour l'instant.

## Structure du projet

```text
.
├── README.md
├── requirements.txt
├── streamlit_app.py
├── app/
│   ├── main.py
│   ├── ui/
│   ├── services/
│   ├── models/
│   └── utils/
├── data/
│   ├── reference/
│   └── samples/
├── docs/
├── supabase/
├── contexte/
│   ├── # CLAUDE.md
│   ├── subly_schema_v3.sql.md
│   ├── subly_point_global_projet_v3.html.html
│   └── ...
└── base de donnees appels d'offres et appels a projets vides/
```

## Lancer le projet

1. Creer un environnement virtuel :

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Installer les dependances :

```bash
pip install -r requirements.txt
```

3. Lancer l'application :

```bash
streamlit run streamlit_app.py
```

## Etat actuel

- vision produit : definie ;
- architecture cible : definie ;
- schema de donnees : avance ;
- application web : prototype metier local ;
- workflows `WF1` a `WF4` : disponibles localement ;
- structure Python modulaire : amorcee ;
- base documentaire : cataloguée localement ;
- Supabase : prepare mais pas encore lance localement ;
- securite minimale Supabase : activee (`RLS` sur les tables publiques, bucket documents prive) ;
- LLM : ossature directe Python prete, cle API encore absente.

## Prochaines etapes conseillees

1. Stabiliser les cas reels et les comparaisons critere par critere.
2. Brancher la stack locale `Supabase` quand le CLI et Docker seront disponibles.
3. Activer un premier appel LLM reel dans `WF2a` via `app/services/llm_client.py`.
4. Continuer a sortir la logique metier hors de `streamlit_app.py`.
