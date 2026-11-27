"""Tests for settings.py. Run from the project root:  pytest"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from settings import ConfigError, Settings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def load(tmp_path: Path, text: str) -> Settings:
    return load_settings(write(tmp_path, text))


# ----------------------------- defaults and the example file -----------
def test_no_file_gives_the_defaults(tmp_path):
    assert load_settings(tmp_path / "missing.toml") == Settings()


def test_example_file_matches_the_defaults():
    # If this fails, config.example.toml and the defaults in settings.py have drifted apart.
    assert load_settings(PROJECT_ROOT / "config.example.toml") == Settings()


def test_file_values_win_and_the_rest_stay_default(tmp_path):
    s = load(tmp_path, '[search]\ntime_range = "month"\n\n[score.weights]\nrole = 50\n')
    assert s.search.time_range == "month"
    assert s.search.max_queries == 1  # untouched
    assert s.score.weights.role == 50
    assert s.score.weights.stack == 30  # untouched, same table


def test_file_saved_with_a_bom_still_loads(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b"\xef\xbb\xbf[fetch]\nmax_pages = 3\n")
    assert load_settings(path).fetch.max_pages == 3


# ----------------------------- models: only from the file --------------
def test_each_step_can_use_its_own_model(tmp_path):
    text = '[models]\nquery = "openai:a"\nextract = "openai:b"\nscore = "openai:c"\n'
    s = load(tmp_path, text)
    m = s.models
    assert (m.query, m.extract, m.score) == ("openai:a", "openai:b", "openai:c")
    assert s.models.parse == Settings().models.parse  # not in the file: the default


def test_environment_variables_do_not_change_the_models(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBAGENT_MODEL", "openai:from-env")
    monkeypatch.setenv("JOBAGENT_SCORE_MODEL", "openai:from-env")
    s = load(tmp_path, '[models]\nscore = "openai:from-file"\n')
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
        load(tmp_path, 'models = "openai:gpt-4o-mini"')


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
