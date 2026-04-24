from __future__ import annotations

import os
from pathlib import Path


def load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    root_dir = Path(__file__).resolve().parents[2]
    env_file = root_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)


def get_env_value(key: str, default: str = "") -> str:
    try:
        import streamlit as st

        if key in st.secrets:
            value = st.secrets[key]
            return str(value) if value is not None else default
    except Exception:
        pass

    return os.getenv(key, default)
