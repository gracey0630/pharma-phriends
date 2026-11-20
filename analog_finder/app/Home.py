"""Analog Finder app, home page: what's waiting for review.

Run from the repo root: streamlit run analog_finder/app/Home.py
Pages: 1 Review (step 12). The finder page is step 14.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # streamlit puts only this folder on the path
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from analog_finder.research import review  # noqa: E402

st.set_page_config(page_title="Analog Finder", layout="wide")
st.title("Launch Analog and Input Tool")
st.write("Helps a forecaster choose and defend a launch forecast's trajectory from comparable past launches. "
         "Label facts the agent reads (line of therapy, dosing, launch date, # competitors) are used only after a "
         "person approves them here.")

path = review.evidence_path(st.session_state.get("evidence_path"))
c = review.counts(review.load(path))
a, b, r = st.columns(3)
a.metric("Waiting for review", c["waiting"])
b.metric("Approved", c["approved"])
r.metric("Rejected", c["rejected"])
st.page_link("pages/1_Review.py", label="Review label reads")
st.caption(f"Evidence file: {path}. The finder page comes in step 14; until then run "
           "`python -m analog_finder.finder --scenario torevia`.")
