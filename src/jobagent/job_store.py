"""Local SQLite database with every job we have seen, so later runs can skip them.

One row per job, identified by job_id(url). The file is data/jobs.db (never commit it).
"""

import sqlite3
from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from pathlib import Path

from schemas.search_hit import SearchHit
from urls import job_id

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "jobs.db"


class JobStatus(StrEnum):
    NEW = "new"  # seen, nothing decided yet
    REJECTED = "rejected"  # thrown out by the filter or the score
    SENT = "sent"  # included in a result sent to you
    GOOD = "good"  # you marked it as a good match
    BAD = "bad"  # you marked it as a bad match


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id         TEXT PRIMARY KEY,   -- hash of the normalized URL
    url        TEXT NOT NULL,
    title      TEXT NOT NULL,
    first_seen TEXT NOT NULL,      -- YYYY-MM-DD
    last_seen  TEXT NOT NULL,      -- YYYY-MM-DD
    status     TEXT NOT NULL
)
"""

# If the job already exists we only refresh last_seen: its status is never overwritten here.
UPSERT = """
INSERT INTO jobs (id, url, title, first_seen, last_seen, status)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen
"""


class JobStore:
    """Use it with `with`, so the connection is always closed:

    with JobStore() as store:
        store.save_hits(hits)
    """

    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(CREATE_TABLE)
        self._conn.commit()

    def __enter__(self) -> "JobStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def seen_ids(self, ids: Iterable[str]) -> set[str]:
        """Which of these job ids are already in the database?

        We read all ids and intersect in Python: simple, and fast enough for the
        few thousand jobs one person accumulates.
        """
        rows = self._conn.execute("SELECT id FROM jobs").fetchall()
        return {row[0] for row in rows} & set(ids)

    def save_hits(self, hits: list[SearchHit], status: JobStatus = JobStatus.NEW) -> int:
        """Save jobs. New ones are inserted; known ones only get last_seen updated.

        Returns how many jobs were new.
        """
        today = date.today().isoformat()
        ids = {job_id(hit.url) for hit in hits}
        already_known = self.seen_ids(ids)
        with self._conn:  # commits on success, rolls back on error
            self._conn.executemany(
                UPSERT,
                [
                    (job_id(hit.url), hit.url, hit.title, today, today, status.value)
                    for hit in hits
                ],
            )
        return len(ids - already_known)
