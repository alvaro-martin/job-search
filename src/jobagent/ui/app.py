"""Streamlit entry point.

Run from the project root:
    streamlit run src/jobagent/ui/app.py
"""

import sys
from pathlib import Path

# The project uses flat imports (from schemas..., import profile_parser), so the folder above
# this one must be on the import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

import jobs_view  # noqa: E402
import profile_view  # noqa: E402
import run_view  # noqa: E402
from logs import setup_logging  # noqa: E402

setup_logging()  # console and data/logs/jobagent.log; does nothing if already set up
st.set_page_config(page_title="Job Agent", layout="wide")
st.title("Job Agent")

tab_profile, tab_run, tab_jobs = st.tabs(["Profile", "Run", "Jobs"])

with tab_profile:
    profile_view.render()
with tab_run:
    run_view.render()
with tab_jobs:
    jobs_view.render()
