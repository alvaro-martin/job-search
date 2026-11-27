"""Jobs tab: browse everything in the database, see the details of a job, read past reports
and see the history of the runs."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import write_report
from job_store import JobStore, StoredJob
from run_history import RunHistory, RunRecord
from schemas.score import JobScore
from text_match import normalize_text


# ----------------------------- helpers (no Streamlit) ------------------
def safe_link(url: str) -> str | None:
    """Only http(s) links are shown as clickable."""
    return url if url.lower().startswith(("http://", "https://")) else None


def job_matches(job: StoredJob, statuses: list[str], min_score: int, query: str) -> bool:
    if job.status not in statuses:
        return False
    if min_score > 0 and (job.score is None or job.score < min_score):
        return False  # jobs rejected before scoring have no score
    if query.strip():
        parts = [job.title, job.reason or ""]
        if job.job:
            parts += [job.job.company or "", job.job.location or "", *job.job.required_stack]
        if normalize_text(query.strip()) not in normalize_text(" ".join(parts)):
            return False
    return True


def to_dataframe(jobs: list[StoredJob]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Score": j.score,
                "Status": j.status,
                "Title": j.title,
                "Company": j.job.company if j.job else None,
                "Work model": j.job.work_model.value if j.job and j.job.work_model else None,
                "Why": j.reason,
                "First seen": j.first_seen,
                "Link": safe_link(j.url),
            }
            for j in jobs
        ]
    ).astype({"Score": "float64"})


def duration_text(started: str, finished: str | None) -> str:
    """'1m 05s' or '42s'; '-' if the run has no end time (still running, or it died)."""
    if not finished:
        return "-"
    seconds = int((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds())
    minutes, seconds = divmod(max(seconds, 0), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"


HISTORY_COUNTERS = ["Results", "New", "Rejected", "Matches", "Retry"]


def history_dataframe(runs: list[RunRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Started": r.started_at,
                "Duration": duration_text(r.started_at, r.finished_at),
                "Status": r.status,
                "Trigger": r.triggered_by,
                "Results": r.search_results,
                "New": r.new_jobs,
                "Rejected": r.rejected,
                "Matches": r.matches,
                "Retry": r.to_retry,
                "Report": Path(r.report_path).name if r.report_path else None,
                "Error": r.error.splitlines()[0] if r.error else None,
            }
            for r in runs
        ]
    ).astype({name: "float64" for name in HISTORY_COUNTERS})


def aspects_table(details: JobScore) -> pd.DataFrame:
    aspects = [("role", details.role), ("stack", details.stack), ("experience", details.experience),
               ("logistics", details.logistics), ("salary", details.salary)]
    return pd.DataFrame(
        [{"Aspect": name, "Score": a.score, "Why": a.reason} for name, a in aspects]
    ).astype({"Score": "float64"})


# ----------------------------- details ---------------------------------
def show_details(j: StoredJob) -> None:
    st.markdown(f"### {j.title}")
    link = safe_link(j.url)
    if link:
        st.link_button("Open the posting", link)
    score = "-" if j.score is None else j.score
    st.write(f"**Status:** {j.status} · **Score:** {score} · **First seen:** {j.first_seen}")
    if j.reason:
        st.write(f"**{'Why it was rejected' if j.status == 'rejected' else 'Why it fits'}:** {j.reason}")

    if j.details:
        st.caption("Score per aspect (empty means the posting didn't give enough information)")
        st.dataframe(aspects_table(j.details), hide_index=True, column_config={
            "Score": st.column_config.NumberColumn(format="%d")})
    if not j.job:
        st.caption("The page was not read for this job, or its saved details are from an older version.")
        return

    job = j.job
    facts = {
        "Company": job.company, "Location": job.location,
        "Work model": job.work_model.value if job.work_model else None,
        "Contract": ", ".join(c.value for c in job.contract_types) or None,
        "Seniority": job.seniority.value if job.seniority else None,
        "Years required": job.min_years_experience, "Salary": job.salary_text,
        "Posted": str(job.posted_date) if job.posted_date else None,
        "Languages": ", ".join(job.languages_required) or None,
        "Required stack": ", ".join(job.required_stack) or None,
        "Nice to have": ", ".join(job.nice_to_have_stack) or None,
    }
    for label, value in facts.items():
        if value is not None:
            st.write(f"**{label}:** {value}")
    if job.summary:
        st.write(f"**Summary:** {job.summary}")
    if job.unverified:
        st.warning("Not stated in the posting: " + ", ".join(job.unverified))
    with st.expander("Everything we extracted (JSON)"):
        st.json(job.model_dump(mode="json"))


# ----------------------------- screens ---------------------------------
def render_jobs() -> None:
    with JobStore() as store:
        jobs = store.all_jobs()
    if not jobs:
        st.info("No jobs yet. Run the agent first (Run tab).")
        return

    present = sorted({j.status for j in jobs})
    c1, c2, c3 = st.columns([2, 1, 2])
    statuses = c1.multiselect(
        "Status", present, default=[s for s in present if s != "rejected"] or present, key="jobs_status"
    )
    min_score = c2.slider("Minimum score", 0, 100, 0, key="jobs_min_score")
    query = c3.text_input("Search (title, company, stack, reason)", key="jobs_query")

    shown = [j for j in jobs if job_matches(j, statuses, min_score, query)]
    st.caption(f"{len(shown)} of {len(jobs)} jobs. Click a row to see its details.")
    if not shown:
        st.info("No job matches these filters.")
        return

    # The table key changes with the filters, so a selection never points at the wrong row.
    table_key = f"jobs_table_{abs(hash((tuple(statuses), min_score, query)))}"
    event = st.dataframe(
        to_dataframe(shown), hide_index=True, key=table_key,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
            "Link": st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )
    rows = event.selection.rows
    if rows and rows[0] < len(shown):
        st.divider()
        show_details(shown[rows[0]])


def render_reports() -> None:
    folder = write_report.REPORTS_DIR
    files = sorted(folder.glob("report_*.md"), reverse=True) if folder.exists() else []
    if not files:
        st.info("No reports yet. They are created each time you run the agent.")
        return
    chosen = st.selectbox(
        "Report", files, key="report_choice",
        format_func=lambda p: p.stem.removeprefix("report_").replace("_", " "),
    )
    text = chosen.read_text(encoding="utf-8")
    st.download_button("Download this report", data=text, file_name=chosen.name, mime="text/markdown")
    with st.container(border=True):
        st.markdown(text)


def show_run_details(run: RunRecord) -> None:
    st.write(f"**Run {run.id}** · {run.status} · started {run.started_at} · "
             f"triggered by {run.triggered_by}")
    if run.error:
        st.error(run.error)
    if run.report_path:
        path = Path(run.report_path)
        if path.exists():
            with st.container(border=True):
                st.markdown(path.read_text(encoding="utf-8"))
        else:
            st.caption(f"The report {path.name} is no longer in the reports folder.")


def render_history() -> None:
    with RunHistory() as history:
        runs = history.recent_runs()
    if not runs:
        st.info("No runs yet. Every run is listed here, whether it was started from the Run tab "
                "or from the command line.")
        return
    st.caption(f"The latest {len(runs)} runs, newest first. Click a row to see the details.")
    counter_format = st.column_config.NumberColumn(format="%d")
    event = st.dataframe(
        history_dataframe(runs), hide_index=True, key="history_table",
        on_select="rerun", selection_mode="single-row",
        column_config={name: counter_format for name in HISTORY_COUNTERS},
    )
    rows = event.selection.rows
    if rows and rows[0] < len(runs):
        st.divider()
        show_run_details(runs[rows[0]])


def render() -> None:
    jobs_tab, reports_tab, history_tab = st.tabs(["Jobs", "Reports", "History"])
    with jobs_tab:
        render_jobs()
    with reports_tab:
        render_reports()
    with history_tab:
        render_history()
