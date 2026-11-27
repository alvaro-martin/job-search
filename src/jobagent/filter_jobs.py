"""Seventh node: apply your dealbreakers to the extracted job details (strict, no LLM).

Rules, all in plain code so they are predictable and testable:
  - an excluded stack that is REQUIRED by the job            -> reject
    (a nice-to-have mention does not reject; the score will take it into account)
  - an excluded company                                      -> reject
  - an excluded work model                                   -> reject
  - ALL the contract types the job offers are excluded       -> reject
    (if it offers CLT or PJ and only PJ is excluded, it stays)
  - posted more than settings.search.max_age_days ago        -> reject

When the page does not state something we would have liked to check, the job is NOT
rejected: it is kept and flagged in `job.unverified`.
"""

from datetime import date

from logs import get_logger, log_rejected
from schemas.job import JobPosting
from schemas.schemas import Dealbreakers
from schemas.search_hit import RejectedHit
from state import State
from text_match import contains_term

log = get_logger(__name__)


def check_job(
    job: JobPosting,
    dealbreakers: Dealbreakers,
    today: date | None = None,
    *,
    max_age_days: int,
) -> tuple[str | None, list[str]]:
    """Returns (reason to reject or None, flags for things the page doesn't say)."""
    today = today or date.today()

    for term in dealbreakers.stacks:
        if any(contains_term(item, term) for item in job.required_stack):
            return f"excluded stack '{term}' is required", []

    if job.company:
        for term in dealbreakers.companies:
            if contains_term(job.company, term):
                return f"excluded company '{term}'", []

    if job.work_model and job.work_model in dealbreakers.work_models:
        return f"work model '{job.work_model.value}' is excluded", []

    if job.contract_types and all(c in dealbreakers.contract_types for c in job.contract_types):
        offered = ", ".join(c.value for c in job.contract_types)
        return f"all the contract types offered are excluded ({offered})", []

    if job.posted_date:
        age = (today - job.posted_date).days
        if age > max_age_days:
            return f"posted {age} days ago (max {max_age_days})", []

    flags: list[str] = []
    if dealbreakers.work_models and job.work_model is None:
        flags.append("work model not stated")
    if dealbreakers.contract_types and not job.contract_types:
        flags.append("contract type not stated")
    if job.posted_date is None:
        flags.append("posting date not stated")
    return None, flags


def filter_jobs(state: State) -> dict:
    hits_by_url = {hit.url: hit for hit in state["candidates"]}
    kept_jobs: list[JobPosting] = []
    kept_hits = []
    rejected = list(state["rejected"])
    max_age_days = state["settings"].search.max_age_days

    for job in state["jobs"]:
        reason, flags = check_job(job, state["dealbreakers"], max_age_days=max_age_days)
        if reason:
            rejected.append(RejectedHit(hit=hits_by_url[job.url], reason=reason, job=job))
        else:
            kept_jobs.append(job.model_copy(update={"unverified": flags}))
            kept_hits.append(hits_by_url[job.url])

    n_rejected = len(state["jobs"]) - len(kept_jobs)
    log.info("%d jobs -> %d kept, %d rejected by your dealbreakers",
             len(state["jobs"]), len(kept_jobs), n_rejected)
    log_rejected(log, rejected[len(state["rejected"]) :])
    return {"candidates": kept_hits, "jobs": kept_jobs, "rejected": rejected}
