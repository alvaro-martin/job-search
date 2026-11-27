"""The two functions whose signatures changed when settings moved into the graph state."""

from datetime import date

from schemas.job import JobPosting
from schemas.schemas import Dealbreakers
from schemas.score import Aspect, JobScore
from filter_jobs import check_job
from score_jobs import total_score
from settings import ScoreWeights


def make_score(**scores: int | None) -> JobScore:
    """A JobScore where every aspect not given is 'cannot be judged' (None)."""
    aspects = {
        name: Aspect(score=scores.get(name), reason="test")
        for name in ("role", "stack", "experience", "logistics", "salary")
    }
    return JobScore(**aspects, summary="test")


def test_total_score_is_a_weighted_average():
    details = make_score(role=100, stack=0, experience=0, logistics=0, salary=0)
    even = ScoreWeights(role=1, stack=1, experience=0, logistics=0, salary=0).model_dump()
    assert total_score(details, even) == 50  # (1*100 + 1*0) / 2
    assert total_score(details, ScoreWeights().model_dump()) == 30  # default: 30*100 / 100


def test_total_score_ignores_aspects_that_could_not_be_judged():
    details = make_score(role=80, stack=None, experience=None, logistics=None, salary=None)
    assert total_score(details, ScoreWeights().model_dump()) == 80


def test_total_score_is_zero_when_nothing_counts():
    nothing_judged = make_score()
    assert total_score(nothing_judged, ScoreWeights().model_dump()) == 0
    # only an aspect with weight 0 was judged: must not divide by zero
    only_unweighted = make_score(salary=90)
    weights = ScoreWeights(role=1, stack=0, experience=0, logistics=0, salary=0).model_dump()
    assert total_score(only_unweighted, weights) == 0


def make_job(posted: date) -> JobPosting:
    return JobPosting(url="https://example.com/job/1", is_job_posting=True, posted_date=posted)


def test_max_age_comes_from_the_argument():
    job, today = make_job(date(2026, 11, 1)), date(2026, 11, 20)  # 19 days old
    reason, _ = check_job(job, Dealbreakers(), today, max_age_days=7)
    assert reason == "posted 19 days ago (max 7)"
    assert check_job(job, Dealbreakers(), today, max_age_days=30) == (None, [])
