"""Third node: remove duplicate hits.

Two kinds of duplicates are removed:
  1. In this run: the same job found by several queries.
  2. From earlier runs: jobs already saved in the database.

This node only READS the database. Saving jobs is done by a later node, after the
rest of the pipeline has finished, so a crash in between never loses jobs.
"""

from job_store import JobStore
from logs import get_logger
from schemas.search_hit import SearchHit
from state import State
from urls import job_id, normalize_url

log = get_logger(__name__)


def remove_duplicates_in_run(hits: list[SearchHit]) -> list[SearchHit]:
    """Keep one hit per job. If a job appears several times, keep the best-scored one."""
    best: dict[str, SearchHit] = {}  # normalized url -> hit
    for hit in hits:
        key = normalize_url(hit.url)
        current = best.get(key)
        if current is None or (hit.score or 0) > (current.score or 0):
            best[key] = hit
    return list(best.values())  # keeps the order in which each job first appeared


def remove_already_seen(hits: list[SearchHit]) -> list[SearchHit]:
    """Drop the hits whose job is already in the database."""
    with JobStore() as store:
        seen = store.seen_ids(job_id(hit.url) for hit in hits)
    return [hit for hit in hits if job_id(hit.url) not in seen]


def deduplicate(state: State) -> dict:
    unique_in_run = remove_duplicates_in_run(state["hits"])
    new_hits = remove_already_seen(unique_in_run)
    log.info(
        "%d hits -> %d unique in this run -> %d new (%d already seen)",
        len(state["hits"]), len(unique_in_run), len(new_hits), len(unique_in_run) - len(new_hits),
    )
    return {"unique_hits": new_hits}
