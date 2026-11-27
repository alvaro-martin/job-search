"""Fifth node: download the full text of each candidate page with Tavily Extract.

The text is only needed to extract the job's details, so it lives in the graph state
(memory) and is never saved in the database.

Jobs that are NOT fetched (over the cap, or the page failed) are removed from
`candidates`. That is on purpose: the save node only stores jobs that were fully
processed, so those jobs show up again in a later run instead of being lost.
"""

from logs import get_logger
from schemas.search_hit import SearchHit
from search_jobs import get_client
from state import State
from urls import normalize_url

log = get_logger(__name__)

# Fixed limits. The ones you may want to change (max pages, extract depth) are in the settings.
BATCH_SIZE = 20  # Tavily accepts 1 to 20 URLs per request
MAX_CHARS_PER_PAGE = 15_000  # the job description is almost always near the top
MIN_CHARS_PER_PAGE = 200  # shorter than this means the extraction got nothing useful


def fetch_batch(client, batch: list[SearchHit], extract_depth: str) -> dict[str, str]:
    """Extract up to BATCH_SIZE pages. Returns {hit.url: page text} for the ones that worked."""
    by_key = {normalize_url(hit.url): hit for hit in batch}
    try:
        response = client.extract(
            urls=[hit.url for hit in batch],
            extract_depth=extract_depth,
            format="markdown",
        )
    except Exception as e:  # network error, no credits left, etc.
        log.warning("extract failed for a batch of %d pages: %s", len(batch), e)
        return {}

    pages: dict[str, str] = {}
    for result in response.get("results", []):
        hit = by_key.get(normalize_url(result.get("url", "")))
        text = (result.get("raw_content") or "").strip()
        if hit is None:
            continue
        if len(text) < MIN_CHARS_PER_PAGE:
            log.warning("almost no text extracted from %s", hit.url)
            continue
        pages[hit.url] = text[:MAX_CHARS_PER_PAGE]
    return pages


def fetch_pages(state: State) -> dict:
    # Best-scored first, so if we hit the cap we keep the most promising jobs.
    ranked = sorted(state["candidates"], key=lambda hit: hit.score or 0, reverse=True)
    fetch = state["settings"].fetch
    to_fetch = ranked[: fetch.max_pages]
    left_for_later = len(ranked) - len(to_fetch)

    pages: dict[str, str] = {}
    if to_fetch:
        client = get_client()
        for start in range(0, len(to_fetch), BATCH_SIZE):
            pages.update(
                fetch_batch(client, to_fetch[start : start + BATCH_SIZE], fetch.extract_depth)
            )

    fetched = [hit for hit in to_fetch if hit.url in pages]
    log.info(
        "%d candidates -> %d pages fetched, %d failed, %d left for a later run",
        len(ranked), len(pages), len(to_fetch) - len(pages), left_for_later,
    )
    return {"candidates": fetched, "pages": pages}
