"""Last node: save every job processed in this run, so the next run skips them.

Kept jobs are saved as "new" with their score; rejected jobs as "rejected" with the reason.
Saving rejected jobs matters: it stops us paying to fetch and read them again next week,
and it keeps their score so you can review them or lower the threshold later.

Jobs that failed along the way (page fetch, extraction or scoring) are NOT in these lists,
so they are not saved and will be tried again in a later run.
"""

from job_store import JobRecord, JobStatus, JobStore
from logs import get_logger
from state import State

log = get_logger(__name__)


def save_jobs(state: State) -> dict:
    hits_by_url = {hit.url: hit for hit in state["candidates"]}

    records = [
        JobRecord(
            hit=hits_by_url[scored.job.url],
            status=JobStatus.NEW,
            score=scored.total_score,
            reason=scored.details.summary,
            job=scored.job,
            details=scored.details,
        )
        for scored in state["scored_jobs"]
    ]
    records += [
        JobRecord(
            hit=r.hit,
            status=JobStatus.REJECTED,
            score=r.score,
            reason=r.reason,
            job=r.job,
            details=r.details,
        )
        for r in state["rejected"]
    ]

    with JobStore() as store:
        store.save_records(records)
    log.info(
        "%d kept and %d rejected jobs saved to the database",
        len(state["scored_jobs"]), len(state["rejected"]),
    )
    return {}
