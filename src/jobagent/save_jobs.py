"""Last node: save this run's jobs in the database, so the next run skips them."""

from job_store import JobStatus, JobStore
from state import State


def save_jobs(state: State) -> dict:
    # For now every job is saved as "new". Once there are filter and score nodes,
    # this is where rejected jobs will be saved as "rejected".
    with JobStore() as store:
        new_count = store.save_hits(state["unique_hits"], status=JobStatus.NEW)
    print(f"[save] {new_count} new jobs saved to the database")
    return {}
