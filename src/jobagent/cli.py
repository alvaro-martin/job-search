"""Command-line entry point. A thin layer: the work is done by runner.py and setup_check.py.

    python src/jobagent/cli.py run     run the agent once, with no UI (this is what cron calls)
    python src/jobagent/cli.py ui      start the web UI
    python src/jobagent/cli.py check   is everything ready? (profile, config, API keys)

Exit codes (run and check):
    0    all went well
    1    the run failed, or `check` found a problem
    2    the command line itself is wrong (argparse)
    130  stopped from outside: Ctrl+C, or a termination signal such as `docker stop`

A run writes the same log and the same history as a run started from the UI.
"""

import argparse
import logging
import signal
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from logs import get_logger, setup_logging
from run_history import RunTrigger

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INTERRUPTED = 130

# Who started the run. "ui" is not here: only the Run tab uses it.
RUN_TRIGGERS = [RunTrigger.MANUAL.value, RunTrigger.CRON.value]
UI_APP_PATH = Path(__file__).parent / "ui" / "app.py"

log = get_logger(__name__)


def _stop_as_interrupt(signum, frame) -> None:
    """Make a termination signal behave like Ctrl+C, so the run is recorded as interrupted."""
    raise KeyboardInterrupt


def cmd_run(args: argparse.Namespace) -> int:
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    # Imported here, not at the top, so that `check` and `--help` do not load LangGraph and
    # the model libraries.
    from runner import PipelineError, run_pipeline

    previous = signal.signal(signal.SIGTERM, _stop_as_interrupt)
    try:
        run_pipeline(args.trigger)
    except PipelineError:
        return EXIT_FAILED  # run_pipeline already logged it and recorded it in the history
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED  # also already logged and recorded
    except Exception:
        log.exception("the run could not be started or recorded")
        return EXIT_FAILED
    finally:
        signal.signal(signal.SIGTERM, previous or signal.SIG_DFL)
    return EXIT_OK


def cmd_ui(args: argparse.Namespace) -> int:
    command = [
        sys.executable, "-m", "streamlit", "run", str(UI_APP_PATH),
        "--server.address", args.host,
        "--server.port", str(args.port),
    ]
    if args.headless:
        command += ["--server.headless", "true"]  # no browser is opened, no first-run prompt
    try:
        return subprocess.call(command)  # inherits the environment, including the .env keys
    except KeyboardInterrupt:
        return EXIT_OK  # Ctrl+C is the normal way to stop the UI


def cmd_check(args: argparse.Namespace) -> int:
    from setup_check import check_setup  # imported here: it needs the schema libraries

    report = check_setup()
    print("\n".join(report.lines))
    if report.problems:
        print(f"\n{report.problems} problem(s) found. Fix them before running.")
        return EXIT_FAILED
    print("\nEverything is ready.")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Job Agent: finds job postings that fit you.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the agent once, with no UI")
    run.add_argument("--trigger", choices=RUN_TRIGGERS, default=RunTrigger.MANUAL.value,
                     help="who started this run, as written in the history (default: manual)")
    run.add_argument("-v", "--verbose", action="store_true",
                     help="also show the detail on the console, such as each rejected job "
                          "(the log file always has it)")
    run.set_defaults(func=cmd_run)

    ui = commands.add_parser("ui", help="start the web UI")
    ui.add_argument("--host", default="127.0.0.1",
                    help="address to listen on (default: 127.0.0.1, this computer only)")
    ui.add_argument("--port", type=int, default=8501, help="port (default: 8501)")
    ui.add_argument("--headless", action="store_true",
                    help="do not open a browser (use it where there is no screen, such as Docker)")
    ui.set_defaults(func=cmd_ui)

    check = commands.add_parser(
        "check", help="check the profile, the config and the API keys, without calling any API"
    )
    check.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()  # the API keys in .env
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
