"""The history of the runs, in the same SQLite database as the jobs (data/jobs.db).

One row per run. runner.run_pipeline creates the row when the run starts and completes it
when the run ends, so a run that was killed in the middle still leaves a row, and the next
run marks it as interrupted.

Times are the machine's local time, written as YYYY-MM-DD HH:MM:SS.
"""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from paths import DB_PATH

MAX_ERROR_CHARS = 2000
STALE_RUN_MESSAGE = "The process stopped before the run finished (it was closed or crashed)."


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"  # a step raised an error
    INTERRUPTED = "interrupted"  # stopped from outside: Ctrl+C, a closed page, a killed process


class RunTrigger(StrEnum):
    UI = "ui"  # the Run button
    CRON = "cron"  # a scheduled run
    MANUAL = "manual"  # started by hand from the command line


@dataclass(frozen=True)
class Counters:
    """The five numbers that summarize a run."""

    search_results: int
    new_jobs: int
    rejected: int
    matches: int
    to_retry: int  # new jobs that were neither kept nor rejected: they come back next run

    @classmethod
    def from_state(cls, state: Mapping) -> "Counters":
        new, rejected, matches = (
            len(state["unique_hits"]),
            len(state["rejected"]),
            len(state["scored_jobs"]),
        )
        return cls(
            search_results=len(state["hits"]),
            new_jobs=new,
            rejected=rejected,
            matches=matches,
            to_retry=max(new - matches - rejected, 0),
        )


@dataclass
class RunRecord:
    """A row read back from the database. The counters are None if the run did not finish."""

    id: int
    started_at: str
    finished_at: str | None
    status: str
    triggered_by: str
    search_results: int | None
    new_jobs: int | None
    rejected: int | None
    matches: int | None
    to_retry: int | None
    report_path: str | None
    error: str | None


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,           -- empty while running, or if the process died
    status         TEXT NOT NULL,  -- running, success, failed or interrupted
    triggered_by   TEXT NOT NULL,  -- ui, cron or manual
    search_results INTEGER,        -- the five counters: empty unless the run succeeded
    new_jobs       INTEGER,
    rejected       INTEGER,
    matches        INTEGER,
    to_retry       INTEGER,
    report_path    TEXT,
    error          TEXT            -- what went wrong, if the run did not succeed
)
"""

COLUMNS = (
    "id, started_at, finished_at, status, triggered_by, search_results, new_jobs, rejected, "
    "matches, to_retry, report_path, error"
)


def now_text() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


class RunHistory:
    """Use it with `with`, so the connection is always closed:

    with RunHistory() as history:
        run_id = history.start_run(RunTrigger.UI)
    """

    def __init__(self, path: Path | str = DB_PATH):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(CREATE_TABLE)
        self._conn.commit()

    def __enter__(self) -> "RunHistory":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def start_run(self, triggered_by: RunTrigger | str) -> int:
        """Record that a run started and return its id.

        A run still marked as running at this point never got to write its end (the process
        died), so it is closed as interrupted first. Two runs at the same time are not
        guarded against: if that happens, the first one is closed this way too, and it
        writes its real result when it ends.
        """
        triggered_by = RunTrigger(triggered_by)
        with self._conn:  # commits on success, rolls back on error
            self._conn.execute(
                "UPDATE runs SET status = ?, error = ? WHERE status = ?",
                (RunStatus.INTERRUPTED.value, STALE_RUN_MESSAGE, RunStatus.RUNNING.value),
            )
            cursor = self._conn.execute(
                "INSERT INTO runs (started_at, status, triggered_by) VALUES (?, ?, ?)",
                (now_text(), RunStatus.RUNNING.value, triggered_by.value),
            )
        return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        status: RunStatus,
        counters: Counters | None = None,
        report_path: str | None = None,
        error: str | None = None,
    ) -> None:
        """Complete the row of a run: how it ended, its numbers, its report or its error."""
        if error is not None:
            error = error[:MAX_ERROR_CHARS]
        numbers = (
            (counters.search_results, counters.new_jobs, counters.rejected, counters.matches,
             counters.to_retry)
            if counters
            else (None,) * 5
        )
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET finished_at = ?, status = ?, search_results = ?, new_jobs = ?, "
                "rejected = ?, matches = ?, to_retry = ?, report_path = ?, error = ? WHERE id = ?",
                (now_text(), RunStatus(status).value, *numbers, report_path, error, run_id),
            )

    def recent_runs(self, limit: int = 100) -> list[RunRecord]:
        """The latest runs, newest first."""
        rows = self._conn.execute(
            f"SELECT {COLUMNS} FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [RunRecord(*row) for row in rows]
