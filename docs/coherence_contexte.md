# Coherence avec le dossier contexte

## Etat au 2026-04-24

Cette note compare l'application locale actuelle avec les attendus poses dans `contexte/# CLAUDE.md`.

## Aligne

- logique en 3 blocs `dossier / client / projet`
- sortie `WF1` locale d'ingestion et normalisation documentaire
- sortie `WF2a` structuree avec source, extrait, confiance et validation
- sortie `WF2b` structuree pour `profil_client` et `donnees_projet`
- sortie `WF3` critere par critere avec score, statut, justification et action
- sortie `WF4` locale avec :
  - rapport structure
  - rapport markdown
  - champs de pre-remplissage
  - suggestions alternatives
- preparation d'appels LLM directs depuis Python pour enrichir `WF2a`, sans `n8n` a ce stade
- preparation Supabase locale :
  - migration
  - seed
  - config
  - pont Python
- integration de la base documentaire locale dans un catalogue exploitable
- socle de securite Supabase applique :
  - `RLS` active sur les tables du schema `public`
  - bucket `subly-documents` cree en mode prive

## Partiellement aligne

- le moteur `WF2` reste encore heuristique localement
- `WF3` est critere par critere, mais pas encore alimente par un LLM ni persiste dans la vraie base
- `WF4` fournit les 4 sorties metier, mais en version prototype locale
- la logique n8n sequentielle `WF1 -> WF2a -> WF2b -> WF3 -> WF4` est representee dans l'application, pas encore orchestree en production

## Non encore finalise

- connexion reelle a un projet Supabase distant
- stack locale Supabase demarree via CLI + Docker
- persistence effective des analyses dans `analyses`, `resultats_criteres`, `rapports`, `champs_preremplissage`, `suggestions`
- integration Claude API avec cle active et retours verifies sur cas reels
- test end-to-end complet avec un vrai dossier client totalement renseigne

## Conclusion

L'application est maintenant coherentement alignee avec le `contexte` sur la structure fonctionnelle et les sorties metier attendues.

Le principal ecart restant n'est plus le produit ni l'UX, mais la couche d'execution reelle :

- base Supabase non branchee
- orchestration n8n non retenue pour l'instant
- LLM prepare mais pas encore actif dans la boucle de production
- policies fines `authenticated` / `owner_id` pas encore definies

Autrement dit :

- coherence produit : bonne
- coherence prototype local : bonne
- coherence infra / execution finale : en preparation
