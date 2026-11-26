"""Schemas for a job posting, as extracted from the page text.

A field set to None (or an empty list) means "the page doesn't say".
"""

from datetime import date

from pydantic import Field

from schemas.schemas import ContractType, Seniority, StrictModel, WorkModel


class JobExtraction(StrictModel):
    """What the LLM fills in after reading a page. It only reports facts, no judgments."""

    is_job_posting: bool = Field(
        description="True only for ONE specific job posting. False for listing or search "
        "pages, blog posts, company pages, or postings that are closed or expired."
    )
    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_model: WorkModel | None = None
    contract_types: list[ContractType] = Field(
        default_factory=list, description="All the contract types the posting offers"
    )
    seniority: Seniority | None = None
    required_stack: list[str] = Field(default_factory=list)
    nice_to_have_stack: list[str] = Field(default_factory=list)
    min_years_experience: int | None = Field(None, ge=0, le=50)
    languages_required: list[str] = Field(
        default_factory=list, description="e.g. 'English - advanced'"
    )
    salary_text: str | None = Field(
        None, description="Salary exactly as written in the posting; never convert it"
    )
    posting_language: str | None = Field(None, description="ISO 639-1 code, e.g. 'pt' or 'en'")
    posted_date: date | None = Field(None, description="Publication date, if the page shows it")
    summary: str | None = Field(None, description="At most two sentences, in English")


class JobPosting(JobExtraction):
    """An extraction plus the URL it came from (the LLM doesn't know the URL)."""

    url: str
