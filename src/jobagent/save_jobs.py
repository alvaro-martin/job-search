"""Last node: save this run's jobs in the database, so the next run skips them."""

from job_store import JobStatus, JobStore
from state import State


def save_jobs(state: State) -> dict:
    # Kept jobs are saved as "new". Rejected ones are saved too (as "rejected"), so that
    # next week we don't fetch and evaluate them all over again.
    with JobStore() as store:
        new_count = store.save_hits(state["candidates"], status=JobStatus.NEW)
        rejected_count = store.save_hits(
            [r.hit for r in state["rejected"]], status=JobStatus.REJECTED
        )
    print(f"[save] {new_count} new jobs and {rejected_count} rejected jobs saved to the database")
    return {}
