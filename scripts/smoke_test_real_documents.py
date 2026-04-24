from __future__ import annotations

import json
from pathlib import Path
import sys
import warnings

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.document_catalog import build_smoke_test_case
from app.services.wf2 import build_bridge_from_wf2, extract_wf2a_structured, extract_wf2b_structured
from app.services.wf3 import build_wf3_analysis
from app.services.wf4 import build_wf4_outputs


OUTPUT_PATH = ROOT_DIR / "data" / "samples" / "smoke_test_results.json"


def main() -> None:
    warnings.filterwarnings(
        "ignore",
        message="Data Validation extension is not supported and will be removed",
    )
    case = build_smoke_test_case()
    wf2a = extract_wf2a_structured(case["dossier"])
    wf2b = extract_wf2b_structured(case["client"], case["projet"])
    bridge = build_bridge_from_wf2(wf2a, wf2b)
    wf3 = build_wf3_analysis(wf2a, wf2b)
    wf4 = build_wf4_outputs(wf2b, wf3)

    payload = {
        "documents": {
            "dossier": [item.name for item in case["dossier"]],
            "client": [item.name for item in case["client"]],
            "projet": [item.name for item in case["projet"]],
        },
        "wf2a": {
            "nb_criteres": len(wf2a.get("criteres", [])),
            "metadata": wf2a.get("metadata", {}),
        },
        "wf2b": {
            "profil_client": wf2b.get("profil_client", {}),
            "donnees_projet": wf2b.get("donnees_projet", {}),
        },
        "bridge": bridge,
        "wf3": {
            "statut_eligibilite": wf3.get("statut_eligibilite"),
            "score_global": wf3.get("score_global"),
            "niveau_confiance": wf3.get("niveau_confiance"),
            "counts": wf3.get("counts"),
            "resume_executif": wf3.get("resume_executif"),
        },
        "wf4": {
            "rapport_structured": wf4.get("rapport_structured", {}),
            "prefill_count": len(wf4.get("champs_preremplissage", [])),
            "suggestions_count": len(wf4.get("suggestions", [])),
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Smoke test écrit dans {OUTPUT_PATH}")
    print(json.dumps(payload["wf3"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
