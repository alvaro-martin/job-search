"""The data that travels through the graph. Every node reads it and returns updates."""

from typing import TypedDict

from schemas.schemas import Dealbreakers, Preferences, Profile
from schemas.job import JobPosting
from schemas.score import ScoredJob
from schemas.search_hit import RejectedHit, SearchHit


class State(TypedDict):
    profile: Profile
    preferences: Preferences
    dealbreakers: Dealbreakers
    queries: list[str]  # filled by generate_queries
    hits: list[SearchHit]  # filled by search_jobs (may contain duplicates)
    unique_hits: list[SearchHit]  # filled by deduplicate (jobs not seen before)
    candidates: list[SearchHit]  # filled by filter_by_title: still in the race
    rejected: list[RejectedHit]  # filled by filter_by_title: thrown out, with reason
    pages: dict[str, str]  # filled by fetch_pages: job url -> page text (memory only)
    jobs: list[JobPosting]  # filled by extract_jobs: structured details of each job
    scored_jobs: list[ScoredJob]  # filled by score_jobs: best first
