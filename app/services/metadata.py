from pathlib import Path
import re

import pandas as pd


def extract_text_metadata(text: str, filename: str) -> dict[str, str]:
    compact_text = re.sub(r"\s+", " ", text).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    title = lines[0] if lines else Path(filename).stem

    date_match = re.search(
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
        compact_text,
    )
    amount_match = re.search(
        r"\b\d[\d\s.,]{2,}\s?(?:€|euros?)\b",
        compact_text,
        flags=re.IGNORECASE,
    )
    org_match = re.search(
        r"\b(Région|Region|CNM|ADEME|BPI|France Travail|DEETS|Europe|Etat|Minist[eè]re)\b",
        compact_text,
        flags=re.IGNORECASE,
    )

    lower_name = filename.lower()
    if "appel" in lower_name or "aap" in lower_name:
        document_type = "appel a projets"
    elif "formulaire" in lower_name:
        document_type = "formulaire"
    elif "cadre" in lower_name:
        document_type = "cadre d'intervention"
    elif "reglement" in lower_name:
        document_type = "reglement"
    else:
        document_type = "document texte"

    return {
        "Titre probable": title[:120],
        "Type probable": document_type,
        "Date detectee": date_match.group(1) if date_match else "Non detectee",
        "Montant detecte": amount_match.group(0) if amount_match else "Non detecte",
        "Organisme detecte": org_match.group(1) if org_match else "Non detecte",
    }


def extract_table_metadata(dataframe: pd.DataFrame, filename: str) -> dict[str, str]:
    return {
        "Nom du fichier": filename,
        "Type probable": "tableau",
        "Nombre de lignes": str(len(dataframe)),
        "Nombre de colonnes": str(len(dataframe.columns)),
        "Colonnes detectees": ", ".join(str(col) for col in list(dataframe.columns)[:6]) or "Aucune",
    }


def normalize_detected_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def add_detected_value(store: dict[str, set[str]], key: str, value: str, source_name: str) -> None:
    normalized = normalize_detected_value(value)
    if not normalized or normalized in {"Non detectee", "Non detecte", "Aucun", "Aucune"}:
        return
    store.setdefault(normalized, set()).add(source_name)


def format_detected_values(store: dict[str, set[str]]) -> str:
    if not store:
        return "Aucun"
    items = sorted(
        store.items(),
        key=lambda item: (-len(item[1]), item[0].lower()),
    )
    return " | ".join(
        f"{value} ({len(sources)} doc)" if len(sources) == 1 else f"{value} ({len(sources)} docs)"
        for value, sources in items[:8]
    )


def extract_keywords_from_text(text: str) -> list[str]:
    words = re.findall(r"\b[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ-]{3,}\b", text.lower())
    filtered = []
    seen = set()
    stop_words = {
        "dans", "avec", "pour", "cette", "document", "documents", "projet",
        "dossier", "client", "bloc", "fichier", "charge", "titre", "type",
        "date", "montant", "organisme", "texte", "tableau", "feuille",
    }
    for word in words:
        if len(word) <= 4 or word in stop_words or word in seen:
            continue
        seen.add(word)
        filtered.append(word)
        if len(filtered) >= 20:
            break
    return filtered
