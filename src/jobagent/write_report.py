"""Ninth node: write the matches of this run to a markdown report, best score first.

It runs BEFORE save_jobs on purpose: if writing the report fails, nothing is saved, so
the same jobs show up again in the next run instead of being lost.
"""

from datetime import datetime
from pathlib import Path

from schemas.score import ScoredJob
from score_jobs import MIN_SCORE
from state import State

REPORTS_DIR = Path(__file__).parent / "data" / "reports"


def md_escape(text: str) -> str:
    """Keep titles from breaking markdown links and tables."""
    return text.replace("[", "\\[").replace("]", "\\]").replace("|", "\\|").replace("\n", " ")


def render_job(rank: int, scored: ScoredJob) -> str:
    job, d = scored.job, scored.details
    title = md_escape(job.title or "(no title)")
    company = f" - {md_escape(job.company)}" if job.company else ""

    facts = [
        job.work_model.value if job.work_model else None,
        ", ".join(c.value for c in job.contract_types) or None,
        job.seniority.value if job.seniority else None,
        job.location,
    ]
    lines = [
        f"## {rank}. [{scored.total_score}] {title}{company}",
        "",
        f"[Open the posting]({job.url})",
        "",
    ]
    if any(facts):
        lines.append("- " + " · ".join(f for f in facts if f))
    if job.salary_text:
        lines.append(f"- Salary: {md_escape(job.salary_text)}")
    if job.required_stack:
        lines.append(f"- Required stack: {', '.join(job.required_stack)}")
    if job.nice_to_have_stack:
        lines.append(f"- Nice to have: {', '.join(job.nice_to_have_stack)}")
    lines.append(f"- Why: {md_escape(d.summary)}")
    aspects = [("role", d.role), ("stack", d.stack), ("experience", d.experience),
               ("logistics", d.logistics), ("salary", d.salary)]
    lines.append(
        "- Scores: " + " · ".join(f"{name} {a.score if a.score is not None else '-'}" for name, a in aspects)
    )
    if job.unverified:
        lines.append(f"- Unverified: {', '.join(job.unverified)}")
    return "\n".join(lines)


def render_report(state: State, generated_at: datetime) -> str:
    scored = state["scored_jobs"]
    new = len(state["unique_hits"])
    rejected = len(state["rejected"])
    retry = new - len(scored) - rejected  # failed or over the cap: will come back next run

    summary = (
        f"Search results: {len(state['hits'])} · new jobs: {new} · rejected: {rejected} · "
        f"matches (score >= {MIN_SCORE}): {len(scored)}"
    )
    if retry > 0:
        summary += f" · to retry next run: {retry}"

    parts = [f"# Job report - {generated_at:%Y-%m-%d}", "", summary, ""]
    if scored:
        parts.append("\n\n".join(render_job(i, s) for i, s in enumerate(scored, start=1)))
    else:
        parts.append("No new matching jobs this time.")
    return "\n".join(parts) + "\n"


def write_report(state: State) -> dict:
    now = datetime.now()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"report_{now:%Y-%m-%d_%H%M%S}.md"
    path.write_text(render_report(state, now), encoding="utf-8")
    print(f"[report] {len(state['scored_jobs'])} matches written to {path}")
    return {"report_path": str(path)}
