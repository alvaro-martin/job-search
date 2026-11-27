"""Tests for settings.py. Run from the project root:  pytest"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from settings import ConfigError, Settings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NO_ENV: dict[str, str] = {}  # pass environ explicitly so the tests never read your real .env


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def load(tmp_path: Path, text: str, environ: dict[str, str] = NO_ENV) -> Settings:
    return load_settings(write(tmp_path, text), environ)


# ----------------------------- defaults and the example file -----------
def test_no_file_gives_the_defaults(tmp_path):
    assert load_settings(tmp_path / "missing.toml", NO_ENV) == Settings()


def test_example_file_matches_the_defaults():
    # If this fails, config.example.toml and the defaults in settings.py have drifted apart.
    assert load_settings(PROJECT_ROOT / "config.example.toml", NO_ENV) == Settings()


def test_file_values_win_and_the_rest_stay_default(tmp_path):
    s = load(tmp_path, '[search]\ntime_range = "month"\n\n[score.weights]\nrole = 50\n')
    assert s.search.time_range == "month"
    assert s.search.max_queries == 1  # untouched
    assert s.score.weights.role == 50
    assert s.score.weights.stack == 30  # untouched, same table


def test_file_saved_with_a_bom_still_loads(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b"\xef\xbb\xbf[fetch]\nmax_pages = 3\n")
    assert load_settings(path, NO_ENV).fetch.max_pages == 3


# ----------------------------- models and the environment --------------
def test_environment_beats_the_file_and_a_specific_variable_beats_the_general_one(tmp_path):
    text = '[models]\nscore = "openai:from-file"\nextract = "openai:from-file"\n'
    env = {"JOBAGENT_MODEL": "openai:everywhere", "JOBAGENT_SCORE_MODEL": "openai:score-only"}
    s = load(tmp_path, text, env)
    assert s.models.score == "openai:score-only"
    assert s.models.extract == "openai:everywhere"
    assert s.models.query == "openai:everywhere"
    assert s.models.parse == "openai:everywhere"


def test_blank_environment_variables_are_ignored(tmp_path):
    env = {"JOBAGENT_MODEL": "", "JOBAGENT_SCORE_MODEL": "   "}
    s = load(tmp_path, '[models]\nscore = "openai:from-file"\n', env)
    assert s.models.score == "openai:from-file"
    assert s.models.query == Settings().models.query


# ----------------------------- bad input fails loudly ------------------
def test_unknown_setting_is_rejected_and_named(tmp_path):
    with pytest.raises(ConfigError) as error:
        load(tmp_path, '[search]\ntime_rnage = "day"\n')
    assert "search → time_rnage" in str(error.value)


def test_unknown_section_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="serach"):
        load(tmp_path, "[serach]\nmax_queries = 2\n")


def test_value_out_of_range_names_the_setting_and_the_value(tmp_path):
    with pytest.raises(ConfigError) as error:
        load(tmp_path, '[search]\ntime_range = "weeks"\n[score]\nmin_score = 150\n')
    message = str(error.value)
    assert "search → time_range" in message and "'weeks'" in message
    assert "score → min_score" in message and "150" in message


def test_invalid_toml_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(tmp_path, "[search\nmax_queries = 1")


def test_wrong_type_for_a_whole_section_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="models"):
        load(tmp_path, 'models = "openai:gpt-4o-mini"', {"JOBAGENT_MODEL": "openai:other"})


def test_domains_must_be_bare_names(tmp_path):
    with pytest.raises(ConfigError, match="bare domain"):
        load(tmp_path, '[search]\ndomains = ["https://gupy.io"]\n')
    with pytest.raises(ConfigError):
        load(tmp_path, "[search]\ndomains = []\n")


def test_domains_are_lowercased_and_deduplicated(tmp_path):
    s = load(tmp_path, '[search]\ndomains = ["Gupy.io", "gupy.io", "vagas.com.br"]\n')
    assert s.search.domains == ["gupy.io", "vagas.com.br"]


def test_weights_cannot_all_be_zero(tmp_path):
    text = "[score.weights]\nrole = 0\nstack = 0\nexperience = 0\nlogistics = 0\nsalary = 0\n"
    with pytest.raises(ConfigError, match="at least one weight"):
        load(tmp_path, text)


def test_loaded_settings_cannot_be_changed():
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.search.max_queries = 99
