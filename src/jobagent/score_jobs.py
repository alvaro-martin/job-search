"""Eighth node: score how well each remaining job fits you (0 to 100).

The LLM judges separate aspects (role, stack, experience, logistics, salary). The total is
computed here, in plain code, with fixed weights, so scores are consistent and every number
can be explained. Aspects the job doesn't give information about are left out of the average.

Also checks your free-text dealbreaker notes, which plain code cannot evaluate.
The system prompt is a text file you can replace (JOBAGENT_SCORE_PROMPT).
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from logs import get_logger, log_rejected
from schemas.score import JobScore, ScoredJob
from schemas.search_hit import RejectedHit
from state import State

load_dotenv()
log = get_logger(__name__)

# The model, the minimum score and the weights are in the settings (see settings.py).
MAX_CONCURRENCY = 5

SYSTEM_PROMPT_PATH = Path(
    os.getenv("JOBAGENT_SCORE_PROMPT", Path(__file__).parent / "prompts" / "score_job_system.txt")
)

HUMAN_TEMPLATE = """Candidate profile:
{profile}

Candidate preferences:
{preferences}

Candidate notes about what they do not want:
{notes}

Job:
{job}"""


def build_prompt() -> ChatPromptTemplate:
    system = SystemMessage(content=SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip())
    return ChatPromptTemplate.from_messages([system, ("human", HUMAN_TEMPLATE)])


def build_chain(model: str):
    """Prompt -> LLM -> validated JobScore object."""
    llm = init_chat_model(model, temperature=0)
    return build_prompt() | llm.with_structured_output(JobScore)


def total_score(details: JobScore, weights: dict[str, int]) -> int:
    """Weighted average of the aspects that could be judged (0 if none could)."""
    judged = [
        (weights[name], getattr(details, name).score)
        for name in weights
        if getattr(details, name).score is not None
    ]
    total_weight = sum(w for w, _ in judged)
    if total_weight == 0:  # nothing judged, or only aspects whose weight is 0
        return 0
    return round(sum(w * s for w, s in judged) / total_weight)


def score_jobs(state: State) -> dict:
    jobs, candidates = state["jobs"], state["candidates"]
    if not jobs:
        return {"scored_jobs": []}

    settings = state["settings"]
    min_score, weights = settings.score.min_score, settings.score.weights.model_dump()
    profile = state["profile"].model_dump_json(indent=2, exclude_none=True)
    preferences = state["preferences"].model_dump_json(indent=2, exclude_none=True)
    notes = state["dealbreakers"].notes or "(none)"
    inputs = [
        {
            "profile": profile,
            "preferences": preferences,
            "notes": notes,
            "job": job.model_dump_json(indent=2, exclude_none=True, exclude={"url", "is_job_posting"}),
        }
        for job in jobs
    ]
    results = build_chain(settings.models.score).batch(
        inputs, config={"max_concurrency": MAX_CONCURRENCY}, return_exceptions=True
    )

    scored: list[ScoredJob] = []
    kept_hits, kept_jobs = [], []
    rejected = list(state["rejected"])
    failed = 0
    for hit, job, details in zip(candidates, jobs, results, strict=True):
        if isinstance(details, Exception) or details is None:
            # Not saved, so it will be tried again in a later run.
            log.warning("scoring failed for %s: %s", job.url, details)
            failed += 1
            continue

        total = total_score(details, weights)
        if details.violates_notes:
            reason = f"breaks your notes: {details.notes_reason or 'see job'}"
        elif total < min_score:
            reason = f"score {total} is below {min_score}: {details.summary}"
        else:
            reason = None

        if reason:
            rejected.append(
                RejectedHit(hit=hit, reason=reason, job=job, score=total, details=details)
            )
        else:
            scored.append(ScoredJob(job=job, total_score=total, details=details))
            kept_hits.append(hit)
            kept_jobs.append(job)

    order = sorted(range(len(scored)), key=lambda i: scored[i].total_score, reverse=True)
    scored = [scored[i] for i in order]
    kept_hits, kept_jobs = [kept_hits[i] for i in order], [kept_jobs[i] for i in order]

    log.info(
        "%d jobs -> %d kept (score >= %d), %d rejected, %d failed",
        len(jobs), len(scored), min_score, len(jobs) - len(scored) - failed, failed,
    )
    log_rejected(log, rejected[len(state["rejected"]) :])
    return {"scored_jobs": scored, "candidates": kept_hits, "jobs": kept_jobs, "rejected": rejected}
