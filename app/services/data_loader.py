from pathlib import Path

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[2]
SAMPLE_DIR = ROOT_DIR / "data" / "samples"
SWOT_CSV = SAMPLE_DIR / "converted_data.csv"


@st.cache_data
def load_swot_data() -> pd.DataFrame:
    if not SWOT_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(SWOT_CSV)
