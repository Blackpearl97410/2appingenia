from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.document_catalog import scan_document_catalog


OUTPUT_DIR = ROOT_DIR / "data" / "reference"
CSV_PATH = OUTPUT_DIR / "document_catalog.csv"
JSON_PATH = OUTPUT_DIR / "document_catalog.json"


def main() -> None:
    dataframe = scan_document_catalog()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(CSV_PATH, index=False)
    JSON_PATH.write_text(
        json.dumps(dataframe.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Catalogue CSV écrit dans {CSV_PATH}")
    print(f"Catalogue JSON écrit dans {JSON_PATH}")
    print(f"Documents catalogués : {len(dataframe)}")


if __name__ == "__main__":
    main()
