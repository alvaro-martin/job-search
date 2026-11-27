"""Run the whole pipeline and record the run in the history.

The Run tab of the UI and the command line both call run_pipeline(), so they behave the
same and write the same history. Nothing here depends on Streamlit.

How a run ends, and what is written in the history:
  - it finishes:           status "success", the five counters and the report path
  - a step raises:         status "failed" and the error, and PipelineError is raised
  - it is stopped outside: status "interrupted" (Ctrl+C, a closed page) and the original
                           exception is raised again
"""

from collections.abc import Callable
from dataclasses import dataclass

from graph import NODES, build_graph, load_initial_state
from logs import get_logger
from run_history import Counters, RunHistory, RunStatus, RunTrigger

log = get_logger(__name__)

# Called after each step with (step name, state before it, state after it).
StepCallback = Callable[[str, dict, dict], None]

SETUP_STEP = "setup"  # reading the settings and the profile, before the first step


class PipelineError(Exception):
    """A step of the pipeline raised an error. `step` is its name and `cause` the error."""

    def __init__(self, step: str, cause: Exception, run_id: int):
        super().__init__(f"{step}: {describe_error(cause)}")
        self.step = step
        self.cause = cause
        self.run_id = run_id


@dataclass
class RunResult:
    run_id: int
    counters: Counters
    report_path: str
    state: dict  # the final state of the graph


def describe_error(error: BaseException) -> str:
    """'RuntimeError: message', or just the type if the error has no message."""
    text = str(error).strip()
    name = type(error).__name__
    return f"{name}: {text}" if text else name


def _record_start(trigger: RunTrigger) -> int:
    with RunHistory() as history:
        return history.start_run(trigger)


def _record_end(run_id: int, status: RunStatus, **details) -> None:
    """Complete the run's row. A problem here is logged, not raised: it must not hide how
    the run itself ended."""
    try:
        with RunHistory() as history:
            history.finish_run(run_id, status, **details)
    except Exception:
        log.exception("could not update the history of run %d", run_id)


def run_pipeline(
    trigger: RunTrigger | str,
    state: dict | None = None,
    on_step: StepCallback | None = None,
) -> RunResult:
    """Run every step of the pipeline, in order, and record the run.

    `state` is the starting state. Leave it out to load the settings and your saved profile
    (which fail if there is no valid profile yet). The UI passes the state it already loaded.
    `on_step` is for live progress: it is called after each step.
    """
    trigger = RunTrigger(trigger)
    run_id = _record_start(trigger)
    log.info("run %d started (trigger: %s)", run_id, trigger.value)

    names = list(NODES)
    step = SETUP_STEP  # the step that is running now, so a failure can name it
    try:
        final = dict(state if state is not None else load_initial_state())
        step = names[0]
        for chunk in build_graph().stream(final, stream_mode="updates"):
            for node, update in chunk.items():
                before = dict(final)
                final.update(update or {})  # a node that changes nothing may report None
                if node in names:
                    step = names[min(names.index(node) + 1, len(names) - 1)]
                if on_step:
                    on_step(node, before, final)
        counters = Counters.from_state(final)
    except Exception as e:
        _record_end(run_id, RunStatus.FAILED, error=f"{step}: {describe_error(e)}")
        log.error("run %d failed during %s: %s", run_id, step, describe_error(e))
        log.debug("traceback of run %d", run_id, exc_info=True)
        raise PipelineError(step, e, run_id) from e
    except BaseException as e:  # Ctrl+C, a closed page: not an error in the steps
        _record_end(run_id, RunStatus.INTERRUPTED, error=f"{step}: {describe_error(e)}")
        log.warning("run %d interrupted during %s", run_id, step)
        raise

    _record_end(
        run_id, RunStatus.SUCCESS, counters=counters, report_path=final["report_path"]
    )
    log.info(
        "run %d finished: %d results, %d new, %d rejected, %d matches, %d to retry. Report: %s",
        run_id,
        counters.search_results,
        counters.new_jobs,
        counters.rejected,
        counters.matches,
        counters.to_retry,
        final["report_path"],
    )
    return RunResult(
        run_id=run_id, counters=counters, report_path=final["report_path"], state=final
    )
