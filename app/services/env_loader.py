from __future__ import annotations

from pathlib import Path


def load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    root_dir = Path(__file__).resolve().parents[2]
    env_file = root_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
