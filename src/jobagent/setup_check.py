"""Is everything ready for a run? Reads files and environment variables only: it never
calls an API, so it costs nothing and can be run at any time.

Used by the `check` command and, for the API keys, by the Setup check box of the Run tab.
The keys are read from the environment: load the .env file first (load_dotenv()).
"""

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from paths import CONFIG_PATH, PROFILE_PATH
from schemas.user_profile import UserProfile
from settings import ConfigError, Settings, format_errors, load_settings

# Which environment variable holds the key for each model provider.
# None means no key is needed; providers that are not listed can't be checked.
PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistralai": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "ollama": None,
}


def check_keys(settings: Settings) -> list[dict]:
    """Which API keys does a run need, and are they set? Never returns the keys themselves."""
    checks = [{"name": "TAVILY_API_KEY", "needed_by": "search and page download",
               "status": "found" if os.getenv("TAVILY_API_KEY") else "missing"}]
    models = settings.models
    for model in dict.fromkeys([models.query, models.extract, models.score]):  # unique, in order
        provider = model.split(":", 1)[0] if ":" in model else None
        if provider in PROVIDER_KEYS and PROVIDER_KEYS[provider] is None:
            continue  # e.g. a local model: no key needed
        if provider in PROVIDER_KEYS:
            env = PROVIDER_KEYS[provider]
            checks.append({"name": env, "needed_by": f"model {model}",
                           "status": "found" if os.getenv(env) else "missing"})
        else:
            checks.append({"name": f"key for {model}", "needed_by": f"model {model}",
                           "status": "unknown"})
    unique = {}
    for c in checks:  # two models from the same provider share one key
        unique.setdefault(c["name"], c)
    return list(unique.values())


@dataclass
class SetupReport:
    lines: list[str]  # what to print
    problems: int  # how many things stop a run; 0 means ready


def _line(tag: str, text: str) -> str:
    """'[ok]       text'. A text on several lines is indented under the first one."""
    first, *rest = text.splitlines() or [""]
    prefix = f"[{tag}]" if tag else ""  # no tag: a continuation of the line above
    return "\n".join([f"{prefix:<11}{first}", *(f"{'':<11}{line}" for line in rest)])


def check_setup(
    config_path: Path | str | None = None, profile_path: Path | str | None = None
) -> SetupReport:
    """Check the config file, the profile and the API keys, and say what is wrong."""
    config_path = Path(config_path) if config_path is not None else CONFIG_PATH
    profile_path = Path(profile_path) if profile_path is not None else PROFILE_PATH
    lines, problems = [], 0

    # ---- config
    settings = None
    try:
        settings = load_settings(config_path)
    except ConfigError as e:
        problems += 1
        lines.append(_line("problem", f"Config: {e}"))
    else:
        where = str(config_path) if config_path.exists() else "no config file, using the defaults"
        lines.append(_line("ok", f"Config: {where}"))
        m = settings.models
        lines.append(_line("", f"Models: query={m.query}, extract={m.extract}, score={m.score}"))

    # ---- profile
    try:
        user = UserProfile.load(profile_path)
    except FileNotFoundError:
        problems += 1
        lines.append(_line("problem", f"Profile: not found at {profile_path}. "
                                      "Create it in the Profile tab of the UI."))
    except ValueError as e:  # ValidationError (a pydantic ValueError) or a file we can't read
        problems += 1
        details = "\n".join(format_errors(e)) if isinstance(e, ValidationError) else str(e)
        lines.append(_line("problem", f"Profile: {profile_path} is not valid:\n{details}"))
    else:
        roles = ", ".join(user.preferences.target_roles)
        lines.append(_line("ok", f"Profile: {profile_path} (target roles: {roles})"))

    # ---- API keys (they depend on the models, so they need a valid config)
    if settings is None:
        lines.append(_line("skipped", "API keys: can't be checked until the config is valid"))
    else:
        for check in check_keys(settings):
            what = f"{check['name']} ({check['needed_by']})"
            if check["status"] == "found":
                lines.append(_line("ok", f"{what}: found"))
            elif check["status"] == "missing":
                problems += 1
                lines.append(_line("problem", f"{what}: MISSING, add it to your .env file"))
            else:
                lines.append(_line("unknown", f"{what}: can't be checked here"))

    return SetupReport(lines=lines, problems=problems)
