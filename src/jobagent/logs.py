"""Logging for the whole app.

Everything the pipeline reports goes through the standard `logging` module, under the
logger name "jobagent". Each module gets its own logger with get_logger(__name__).

setup_logging() sends the messages to two places:
  - the console (stderr), at INFO: the counts and the warnings. `docker logs` shows this.
  - a rotating file, data/logs/jobagent.log, at DEBUG: the same, plus one line for every
    rejected job and the traceback of a crash.

Levels used by the pipeline:
  INFO     what each step did, in numbers
  WARNING  something failed but the run goes on (a search, a page, one job)
  DEBUG    detail: every query, every rejected job and why
  ERROR    the run stopped
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from paths import LOG_DIR

ROOT_NAME = "jobagent"
LOG_FILE_NAME = "jobagent.log"
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_FILE_BYTES = 1_000_000  # the file is rotated when it reaches this size
BACKUP_FILES = 5  # jobagent.log.1 ... jobagent.log.5 are kept; the oldest is deleted

_configured_with: tuple[int, Path] | None = None


def get_logger(name: str) -> logging.Logger:
    """The logger of a module: `log = get_logger(__name__)`."""
    return logging.getLogger(f"{ROOT_NAME}.{name}")


def _remove_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def setup_logging(console_level: int = logging.INFO, log_dir: Path | str | None = None) -> None:
    """Send the app's log to the console and to a rotating file. Safe to call again.

    Calling it again with the same arguments does nothing, so the Streamlit app can call it
    on every rerun without piling up handlers.
    """
    global _configured_with
    log_dir = Path(log_dir) if log_dir is not None else LOG_DIR
    if _configured_with == (console_level, log_dir):
        return

    logger = logging.getLogger(ROOT_NAME)
    _remove_handlers(logger)
    logger.setLevel(logging.DEBUG)  # the handlers below decide what is shown
    logger.propagate = False  # we handle it here: don't also print it through the root logger
    formatter = logging.Formatter(FORMAT, DATE_FORMAT)

    console = logging.StreamHandler()  # stderr
    console.setLevel(console_level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / LOG_FILE_NAME,
            maxBytes=MAX_FILE_BYTES,
            backupCount=BACKUP_FILES,
            encoding="utf-8",
        )
    except OSError as e:  # e.g. a folder we may not write to: the run must not depend on it
        logger.warning("Could not open the log file in %s (%s). Logging to the console only.",
                       log_dir, e)
    else:
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _configured_with = (console_level, log_dir)


def reset_logging() -> None:
    """Undo setup_logging(). Used by the tests."""
    global _configured_with
    logger = logging.getLogger(ROOT_NAME)
    _remove_handlers(logger)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    _configured_with = None


def log_rejected(log: logging.Logger, rejected: list) -> None:
    """One DEBUG line for each rejected job, with the reason. `rejected` holds RejectedHit."""
    for item in rejected:
        log.debug("rejected: %s (%s)", item.hit.title, item.reason)
