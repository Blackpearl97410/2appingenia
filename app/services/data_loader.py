from pathlib import Path
import json

import pandas as pd
import streamlit as st

from app.services.document_catalog import scan_document_catalog


ROOT_DIR = Path(__file__).resolve().parents[2]
SAMPLE_DIR = ROOT_DIR / "data" / "samples"
SWOT_CSV = SAMPLE_DIR / "converted_data.csv"
SMOKE_TEST_JSON = SAMPLE_DIR / "smoke_test_results.json"


@st.cache_data
def load_swot_data() -> pd.DataFrame:
    if not SWOT_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(SWOT_CSV)


@st.cache_data
def load_document_catalog() -> pd.DataFrame:
    return scan_document_catalog()


@st.cache_data
def load_smoke_test_results() -> dict:
    if not SMOKE_TEST_JSON.exists():
        return {}
    return json.loads(SMOKE_TEST_JSON.read_text(encoding="utf-8"))
