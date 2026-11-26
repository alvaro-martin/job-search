"""Local SQLite database with every job we have processed, so later runs can skip them.

One row per job, identified by job_id(url). The file is data/jobs.db (never commit it).
"""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from schemas.job import JobPosting
from schemas.score import JobScore
from schemas.search_hit import SearchHit
from urls import job_id

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "jobs.db"


class JobStatus(StrEnum):
    NEW = "new"  # scored and kept, nothing decided yet
    REJECTED = "rejected"  # thrown out by a filter or the score
    SENT = "sent"  # included in a result sent to you
    GOOD = "good"  # you marked it as a good match
    BAD = "bad"  # you marked it as a bad match


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,   -- hash of the normalized URL
    url          TEXT NOT NULL,
    title        TEXT NOT NULL,
    first_seen   TEXT NOT NULL,      -- YYYY-MM-DD
    last_seen    TEXT NOT NULL,      -- YYYY-MM-DD
    status       TEXT NOT NULL,
    score        INTEGER,            -- 0-100, empty if the job was rejected before scoring
    reason       TEXT,               -- why it was rejected, or the one-sentence fit summary
    job_json     TEXT,               -- the extracted job (JobPosting), if we got that far
    details_json TEXT                -- the score per aspect (JobScore), if it was scored
)
"""

# Columns added after the first version. Databases created earlier get them automatically.
ADDED_COLUMNS = {"score": "INTEGER", "reason": "TEXT", "job_json": "TEXT", "details_json": "TEXT"}

# If the job already exists we only refresh last_seen: nothing else is overwritten here.
UPSERT = """
INSERT INTO jobs (id, url, title, first_seen, last_seen, status, score, reason, job_json, details_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen
"""


@dataclass
class JobRecord:
    """Everything we want to remember about one job."""

    hit: SearchHit
    status: JobStatus
    score: int | None = None
    reason: str | None = None
    job: JobPosting | None = None
    details: JobScore | None = None


class JobStore:
    """Use it with `with`, so the connection is always closed:

    with JobStore() as store:
        store.save_records(records)
    """

    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(CREATE_TABLE)
        self._add_missing_columns()
        self._conn.commit()

    def _add_missing_columns(self) -> None:
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(jobs)")}
        for name, sql_type in ADDED_COLUMNS.items():
            if name not in existing:
                self._conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {sql_type}")

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

    def save_records(self, records: list[JobRecord]) -> int:
        """Save jobs. New ones are inserted; known ones only get last_seen updated.

        Returns how many jobs were new.
        """
        today = date.today().isoformat()
        ids = {job_id(r.hit.url) for r in records}
        already_known = self.seen_ids(ids)
        rows = [
            (
                job_id(r.hit.url),
                r.hit.url,
                (r.job.title if r.job and r.job.title else r.hit.title),
                today,
                today,
                r.status.value,
                r.score,
                r.reason,
                r.job.model_dump_json() if r.job else None,
                r.details.model_dump_json() if r.details else None,
            )
            for r in records
        ]
        with self._conn:  # commits on success, rolls back on error
            self._conn.executemany(UPSERT, rows)
        return len(ids - already_known)
