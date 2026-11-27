"""Where the user's data lives. Shared by the graph and the UI."""

from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PROFILE_PATH = DATA_DIR / "profile.json"
CONFIG_PATH = DATA_DIR / "config.toml"
