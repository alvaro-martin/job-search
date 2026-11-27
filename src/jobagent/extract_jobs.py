"""Sixth node: an LLM reads each page and fills in a structured job posting.

It only extracts facts. Deciding whether a job passes your dealbreakers is the job of the
next nodes. The system prompt is a text file you can replace (JOBAGENT_EXTRACT_PROMPT).
"""

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from schemas.job import JobExtraction, JobPosting
from schemas.search_hit import RejectedHit
from state import State

load_dotenv()

# The model is in the settings (see settings.py).
MAX_CONCURRENCY = 5  # how many pages are read by the LLM at the same time
SYSTEM_PROMPT_PATH = Path(
    os.getenv(
        "JOBAGENT_EXTRACT_PROMPT", Path(__file__).parent / "prompts" / "extract_job_system.txt"
    )
)

HUMAN_TEMPLATE = """Today's date: {today}
Page URL: {url}

Page text:
{text}"""


def build_prompt() -> ChatPromptTemplate:
    # SystemMessage is not treated as a template, so the prompt file can contain any characters.
    system = SystemMessage(content=SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip())
    return ChatPromptTemplate.from_messages([system, ("human", HUMAN_TEMPLATE)])


def build_chain(model: str):
    """Prompt -> LLM -> validated JobExtraction object."""
    llm = init_chat_model(model, temperature=0)
    return build_prompt() | llm.with_structured_output(JobExtraction)


def extract_jobs(state: State) -> dict:
    candidates = state["candidates"]
    if not candidates:
        return {"jobs": []}

    today = date.today().isoformat()
    inputs = [{"today": today, "url": h.url, "text": state["pages"][h.url]} for h in candidates]
    # return_exceptions=True: one failing page must not stop the others
    results = build_chain(state["settings"].models.extract).batch(
        inputs, config={"max_concurrency": MAX_CONCURRENCY}, return_exceptions=True
    )

    jobs: list[JobPosting] = []
    kept = []
    rejected = list(state["rejected"])
    failed = 0
    for hit, result in zip(candidates, results, strict=True):
        if isinstance(result, Exception) or result is None:
            # Not saved, so it will be tried again in a later run.
            print(f"[warn] extraction failed for {hit.url}: {result}")
            failed += 1
        elif not result.is_job_posting:
            reason = "not a single, open job posting (listing page or other)"
            rejected.append(RejectedHit(hit=hit, reason=reason))
        else:
            jobs.append(JobPosting(url=hit.url, **result.model_dump()))
            kept.append(hit)

    print(
        f"[extract] {len(candidates)} pages -> {len(jobs)} job postings, "
        f"{len(candidates) - len(jobs) - failed} not postings, {failed} failed"
    )
    return {"candidates": kept, "jobs": jobs, "rejected": rejected}
