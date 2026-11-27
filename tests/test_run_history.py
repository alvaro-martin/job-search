"""Tests for run_history.py: the runs table and the five counters."""

import pytest

from run_history import (
    MAX_ERROR_CHARS,
    Counters,
    RunHistory,
    RunStatus,
    RunTrigger,
    STALE_RUN_MESSAGE,
)


@pytest.fixture
def history(tmp_path):
    with RunHistory(tmp_path / "jobs.db") as h:
        yield h


def test_a_started_run_is_recorded_as_running(history):
    run_id = history.start_run(RunTrigger.UI)
    (run,) = history.recent_runs()
    assert run.id == run_id
    assert run.status == "running"
    assert run.triggered_by == "ui"
    assert run.started_at and run.finished_at is None
    assert run.matches is None and run.error is None


def test_the_trigger_can_be_given_as_text_but_must_be_a_known_one(history):
    history.start_run("cron")
    assert history.recent_runs()[0].triggered_by == "cron"
    with pytest.raises(ValueError):
        history.start_run("somebody")


def test_a_successful_run_keeps_its_counters_and_report(history):
    run_id = history.start_run(RunTrigger.MANUAL)
    counters = Counters(search_results=10, new_jobs=5, rejected=2, matches=1, to_retry=2)
    history.finish_run(run_id, RunStatus.SUCCESS, counters=counters, report_path="/r/report.md")
    (run,) = history.recent_runs()
    assert run.status == "success"
    assert run.finished_at is not None
    assert (run.search_results, run.new_jobs, run.rejected, run.matches, run.to_retry) == (
        10, 5, 2, 1, 2,
    )
    assert run.report_path == "/r/report.md"
    assert run.error is None


def test_a_failed_run_keeps_the_error_and_no_counters(history):
    run_id = history.start_run(RunTrigger.CRON)
    history.finish_run(run_id, RunStatus.FAILED, error="score_jobs: RuntimeError: boom")
    (run,) = history.recent_runs()
    assert run.status == "failed"
    assert run.error == "score_jobs: RuntimeError: boom"
    assert run.search_results is None and run.report_path is None


def test_a_very_long_error_is_cut(history):
    run_id = history.start_run(RunTrigger.UI)
    history.finish_run(run_id, RunStatus.FAILED, error="x" * (MAX_ERROR_CHARS + 500))
    assert len(history.recent_runs()[0].error) == MAX_ERROR_CHARS


def test_a_run_that_never_ended_is_closed_as_interrupted_by_the_next_one(history):
    dead = history.start_run(RunTrigger.UI)  # the process died: finish_run was never called
    history.start_run(RunTrigger.CRON)
    newest, oldest = history.recent_runs()
    assert oldest.id == dead and oldest.status == "interrupted"
    assert oldest.error == STALE_RUN_MESSAGE and oldest.finished_at is None
    assert newest.status == "running"  # the new run is not touched


def test_a_finished_run_is_not_touched_by_the_next_one(history):
    first = history.start_run(RunTrigger.UI)
    history.finish_run(first, RunStatus.SUCCESS, counters=Counters(1, 1, 0, 1, 0))
    history.start_run(RunTrigger.UI)
    assert history.recent_runs()[1].status == "success"


def test_recent_runs_are_newest_first_and_limited(history):
    ids = [history.start_run(RunTrigger.UI) for _ in range(5)]
    assert [r.id for r in history.recent_runs()] == ids[::-1]
    assert [r.id for r in history.recent_runs(limit=2)] == ids[::-1][:2]


def test_the_history_is_still_there_when_the_database_is_opened_again(tmp_path):
    path = tmp_path / "jobs.db"
    with RunHistory(path) as h:
        h.start_run(RunTrigger.UI)
    with RunHistory(path) as h:
        assert len(h.recent_runs()) == 1


def test_counters_from_a_state():
    state = {
        "hits": list(range(10)),
        "unique_hits": list(range(5)),
        "rejected": list(range(2)),
        "scored_jobs": [1],
    }
    assert Counters.from_state(state) == Counters(
        search_results=10, new_jobs=5, rejected=2, matches=1, to_retry=2
    )


def test_to_retry_is_never_negative():
    # defensive: if the counts ever do not add up, the result is 0, never negative
    state = {"hits": [1], "unique_hits": [1], "rejected": [1, 2], "scored_jobs": [1]}
    assert Counters.from_state(state).to_retry == 0
