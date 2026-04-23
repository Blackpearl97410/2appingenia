import streamlit as st

from app.services.data_loader import load_swot_data


def render_home() -> None:
    st.title("AAP Ingenia")
    st.caption("Prototype de back-office pour analyser des dossiers de financement public")

    col1, col2, col3 = st.columns(3)
    col1.metric("Etat du projet", "Cadrage en place")
    col2.metric("Interface", "Prototype v0")
    col3.metric("Base documentaire", "Disponible")

    st.markdown(
        """
        Cette premiere version sert a poser une base claire :

        - une interface simple ;
        - une lecture rapide du projet ;
        - un point d'entree pour les prochaines integrations.
        """
    )

    st.subheader("MVP vise")
    st.write(
        """
        Le MVP doit permettre d'ingerer un dossier, d'extraire des criteres,
        de comparer un profil client, puis de produire un score, un rapport,
        un pre-remplissage et des suggestions alternatives.
        """
    )


def render_project_frame() -> None:
    st.subheader("Cadre du projet")

    left, right = st.columns(2)

    with left:
        st.markdown("### Ce qui est deja clair")
        st.markdown(
            """
            - Le projet est pense comme un outil interne avant d'etre un SaaS.
            - La stack cible est legere et adaptee a un solo founder.
            - La logique par workflows est deja bien decoupee.
            - Le schema de donnees a deja ete travaille en profondeur.
            """
        )

    with right:
        st.markdown("### Ce qu'on ne fait pas encore")
        st.markdown(
            """
            - Pas de connexion reelle a Supabase
            - Pas d'orchestration n8n en production
            - Pas d'appel LLM dans cette version
            - Pas de traitement automatique des documents
            """
        )


def render_next_steps() -> None:
    st.subheader("Feuille de route simple")
    st.markdown(
        """
        1. Rendre le prototype lisible et presentable
        2. Ajouter un premier formulaire d'upload
        3. Structurer les futurs modules Python
        4. Connecter ensuite la base et les workflows
        """
    )


def render_swot() -> None:
    st.subheader("Exemple de donnees chargees depuis `data/samples/`")
    df = load_swot_data()

    if df.empty:
        st.info("Aucune donnee de demonstration n'a ete trouvee.")
        return

    st.dataframe(df, use_container_width=True)

    first_row = df.iloc[0]
    st.markdown("### Resume du premier enregistrement")
    st.write(first_row.get("resume_executif", "Resume indisponible."))
