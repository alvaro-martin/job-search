"""Third node: remove duplicate hits found in this run (same job found by several queries).

It only looks at this run. Comparing with jobs from previous runs comes later,
when we add the database.
"""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from schemas.search_hit import SearchHit
from state import State

# Query-string parameters that only track where a click came from, never which job it is.
# Any other parameter is kept, because some sites identify jobs with e.g. ?id=123.
TRACKING_PARAMS = {"gclid", "fbclid", "ref", "referrer", "source", "src", "trk", "trackingid"}


def normalize_url(url: str) -> str:
    """Canonical form of a URL, so that two links to the same job look identical."""
    parts = urlparse(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    )
    return urlunparse(
        (parts.scheme.lower() or "https", host, parts.path.rstrip("/"), "", urlencode(query), "")
    )


def deduplicate(state: State) -> dict:
    """Keep one hit per job. If a job appears several times, keep the best-scored one."""
    best: dict[str, SearchHit] = {}  # normalized url -> hit
    for hit in state["hits"]:
        key = normalize_url(hit.url)
        current = best.get(key)
        if current is None or (hit.score or 0) > (current.score or 0):
            best[key] = hit

    unique_hits = list(best.values())  # keeps the order in which each job first appeared
    print(f"[dedupe] {len(state['hits'])} hits -> {len(unique_hits)} unique")
    return {"unique_hits": unique_hits}
