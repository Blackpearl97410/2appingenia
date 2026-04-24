from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
BASE_DOCUMENTS_DIR = ROOT_DIR / "base de données appels d'offres et appels à projets vides"
CONTEXT_DIR = ROOT_DIR / "contexte"


@dataclass
class LocalWorkspaceFile:
    path: Path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size(self) -> int:
        return self.path.stat().st_size

    def getvalue(self) -> bytes:
        return self.path.read_bytes()


def infer_document_family(path: Path) -> str:
    lowered = str(path).lower()
    name = path.name.lower()

    if "dce" in lowered:
        return "marche_public"
    if "fom" in name or "presence digitale" in name or "diffusions alter" in name:
        return "fonds_outre_mer"
    if "cadre" in name:
        return "cadre_intervention"
    if "reglement" in name or "rc " in name or name.startswith("rc"):
        return "reglement_consultation"
    if "formulaire" in name or "candidature" in name:
        return "formulaire"
    if "charte" in name:
        return "charte"
    return "autre"


def infer_workflow_role(path: Path) -> str:
    lowered = str(path).lower()
    name = path.name.lower()

    if any(keyword in lowered for keyword in ["dce/", "dce v2/", "dce_15 07 25/"]) or any(
        keyword in name for keyword in ["reglement", "rc ", "cadre", "appel-a-candidature", "fonds-de-soutien"]
    ):
        return "dossier"
    if any(keyword in name for keyword in ["plaquette", "charte", "statut", "reference", "référence", "presentation"]):
        return "client"
    if any(keyword in name for keyword in ["formulaire", "budget", "planning", "phono", "volet", "dq", "dqe", "ae"]):
        return "projet"
    return "a_classifier"


def infer_topic(path: Path) -> str:
    name = path.name.lower()

    if any(keyword in name for keyword in ["audio", "audiovisuel", "cinema", "multimedia"]):
        return "audiovisuel"
    if any(keyword in name for keyword in ["musique", "spectacle", "artiste"]):
        return "musique_spectacle"
    if any(keyword in name for keyword in ["formation", "formateur", "afpjei", "pre-poc"]):
        return "formation"
    if any(keyword in name for keyword in ["digitale", "numerique", "web", "graphiste", "photo"]):
        return "numerique_communication"
    if any(keyword in name for keyword in ["agricole", "mara", "fruit", "paysagiste"]):
        return "agricole"
    return "generaliste"


def scan_document_catalog() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not BASE_DOCUMENTS_DIR.exists():
        return pd.DataFrame()

    for path in sorted(BASE_DOCUMENTS_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(".") or path.name.lower() == "thumbs.db":
            continue

        relative_path = path.relative_to(ROOT_DIR)
        parent = path.parent.relative_to(BASE_DOCUMENTS_DIR)
        suffix = path.suffix.lower() or "inconnu"

        rows.append(
            {
                "nom_fichier": path.name,
                "extension": suffix,
                "taille_octets": path.stat().st_size,
                "dossier_parent": str(parent) if str(parent) != "." else "racine",
                "chemin_relatif": str(relative_path),
                "famille_documentaire": infer_document_family(path),
                "role_workflow_recommande": infer_workflow_role(path),
                "thematique_probable": infer_topic(path),
            }
        )

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return dataframe

    return dataframe.sort_values(
        by=["role_workflow_recommande", "famille_documentaire", "nom_fichier"],
        ascending=[True, True, True],
    ).reset_index(drop=True)


def build_smoke_test_case() -> dict[str, list[LocalWorkspaceFile]]:
    def existing_files(paths: list[Path]) -> list[LocalWorkspaceFile]:
        return [LocalWorkspaceFile(path) for path in paths if path.exists()]

    dossier_paths = [
        BASE_DOCUMENTS_DIR / "FOM Présence digitale 25 volet 1.xlsx",
        BASE_DOCUMENTS_DIR / "region-reunion.fonds-de-soutien-a-l-audiovisuel-au-cinema-et-au-multimedia.pdf",
        BASE_DOCUMENTS_DIR / "cadre_intervention_2025.pdf",
    ]
    client_paths = [
        CONTEXT_DIR / "plaquette_formation_audio.pdf",
        BASE_DOCUMENTS_DIR / "PRE-6.3 V01 Maj 23juillet2024 Charte du formateur externe Doc de diffusion paviel signé.pdf",
    ]
    project_paths = [
        BASE_DOCUMENTS_DIR / "formulaire_de_demande_-pre-poc_v2.docx",
        BASE_DOCUMENTS_DIR / "Phono-Production-phonographique-2026.xlsx",
    ]

    return {
        "dossier": existing_files(dossier_paths),
        "client": existing_files(client_paths),
        "projet": existing_files(project_paths),
    }
