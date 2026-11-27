"""Where the user's data lives. Shared by the graph and the UI."""

from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PROFILE_PATH = DATA_DIR / "profile.json"
CONFIG_PATH = DATA_DIR / "config.toml"
DB_PATH = DATA_DIR / "jobs.db"  # the jobs and the run history
LOG_DIR = DATA_DIR / "logs"
