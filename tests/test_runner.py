"""Tests for runner.py: what run_pipeline does and what it writes in the history.

The graph is replaced by a fake that streams ready-made updates, so these tests need no
network, no API keys and no models.
"""

import pytest

import runner
from run_history import Counters, RunHistory, RunStatus, RunTrigger

STEPS = list(runner.NODES)  # the real steps, in order

# What each step adds to the state, as the real steps would
UPDATES = {
    "search_jobs": {"hits": list(range(10))},
    "deduplicate": {"unique_hits": list(range(5))},
    "score_jobs": {"scored_jobs": [1], "rejected": [1, 2]},
    "write_report": {"report_path": "/reports/report.md"},
    "save_jobs": None,  # a step that changes nothing may report None
}


def start_state() -> dict:
    return {"hits": [], "unique_hits": [], "rejected": [], "scored_jobs": [], "report_path": ""}


class FakeApp:
    """Streams one update per step. Raises `error` right after the step `fail_after`."""

    def __init__(self, fail_after: str | None = None, error: BaseException | None = None):
        self.fail_after, self.error = fail_after, error

    def stream(self, state, stream_mode):
        assert stream_mode == "updates"
        for name in STEPS:
            yield {name: UPDATES.get(name, {})}
            if name == self.fail_after:
                raise self.error


@pytest.fixture
def history_db(tmp_path, monkeypatch):
    """Keep the history in a temporary database. Returns a function that reads its runs."""
    path = tmp_path / "jobs.db"
    monkeypatch.setattr(runner, "RunHistory", lambda: RunHistory(path))

    def runs():
        with RunHistory(path) as history:
            return history.recent_runs()

    return runs


def use_app(monkeypatch, app: FakeApp) -> None:
    monkeypatch.setattr(runner, "build_graph", lambda: app)


def test_a_successful_run_returns_and_records_its_result(history_db, monkeypatch):
    use_app(monkeypatch, FakeApp())
    result = runner.run_pipeline(RunTrigger.UI, state=start_state())

    assert result.counters == Counters(
        search_results=10, new_jobs=5, rejected=2, matches=1, to_retry=2
    )
    assert result.report_path == "/reports/report.md"
    assert result.state["hits"] == list(range(10))

    (run,) = history_db()
    assert run.id == result.run_id
    assert run.status == "success" and run.triggered_by == "ui"
    assert run.finished_at is not None
    assert (run.search_results, run.new_jobs, run.rejected, run.matches, run.to_retry) == (
        10, 5, 2, 1, 2,
    )
    assert run.report_path == "/reports/report.md" and run.error is None


def test_the_trigger_is_recorded(history_db, monkeypatch):
    use_app(monkeypatch, FakeApp())
    runner.run_pipeline("cron", state=start_state())
    assert history_db()[0].triggered_by == "cron"


def test_the_progress_callback_is_called_after_every_step(history_db, monkeypatch):
    use_app(monkeypatch, FakeApp())
    hits_seen = {}  # step -> (hits before it, hits after it)

    def on_step(node, before, after):
        hits_seen[node] = (len(before["hits"]), len(after["hits"]))

    runner.run_pipeline(RunTrigger.UI, state=start_state(), on_step=on_step)
    assert list(hits_seen) == STEPS  # every step, in order
    assert hits_seen["search_jobs"] == (0, 10)


def test_the_starting_state_is_not_changed(history_db, monkeypatch):
    use_app(monkeypatch, FakeApp())
    state = start_state()
    runner.run_pipeline(RunTrigger.UI, state=state)
    assert state == start_state()


def test_a_failing_step_is_named_and_recorded(history_db, monkeypatch):
    use_app(monkeypatch, FakeApp(fail_after="filter_jobs", error=RuntimeError("boom")))
    with pytest.raises(runner.PipelineError) as error:
        runner.run_pipeline(RunTrigger.CRON, state=start_state())

    assert error.value.step == "score_jobs"  # the step after the last one that finished
    assert isinstance(error.value.cause, RuntimeError)

    (run,) = history_db()
    assert run.id == error.value.run_id
    assert run.status == "failed"
    assert run.error == "score_jobs: RuntimeError: boom"
    assert run.finished_at is not None
    assert run.search_results is None and run.report_path is None


def test_an_error_without_a_message_still_says_what_it_was(history_db, monkeypatch):
    use_app(monkeypatch, FakeApp(fail_after="generate_queries", error=KeyError()))
    with pytest.raises(runner.PipelineError):
        runner.run_pipeline(RunTrigger.UI, state=start_state())
    assert history_db()[0].error == "search_jobs: KeyError"


def test_a_problem_before_the_first_step_is_recorded_as_setup(history_db, monkeypatch):
    def no_profile():
        raise FileNotFoundError("no profile saved yet")

    monkeypatch.setattr(runner, "load_initial_state", no_profile)
    with pytest.raises(runner.PipelineError) as error:
        runner.run_pipeline(RunTrigger.CRON)  # no state given: it must be loaded
    assert error.value.step == "setup"
    run = history_db()[0]
    assert run.status == "failed" and run.error.startswith("setup: FileNotFoundError")


def test_a_stopped_run_is_recorded_as_interrupted_and_the_stop_is_not_hidden(
    history_db, monkeypatch
):
    use_app(monkeypatch, FakeApp(fail_after="search_jobs", error=KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        runner.run_pipeline(RunTrigger.UI, state=start_state())
    run = history_db()[0]
    assert run.status == "interrupted"
    assert run.error.startswith("deduplicate: KeyboardInterrupt")


def test_a_problem_writing_the_end_of_the_history_does_not_hide_the_result(
    history_db, monkeypatch
):
    use_app(monkeypatch, FakeApp())
    real = runner.RunHistory
    opened = []

    def second_open_fails():
        opened.append(1)
        if len(opened) > 1:  # the first open records the start; the end cannot be written
            raise OSError("disk full")
        return real()

    monkeypatch.setattr(runner, "RunHistory", second_open_fails)
    result = runner.run_pipeline(RunTrigger.UI, state=start_state())
    assert result.counters.matches == 1  # the run itself is reported as it went
    assert history_db()[0].status == "running"  # and the row will be closed by the next run
