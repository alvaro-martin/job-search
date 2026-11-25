"""Schema for one raw result returned by the search engine (data shape only, no logic)."""

from schemas.schemas import StrictModel


class SearchHit(StrictModel):
    url: str
    title: str = ""
    snippet: str = ""  # short text extract Tavily returns for the page
    score: float | None = None  # Tavily's relevance score
    published_date: str | None = None  # often missing for general searches
    query: str  # which query found it


class RejectedHit(StrictModel):
    """A hit that was thrown out, with the reason why."""

    hit: SearchHit
    reason: str
