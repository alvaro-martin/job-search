"""Tests for logs.py: where the messages go and at which level."""

import logging
from types import SimpleNamespace

import pytest

import logs
from logs import get_logger, log_rejected, reset_logging, setup_logging


@pytest.fixture(autouse=True)
def clean_logging():
    reset_logging()
    yield
    reset_logging()  # leave the "jobagent" logger as we found it for the other tests


def read_log(folder) -> str:
    for handler in logging.getLogger("jobagent").handlers:
        handler.flush()
    return (folder / "jobagent.log").read_text(encoding="utf-8")


def test_loggers_are_named_after_their_module():
    assert get_logger("score_jobs").name == "jobagent.score_jobs"


def test_console_shows_info_and_the_file_also_has_debug(tmp_path, capsys):
    setup_logging(log_dir=tmp_path)
    log = get_logger("demo")
    log.debug("a detail")
    log.info("a count")
    log.warning("a problem")

    shown = capsys.readouterr().err
    assert "a count" in shown and "a problem" in shown
    assert "a detail" not in shown

    in_file = read_log(tmp_path)
    assert "a detail" in in_file and "a count" in in_file and "a problem" in in_file
    assert "DEBUG" in in_file and "jobagent.demo" in in_file


def test_calling_setup_again_does_not_repeat_the_lines(tmp_path, capsys):
    setup_logging(log_dir=tmp_path)
    setup_logging(log_dir=tmp_path)  # what the Streamlit app does on every rerun
    get_logger("demo").info("only once")
    assert capsys.readouterr().err.count("only once") == 1
    assert read_log(tmp_path).count("only once") == 1


def test_a_log_folder_that_cannot_be_used_does_not_stop_the_app(tmp_path, capsys):
    not_a_folder = tmp_path / "file"
    not_a_folder.write_text("in the way")
    setup_logging(log_dir=not_a_folder)  # must not raise
    get_logger("demo").info("still logged")
    shown = capsys.readouterr().err
    assert "Could not open the log file" in shown
    assert "still logged" in shown


def test_the_file_is_rotated_when_it_gets_too_big(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "MAX_FILE_BYTES", 300)
    setup_logging(log_dir=tmp_path)
    for i in range(30):
        get_logger("demo").info("line number %d with some padding to fill the file", i)
    assert (tmp_path / "jobagent.log.1").exists()


def test_rejected_jobs_are_logged_at_debug_only(tmp_path, capsys):
    setup_logging(log_dir=tmp_path)
    rejected = [
        SimpleNamespace(hit=SimpleNamespace(title="PHP developer"), reason="excluded stack 'php'"),
        SimpleNamespace(hit=SimpleNamespace(title="Intern"), reason="title keyword 'intern'"),
    ]
    log_rejected(get_logger("demo"), rejected)
    assert "PHP developer" not in capsys.readouterr().err
    in_file = read_log(tmp_path)
    assert "rejected: PHP developer (excluded stack 'php')" in in_file
    assert "rejected: Intern (title keyword 'intern')" in in_file
