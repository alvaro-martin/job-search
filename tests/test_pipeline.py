"""A whole run of the graph, with Tavily and the LLMs replaced by fakes (no network, no keys).

Checks that every node takes its settings from state["settings"]: change a setting and the
run changes with it.
"""

from datetime import date
from pathlib import Path

import pytest

import deduplicate
import extract_jobs
import fetch_pages
import generate_queries
import save_jobs
import score_jobs
import search_jobs
import write_report
from graph import build_graph
from job_store import JobStore
from schemas.job import JobExtraction
from schemas.schemas import Dealbreakers, Preferences, Profile
from schemas.score import Aspect, JobScore
from settings import FetchSettings, ModelSettings, ScoreSettings, SearchSettings, Settings


# ----------------------------- fakes -----------------------------------
class FakeTavily:
    """Every search returns the same 5 jobs, best-scored first. Calls are recorded."""

    def __init__(self):
        self.searches: list[dict] = []
        self.extractions: list[dict] = []

    def search(self, **kwargs):
        self.searches.append(kwargs)
        return {
            "results": [
                {
                    "url": f"https://example.com/job/{i}",
                    "title": f"Python developer {i}",
                    "content": "snippet",
                    "score": 1 - i / 10,
                }
                for i in range(5)
            ]
        }

    def extract(self, **kwargs):
        self.extractions.append(kwargs)
        return {
            "results": [
                {"url": url, "raw_content": "job description " * 30} for url in kwargs["urls"]
            ]
        }


class FakeQueryChain:
    def invoke(self, inputs):
        queries = ["python developer", "desenvolvedor python", "backend python"]
        return generate_queries.SearchQueries(queries=queries)


class FakeExtractChain:
    def batch(self, inputs, config=None, return_exceptions=False):
        return [
            JobExtraction(is_job_posting=True, title="Python developer", posted_date=date.today())
            for _ in inputs
        ]


class FakeScoreChain:
    """The first job is a great fit (90), all the others a poor one (40)."""

    def batch(self, inputs, config=None, return_exceptions=False):
        def judge(value: int) -> JobScore:
            aspect = Aspect(score=value, reason="test")
            return JobScore(
                role=aspect, stack=aspect, experience=aspect, logistics=aspect, salary=aspect,
                summary="test",
            )

        return [judge(90 if i == 0 else 40) for i in range(len(inputs))]


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """Replace Tavily and the LLMs. Returns (the fake Tavily, the model name each step used)."""
    tavily = FakeTavily()
    models_used: dict[str, str] = {}

    def fake_build_chain(step: str, chain):
        def build_chain(model: str):
            models_used[step] = model
            return chain

        return build_chain

    monkeypatch.setattr(search_jobs, "get_client", lambda: tavily)
    monkeypatch.setattr(fetch_pages, "get_client", lambda: tavily)
    chains = {
        generate_queries: ("query", FakeQueryChain()),
        extract_jobs: ("extract", FakeExtractChain()),
        score_jobs: ("score", FakeScoreChain()),
    }
    for module, (step, chain) in chains.items():
        monkeypatch.setattr(module, "build_chain", fake_build_chain(step, chain))

    # keep the database and the reports inside the test's temporary folder
    db = tmp_path / "jobs.db"
    monkeypatch.setattr(deduplicate, "JobStore", lambda: JobStore(db))
    monkeypatch.setattr(save_jobs, "JobStore", lambda: JobStore(db))
    monkeypatch.setattr(write_report, "REPORTS_DIR", tmp_path / "reports")
    return tavily, models_used


def make_settings(min_score: int = 60) -> Settings:
    """Values that differ from every default, so a node that ignored them would be caught."""
    return Settings(
        search=SearchSettings(
            domains=["example.com"], time_range="day", results_per_query=3, max_queries=2
        ),
        fetch=FetchSettings(max_pages=3, extract_depth="advanced"),
        score=ScoreSettings(min_score=min_score),
        models=ModelSettings(
            query="fake:query", extract="fake:extract", score="fake:score", parse="fake:parse"
        ),
    )


def make_state(settings: Settings) -> dict:
    return {
        "settings": settings,
        "profile": Profile(),
        "preferences": Preferences(target_roles=["python developer"]),
        "dealbreakers": Dealbreakers(),
        "queries": [], "hits": [], "unique_hits": [], "candidates": [], "rejected": [],
        "pages": {}, "jobs": [], "scored_jobs": [], "report_path": "",
    }


# ----------------------------- tests -----------------------------------
def test_every_node_uses_its_settings(fakes):
    tavily, models_used = fakes
    final = build_graph().invoke(make_state(make_settings(min_score=60)))

    # search: max_queries=2 cut the fake model's 3 queries to 2; the other options are passed on
    assert len(tavily.searches) == 2
    for call in tavily.searches:
        assert call["time_range"] == "day"
        assert call["include_domains"] == ["example.com"]
        assert call["max_results"] == 3

    # fetch: 5 different jobs were found but max_pages=3 allows only 3 downloads
    assert len(final["unique_hits"]) == 5
    assert sum(len(call["urls"]) for call in tavily.extractions) == 3
    assert all(call["extract_depth"] == "advanced" for call in tavily.extractions)
    assert len(final["pages"]) == 3

    # each LLM step got its own model
    assert models_used == {"query": "fake:query", "extract": "fake:extract", "score": "fake:score"}

    # score: with min_score=60 only the job scored 90 stays; the two scored 40 are rejected
    assert [s.total_score for s in final["scored_jobs"]] == [90]
    assert len(final["rejected"]) == 2
    assert "score >= 60" in Path(final["report_path"]).read_text(encoding="utf-8")


def test_a_lower_min_score_keeps_more_jobs(fakes):
    final = build_graph().invoke(make_state(make_settings(min_score=30)))
    assert len(final["scored_jobs"]) == 3
    assert final["rejected"] == []
