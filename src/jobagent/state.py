"""The data that travels through the graph. Every node reads it and returns updates."""

from typing import TypedDict

from schemas.schemas import Dealbreakers, Preferences, Profile
from schemas.search_hit import SearchHit


class State(TypedDict):
    profile: Profile
    preferences: Preferences
    dealbreakers: Dealbreakers
    queries: list[str]  # filled by generate_queries
    hits: list[SearchHit]  # filled by search_jobs (may contain duplicates)
    unique_hits: list[SearchHit]  # filled by deduplicate
