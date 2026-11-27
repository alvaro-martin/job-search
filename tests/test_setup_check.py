"""Tests for setup_check.py: what `check` reports. No API is ever called."""

import shutil
from pathlib import Path

import pytest

from setup_check import check_keys, check_setup
from settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_PROFILE = PROJECT_ROOT / "src" / "jobagent" / "data" / "example.profile.json"
SECRET = "sk-this-must-never-be-printed"


@pytest.fixture
def ready(tmp_path, monkeypatch):
    """A valid profile and both API keys set. Returns (config path, profile path)."""
    profile = tmp_path / "profile.json"
    shutil.copy(EXAMPLE_PROFILE, profile)
    monkeypatch.setenv("TAVILY_API_KEY", SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    return tmp_path / "config.toml", profile  # no config file: the defaults are used


def text(report) -> str:
    return "\n".join(report.lines)


def test_everything_ready(ready):
    config, profile = ready
    report = check_setup(config, profile)
    assert report.problems == 0
    assert "[problem]" not in text(report)
    assert "Config: no config file, using the defaults" in text(report)
    assert "Profile:" in text(report) and "TAVILY_API_KEY" in text(report)


def test_the_keys_are_never_printed(ready):
    config, profile = ready
    assert SECRET not in text(check_setup(config, profile))


def test_a_missing_key_is_a_problem(ready, monkeypatch):
    config, profile = ready
    monkeypatch.delenv("OPENAI_API_KEY")
    report = check_setup(config, profile)
    assert report.problems == 1
    assert "[problem]" in text(report) and "OPENAI_API_KEY" in text(report)
    assert "MISSING" in text(report)


def test_a_missing_profile_is_a_problem(ready):
    config, profile = ready
    profile.unlink()
    report = check_setup(config, profile)
    assert report.problems == 1
    assert "not found" in text(report) and "Profile tab" in text(report)


def test_an_invalid_profile_is_a_problem_and_says_why(ready):
    config, profile = ready
    profile.write_text('{"nonsense": 1}', encoding="utf-8")
    report = check_setup(config, profile)
    assert report.problems == 1
    assert "is not valid" in text(report)


def test_an_invalid_config_is_a_problem_and_the_rest_is_still_checked(ready):
    config, profile = ready
    config.write_text('[search]\ntime_rnage = "day"\n', encoding="utf-8")
    report = check_setup(config, profile)
    assert report.problems == 1  # only the config: the profile is fine
    assert "time_rnage" in text(report)
    assert "Profile:" in text(report) and "[ok]" in text(report)
    assert "API keys: can't be checked until the config is valid" in text(report)


def test_every_problem_is_counted(ready, monkeypatch):
    config, profile = ready
    profile.unlink()
    monkeypatch.delenv("TAVILY_API_KEY")
    monkeypatch.delenv("OPENAI_API_KEY")
    assert check_setup(config, profile).problems == 3


def test_a_provider_that_cannot_be_checked_is_not_a_problem(ready):
    config, profile = ready
    config.write_text('[models]\nquery = "newprovider:some-model"\n', encoding="utf-8")
    report = check_setup(config, profile)
    assert report.problems == 0
    assert "[unknown]" in text(report) and "newprovider:some-model" in text(report)


def test_models_of_one_provider_need_one_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    names = [c["name"] for c in check_keys(Settings())]  # the defaults are all OpenAI
    assert names == ["TAVILY_API_KEY", "OPENAI_API_KEY"]
