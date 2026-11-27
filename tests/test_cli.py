"""Tests for cli.py. The real run and the real Streamlit are replaced by fakes."""

import logging
import signal
import sys
from logging.handlers import RotatingFileHandler

import pytest

import cli
import logs
import runner
import setup_check
from setup_check import SetupReport


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)  # don't read your real .env
    monkeypatch.setattr(logs, "LOG_DIR", tmp_path / "logs")  # don't write in your real log folder
    logs.reset_logging()
    yield
    logs.reset_logging()


def fake_run(monkeypatch, behaviour=None):
    """Replace run_pipeline. Returns the list of triggers it was called with."""
    calls = []

    def run_pipeline(trigger, state=None, on_step=None):
        calls.append(trigger)
        if behaviour:
            behaviour()

    monkeypatch.setattr(runner, "run_pipeline", run_pipeline)
    return calls


def console_level() -> int:
    handlers = logging.getLogger("jobagent").handlers
    return next(h for h in handlers if not isinstance(h, RotatingFileHandler)).level


# ----------------------------- the command line ------------------------
def test_run_defaults():
    args = cli.build_parser().parse_args(["run"])
    assert args.trigger == "manual" and args.verbose is False


def test_a_run_cannot_claim_to_come_from_the_ui(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["run", "--trigger", "ui"])
    assert stop.value.code == 2


def test_a_command_is_required(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main([])
    assert stop.value.code == 2


# ----------------------------- run -------------------------------------
def test_run_succeeds_with_exit_code_0(monkeypatch):
    calls = fake_run(monkeypatch)
    assert cli.main(["run"]) == 0
    assert calls == ["manual"]


def test_the_trigger_is_passed_on(monkeypatch):
    calls = fake_run(monkeypatch)
    cli.main(["run", "--trigger", "cron"])
    assert calls == ["cron"]


def test_a_failed_run_exits_with_1(monkeypatch):
    def fail():
        raise runner.PipelineError("score_jobs", RuntimeError("boom"), 7)

    fake_run(monkeypatch, fail)
    assert cli.main(["run"]) == 1


def test_an_unexpected_error_also_exits_with_1(monkeypatch):
    def fail():
        raise OSError("database is locked")

    fake_run(monkeypatch, fail)
    assert cli.main(["run"]) == 1


def test_ctrl_c_exits_with_130(monkeypatch):
    def stop():
        raise KeyboardInterrupt

    fake_run(monkeypatch, stop)
    assert cli.main(["run"]) == 130


def test_a_termination_signal_is_handled_like_ctrl_c_and_then_undone(monkeypatch):
    before = signal.getsignal(signal.SIGTERM)

    def terminated():
        # what the system does on `docker stop`: call the handler that is installed now
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    fake_run(monkeypatch, terminated)
    assert cli.main(["run"]) == 130
    assert signal.getsignal(signal.SIGTERM) == before


def test_verbose_shows_debug_on_the_console(monkeypatch):
    fake_run(monkeypatch)
    cli.main(["run"])
    assert console_level() == logging.INFO
    logs.reset_logging()
    cli.main(["run", "--verbose"])
    assert console_level() == logging.DEBUG


# ----------------------------- ui --------------------------------------
def fake_streamlit(monkeypatch, exit_code=0):
    commands = []

    def call(command):
        commands.append(command)
        if isinstance(exit_code, BaseException):
            raise exit_code
        return exit_code

    monkeypatch.setattr(cli.subprocess, "call", call)
    return commands


def test_ui_starts_streamlit_on_this_computer_only_by_default(monkeypatch):
    commands = fake_streamlit(monkeypatch)
    assert cli.main(["ui"]) == 0
    (command,) = commands
    assert command[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert command[4].replace("\\", "/").endswith("jobagent/ui/app.py")
    assert command[command.index("--server.address") + 1] == "127.0.0.1"
    assert command[command.index("--server.port") + 1] == "8501"
    assert "--server.headless" not in command


def test_ui_options(monkeypatch):
    commands = fake_streamlit(monkeypatch)
    cli.main(["ui", "--host", "0.0.0.0", "--port", "9000", "--headless"])
    command = commands[0]
    assert command[command.index("--server.address") + 1] == "0.0.0.0"
    assert command[command.index("--server.port") + 1] == "9000"
    assert command[command.index("--server.headless") + 1] == "true"


def test_ui_returns_the_exit_code_of_streamlit(monkeypatch):
    fake_streamlit(monkeypatch, exit_code=3)
    assert cli.main(["ui"]) == 3


def test_ctrl_c_is_a_normal_way_to_stop_the_ui(monkeypatch):
    fake_streamlit(monkeypatch, exit_code=KeyboardInterrupt())
    assert cli.main(["ui"]) == 0


# ----------------------------- check -----------------------------------
def test_check_exits_with_0_when_all_is_ready(monkeypatch, capsys):
    monkeypatch.setattr(setup_check, "check_setup", lambda: SetupReport(["[ok]  Config: x"], 0))
    assert cli.main(["check"]) == 0
    out = capsys.readouterr().out
    assert "[ok]  Config: x" in out and "Everything is ready." in out


def test_check_exits_with_1_and_counts_the_problems(monkeypatch, capsys):
    report = SetupReport(["[problem] Profile: not found", "[problem] key"], 2)
    monkeypatch.setattr(setup_check, "check_setup", lambda: report)
    assert cli.main(["check"]) == 1
    out = capsys.readouterr().out
    assert "2 problem(s) found" in out and "Everything is ready" not in out
