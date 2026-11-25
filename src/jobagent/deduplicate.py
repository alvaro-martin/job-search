"""Third node: remove duplicate hits found in this run (same job found by several queries).

It only looks at this run. Comparing with jobs from previous runs comes later,
when we connect the database.
"""

from schemas.search_hit import SearchHit
from state import State
from urls import normalize_url


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
