"""Schema for one raw result returned by the search engine (data shape only, no logic)."""

from schemas.job import JobPosting
from schemas.schemas import StrictModel
from schemas.score import JobScore


class SearchHit(StrictModel):
    url: str
    title: str = ""
    snippet: str = ""  # short text extract Tavily returns for the page
    score: float | None = None  # Tavily's relevance score
    published_date: str | None = None  # often missing for general searches
    query: str  # which query found it


class RejectedHit(StrictModel):
    """A hit that was thrown out, with the reason why.

    The optional fields hold what we had learned about the job at the moment it was rejected
    (nothing for a title rejection; the extracted job after extraction; the score after scoring).
    They are saved so you can review rejected jobs later.
    """

    hit: SearchHit
    reason: str
    job: JobPosting | None = None
    score: int | None = None
    details: JobScore | None = None
