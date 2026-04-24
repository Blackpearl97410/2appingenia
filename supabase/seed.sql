insert into clients (
  id,
  nom,
  forme_juridique,
  type_structure,
  secteur_activite,
  region,
  notes
)
values (
  '11111111-1111-1111-1111-111111111111',
  'En Studio',
  'association',
  'association',
  'culture,formation,audio',
  'La Réunion',
  'Client de demonstration pour le premier test local.'
)
on conflict (id) do nothing;

insert into dossiers (
  id,
  titre,
  type_financement,
  financeur,
  client_id,
  territoire,
  statut,
  notes,
  donnees_projet
)
values (
  '22222222-2222-2222-2222-222222222222',
  'FOM Présence digitale 25 volet 1',
  'aap',
  'Région Réunion',
  '11111111-1111-1111-1111-111111111111',
  'La Réunion',
  'actif',
  'Dossier de demonstration local pour AAP Ingenia.',
  '{"description":"Presence digitale et valorisation d activites culturelles","budget_total":15000,"planning":"2026","objectifs":["visibilite","structuration"]}'::jsonb
)
on conflict (id) do nothing;

insert into documents (
  id,
  dossier_id,
  client_id,
  nom_fichier,
  type_fichier,
  taille_octets,
  storage_path,
  type_document,
  extraction_statut,
  description
)
values
(
  '33333333-3333-3333-3333-333333333331',
  '22222222-2222-2222-2222-222222222222',
  null,
  'FOM Présence digitale 25 volet 1.xlsx',
  '.xlsx',
  101467,
  'local/base/FOM Présence digitale 25 volet 1.xlsx',
  'dossier',
  'en_attente',
  'Classeur dossier de demonstration'
),
(
  '33333333-3333-3333-3333-333333333332',
  '22222222-2222-2222-2222-222222222222',
  null,
  'region-reunion.fonds-de-soutien-a-l-audiovisuel-au-cinema-et-au-multimedia.pdf',
  '.pdf',
  0,
  'local/base/region-reunion.fonds-de-soutien-a-l-audiovisuel-au-cinema-et-au-multimedia.pdf',
  'dossier',
  'en_attente',
  'Cadre dossier complementaire'
),
(
  '33333333-3333-3333-3333-333333333333',
  null,
  '11111111-1111-1111-1111-111111111111',
  'plaquette_formation_audio.pdf',
  '.pdf',
  0,
  'local/contexte/plaquette_formation_audio.pdf',
  'client',
  'en_attente',
  'Presentation client'
),
(
  '33333333-3333-3333-3333-333333333334',
  '22222222-2222-2222-2222-222222222222',
  null,
  'formulaire_de_demande_-pre-poc_v2.docx',
  '.docx',
  0,
  'local/base/formulaire_de_demande_-pre-poc_v2.docx',
  'projet',
  'en_attente',
  'Formulaire projet'
)
on conflict (id) do nothing;
