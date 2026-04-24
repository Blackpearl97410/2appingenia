-- ============================================================
-- SECURITY BASELINE V1
-- Active le niveau minimum de securite pour un prototype public :
-- - RLS sur toutes les tables exposees du schema public
-- - aucun acces anon/authenticated par defaut tant que des policies
--   plus fines ne sont pas definies
-- - le backend Streamlit continue a utiliser la service role key
-- ============================================================

ALTER TABLE public.clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dossiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.criteres ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.financements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resultats_criteres ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rapports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.champs_preremplissage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.journal ENABLE ROW LEVEL SECURITY;
