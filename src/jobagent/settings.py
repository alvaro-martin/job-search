"""Every setting you may want to tune, in one validated object.

Where each value comes from (later wins):
  1. the defaults in this file
  2. the config file, data/config.toml (optional: copy config.example.toml to start)
  3. environment variables, for the model names only:
       JOBAGENT_MODEL           all the steps
       JOBAGENT_QUERY_MODEL     one step only (also _EXTRACT_, _SCORE_, _PARSE_);
                                it beats JOBAGENT_MODEL

Unknown fields are rejected, so a typo in the file fails loudly instead of being ignored.
No API keys here: those stay in .env.

The settings travel inside the graph state, so every node reads state["settings"]
instead of module-level constants.
"""

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from paths import CONFIG_PATH
from schemas.schemas import StrictModel

DEFAULT_DOMAINS = [
    "gupy.io",
    "programathor.com.br",
    "vagas.com.br",
    "remotar.com.br",
    "trampos.co",
    "revelo.com.br",
    "infojobs.com.br",
]


class ConfigError(Exception):
    """The config file has a problem. The message is written to be shown to the user."""


class _Section(StrictModel):
    """Unknown fields are rejected (from StrictModel) and a loaded value can't be changed."""

    model_config = ConfigDict(frozen=True)


# ----------------------------- sections --------------------------------
class SearchSettings(_Section):
    domains: list[str] = Field(default_factory=lambda: list(DEFAULT_DOMAINS), min_length=1)
    time_range: Literal["day", "week", "month", "year"] = "week"
    results_per_query: int = Field(1, ge=1, le=20)  # Tavily allows up to 20
    max_queries: int = Field(1, ge=1, le=20)  # each query costs Tavily credits
    # Jobs posted longer ago than this are rejected after their page is read.
    # Keep it in line with time_range (a week is 7 days).
    max_age_days: int = Field(7, ge=1)

    @field_validator("domains")
    @classmethod
    def check_domains(cls, domains: list[str]) -> list[str]:
        cleaned = []
        for domain in domains:
            domain = domain.strip().lower()
            if not domain or "/" in domain or any(c.isspace() for c in domain):
                raise ValueError(f"{domain!r} should be a bare domain name, like 'gupy.io'")
            cleaned.append(domain)
        return list(dict.fromkeys(cleaned))  # drop repeats, keep the order


class FetchSettings(_Section):
    max_pages: int = Field(15, ge=1)  # pages downloaded and read per run: bounds the cost
    extract_depth: Literal["basic", "advanced"] = "basic"  # advanced: JS-heavy pages, costs more


class ScoreWeights(_Section):
    """How much each aspect counts in the total. Only the proportions matter.

    The names must match the aspects the scoring model judges.
    """

    role: int = Field(30, ge=0)
    stack: int = Field(30, ge=0)
    experience: int = Field(20, ge=0)
    logistics: int = Field(15, ge=0)
    salary: int = Field(5, ge=0)

    @model_validator(mode="after")
    def check_some_weight(self) -> "ScoreWeights":
        if not any(self.model_dump().values()):
            raise ValueError("at least one weight must be above 0")
        return self


class ScoreSettings(_Section):
    min_score: int = Field(60, ge=0, le=100)  # jobs below this are rejected
    weights: ScoreWeights = Field(default_factory=ScoreWeights)


class ModelSettings(_Section):
    """Models as "provider:model", for any provider LangChain supports."""

    query: str = Field("openai:gpt-5-nano", min_length=1)
    extract: str = Field("openai:gpt-4o-mini", min_length=1)
    score: str = Field("openai:gpt-4o-mini", min_length=1)
    parse: str = Field("openai:gpt-4o-mini", min_length=1)  # reads your CV in the Profile tab


class Settings(_Section):
    search: SearchSettings = Field(default_factory=SearchSettings)
    fetch: FetchSettings = Field(default_factory=FetchSettings)
    score: ScoreSettings = Field(default_factory=ScoreSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)


# ----------------------------- loading ---------------------------------
MODEL_ENV_VAR = "JOBAGENT_MODEL"
STEP_MODEL_ENV_VARS = {
    "query": "JOBAGENT_QUERY_MODEL",
    "extract": "JOBAGENT_EXTRACT_MODEL",
    "score": "JOBAGENT_SCORE_MODEL",
    "parse": "JOBAGENT_PARSE_MODEL",
}


def model_overrides(environ: Mapping[str, str]) -> dict[str, str]:
    """Model names set in the environment. Empty values count as not set."""
    everywhere = (environ.get(MODEL_ENV_VAR) or "").strip()
    overrides = {}
    for step, var in STEP_MODEL_ENV_VARS.items():
        value = (environ.get(var) or "").strip() or everywhere
        if value:
            overrides[step] = value
    return overrides


def read_config_file(path: Path) -> dict:
    """The parsed TOML file, or {} if there is no file."""
    if not path.exists():
        return {}
    try:
        # utf-8-sig also accepts a file saved with a BOM, as some Windows editors do
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ConfigError(f"{path} is not valid TOML: {e}") from e
    except OSError as e:
        raise ConfigError(f"Could not read {path}: {e}") from e


def format_errors(error: ValidationError) -> list[str]:
    lines = []
    for e in error.errors():
        where = " → ".join(str(part) for part in e["loc"]) or "(top level)"
        if e["type"] == "extra_forbidden":
            lines.append(f"{where}: unknown setting (check the spelling)")
            continue
        line = f"{where}: {e['msg']}"
        if isinstance(e.get("input"), str | int | float | bool):
            line += f" (got {e['input']!r})"
        lines.append(line)
    return lines


def load_settings(
    path: Path | str | None = None, environ: Mapping[str, str] | None = None
) -> Settings:
    """Defaults, then the config file, then the model environment variables.

    A missing file is fine (the defaults are used). A file with a problem raises ConfigError.
    `path` and `environ` exist for tests; normally call load_settings() with no arguments.
    """
    path = Path(path) if path is not None else CONFIG_PATH
    if environ is None:
        load_dotenv()  # so JOBAGENT_* variables written in .env count too
        environ = os.environ

    data = read_config_file(path)
    overrides = model_overrides(environ)
    models = data.get("models", {})
    if overrides and isinstance(models, dict):  # a wrong type is reported by the validation below
        data["models"] = {**models, **overrides}

    try:
        return Settings.model_validate(data)
    except ValidationError as e:
        problems = "\n".join(f"  - {line}" for line in format_errors(e))
        raise ConfigError(f"Invalid settings in {path}:\n{problems}") from e
