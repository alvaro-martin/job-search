"""Run tab: check the setup, run the pipeline with live progress, show the result."""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import streamlit as st

from graph import NODES, load_initial_state
from run_history import RunTrigger
from runner import SETUP_STEP, PipelineError, run_pipeline
from settings import ConfigError, load_settings
from setup_check import check_keys

# The graph is a straight line, so these are the steps in order.
NODE_LABELS = {
    "generate_queries": "Generating search queries",
    "search_jobs": "Searching the job boards",
    "deduplicate": "Removing duplicates and jobs already seen",
    "filter_by_title": "Filtering by title",
    "fetch_pages": "Downloading the pages",
    "extract_jobs": "Reading each job posting",
    "filter_jobs": "Applying your dealbreakers",
    "score_jobs": "Scoring the jobs",
    "write_report": "Writing the report",
    "save_jobs": "Saving to the database",
    SETUP_STEP: "Reading the settings and your profile",
}

COUNTER_LABELS = {
    "search_results": "Search results",
    "new_jobs": "New jobs",
    "rejected": "Rejected",
    "matches": "Matches",
    "to_retry": "To retry next run",
}


# ----------------------------- helpers (no Streamlit) ------------------
def describe(node: str, before: dict, after: dict) -> str:
    """One short line on what a step just did, from the state before and after it."""
    newly_rejected = len(after["rejected"]) - len(before["rejected"])
    min_score = after["settings"].score.min_score
    if node == "generate_queries":
        return f"{len(after['queries'])} queries"
    if node == "search_jobs":
        return f"{len(after['hits'])} results"
    if node == "deduplicate":
        return f"{len(after['unique_hits'])} new jobs out of {len(after['hits'])} results"
    if node == "filter_by_title":
        return f"{len(after['candidates'])} kept, {newly_rejected} rejected"
    if node == "fetch_pages":
        return f"{len(after['pages'])} of {len(before['candidates'])} pages downloaded"
    if node == "extract_jobs":
        return f"{len(after['jobs'])} job postings, {newly_rejected} were not postings"
    if node == "filter_jobs":
        return f"{len(after['jobs'])} kept, {newly_rejected} rejected"
    if node == "score_jobs":
        return f"{len(after['scored_jobs'])} matches (score >= {min_score}), {newly_rejected} rejected"
    if node == "write_report":
        return "done"
    return ""


# ----------------------------- screen ----------------------------------
def show_setup(checks: list[dict]) -> None:
    missing = [c for c in checks if c["status"] == "missing"]
    with st.expander("Setup check", expanded=bool(missing)):
        for c in checks:
            mark = {"found": "✓", "missing": "✗", "unknown": "?"}[c["status"]]
            note = {"found": "found", "missing": "MISSING, add it to your .env file",
                    "unknown": "can't be checked here"}[c["status"]]
            st.write(f"{mark} `{c['name']}` ({c['needed_by']}): {note}")
        st.caption("Keys are read from your .env file. They are never shown here.")


def execute(state: dict) -> None:
    steps = list(NODES)  # the steps, in running order
    progress = st.progress(0.0)
    done, seen = 0, set()
    with st.status(f"Running: {NODE_LABELS[steps[0]]}", expanded=True) as status:

        def on_step(node: str, before: dict, after: dict) -> None:
            nonlocal done
            done += 1
            seen.add(node)
            detail = describe(node, before, after)
            status.write(f"✓ {NODE_LABELS.get(node, node)}" + (f": {detail}" if detail else ""))
            progress.progress(min(done / len(steps), 1.0))
            if done < len(steps):
                status.update(label=f"Running: {NODE_LABELS.get(steps[done], '...')}")

        try:
            result = run_pipeline(RunTrigger.UI, state=state, on_step=on_step)
        except PipelineError as e:
            status.update(label="The run failed", state="error")
            st.error(f"The run stopped during \"{NODE_LABELS.get(e.step, e.step)}\": "
                     f"{e.cause}\n\nNothing was saved, so you can fix the problem and run again. "
                     "The run is recorded in Jobs > History.")
            return
        if "save_jobs" not in seen:  # this step changes nothing, so it may not report
            status.write(f"✓ {NODE_LABELS['save_jobs']}")
        status.update(label="Run complete", state="complete", expanded=False)
    progress.progress(1.0)
    st.session_state.last_run = {
        "summary": {COUNTER_LABELS[name]: value for name, value in asdict(result.counters).items()},
        "report_path": result.report_path,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def show_last_run() -> None:
    last = st.session_state.get("last_run")
    if not last:
        return
    st.divider()
    st.subheader(f"Last run ({last['finished_at']})")
    for column, (label, value) in zip(st.columns(len(last["summary"])), last["summary"].items()):
        column.metric(label, value)
    path = Path(last["report_path"])
    if path.exists():
        text = path.read_text(encoding="utf-8")
        st.download_button("Download the report", data=text, file_name=path.name, mime="text/markdown")
        with st.container(border=True):
            st.markdown(text)


def render() -> None:
    st.subheader("Run the agent")
    try:
        settings = load_settings()  # read on every rerun, so edits to the config file apply at once
    except ConfigError as e:
        st.error(f"The settings file has a problem, fix it and reload this page.\n\n{e}")
        return
    checks = check_keys(settings)
    show_setup(checks)

    state, problem = None, None
    try:
        state = load_initial_state(settings)
    except FileNotFoundError:
        problem = "No profile saved yet. Create one in the Profile tab first."
    except ValueError as e:
        problem = f"The saved profile is not valid: {e}"
    if problem:
        st.warning(problem)
    else:
        roles = ", ".join(state["preferences"].target_roles)
        st.write(f"The run will use your saved profile. Target roles: **{roles}**")

    max_pages = settings.fetch.max_pages
    st.info(
        f"A run makes up to {settings.search.max_queries} searches, downloads up to {max_pages} "
        f"pages and makes up to {2 * max_pages + 1} AI calls (1 for the queries, then up to "
        f"{max_pages} to read pages and {max_pages} to score them). "
        "It takes a few minutes."
    )
    st.caption(
        "Don't change anything else on the page while it runs: that stops the run. "
        "If a run stops early nothing is saved, so you can just run it again. "
        "It is listed as interrupted in Jobs > History."
    )

    ready = problem is None and not any(c["status"] == "missing" for c in checks)
    if st.button("Run now", type="primary", disabled=not ready):
        execute(state)
    show_last_run()
