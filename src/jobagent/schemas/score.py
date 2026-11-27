"""Schemas for scoring: the LLM judges aspects of the fit, our code computes the total."""

from pydantic import Field

from schemas.job import JobPosting
from schemas.schemas import StrictModel


class Aspect(StrictModel):
    score: int | None = Field(
        None,
        ge=0,
        le=100,
        description="0 to 100, or null if the job does not give the information to judge it",
    )
    reason: str = Field(description="At most 15 words")


class JobScore(StrictModel):
    """What the LLM returns for one job."""

    role: Aspect
    stack: Aspect
    experience: Aspect
    logistics: Aspect
    salary: Aspect
    violates_notes: bool = Field(
        False, description="True only if the job clearly breaks the candidate's free-text notes"
    )
    notes_reason: str | None = None
    summary: str = Field(description="One sentence on the overall fit")


class ScoredJob(StrictModel):
    job: JobPosting
    total_score: int = Field(ge=0, le=100)  # computed by our code from the aspects
    details: JobScore
