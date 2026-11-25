"""Schemas for: who you are (Profile), what you want (Preferences),
and what you do NOT want (Dealbreakers)."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base class: unknown fields are rejected, so a typo in a JSON file fails loudly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ----------------------------- fixed options ---------------------------
class WorkModel(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class ContractType(StrEnum):
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class LanguageLevel(StrEnum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    FLUENT = "fluent"
    NATIVE = "native"


# ----------------------------- Profile: who you are --------------------
class Language(StrictModel):
    name: str  # e.g. "English"
    level: LanguageLevel


class Experience(StrictModel):
    role: str
    company: str | None = None
    years: float | None = Field(None, ge=0, le=60)
    description: str | None = None


class Profile(StrictModel):
    summary: str | None = None
    years_experience: float | None = Field(None, ge=0, le=60)
    skills: list[str] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)


# ----------------------------- Preferences: what you want --------------
class SalaryRange(StrictModel):
    min: int | None = Field(None, ge=0)
    max: int | None = Field(None, ge=0)
    currency: str = Field("BRL", min_length=3, max_length=3)
    period: Literal["month", "year"] = "month"

    @model_validator(mode="after")
    def check_min_not_above_max(self) -> "SalaryRange":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min cannot be greater than max")
        return self


class Preferences(StrictModel):
    target_roles: list[str] = Field(min_length=1)  # required, at least one
    seniority: list[Seniority] = Field(default_factory=list)
    work_models: list[WorkModel] = Field(default_factory=list)
    contract_types: list[ContractType] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    salary: SalaryRange | None = None
    keywords: list[str] = Field(default_factory=list)  # nice to see in a job
    description: str | None = None  # free text: your ideal job


# ----------------------------- Dealbreakers: what you don't want -------
# Everything here is STRICT: a job that matches any of it is thrown out.
class Dealbreakers(StrictModel):
    stacks: list[str] = Field(default_factory=list)  # technologies you refuse
    title_keywords: list[str] = Field(default_factory=list)  # e.g. "estagio"
    companies: list[str] = Field(default_factory=list)
    work_models: list[WorkModel] = Field(default_factory=list)  # e.g. ["onsite"]
    contract_types: list[ContractType] = Field(default_factory=list)
    notes: str | None = None  # free text for anything else
