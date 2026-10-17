"""Console + rotating file logging for Claynext (CLI and Studio)."""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from claynext.utils.paths import LOGS_DIR, ensure_data_dirs

_CONFIGURED = False
_SESSION_LOG: Path | None = None


def session_log_path() -> Path:
    """Path of today's session log file (created on first configure)."""
    global _SESSION_LOG
    if _SESSION_LOG is None:
        ensure_data_dirs()
        stamp = datetime.now().strftime("%Y%m%d")
        _SESSION_LOG = LOGS_DIR / f"claynext-{stamp}.log"
    return _SESSION_LOG


def configure_logging(name: str = "claynext", *, level: int = logging.INFO) -> logging.Logger:
    """
    Attach stdout + rotating file handlers once.
    File lives in data/logs/claynext-YYYYMMDD.log for issue tracking.
    """
    global _CONFIGURED
    root = logging.getLogger()
    if not _CONFIGURED:
        ensure_data_dirs()
        root.setLevel(level)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        stream.setLevel(level)
        root.addHandler(stream)

        log_path = session_log_path()
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

        _CONFIGURED = True
        logging.getLogger("claynext").info("Logging to %s", log_path)

    return logging.getLogger(name)


def install_exception_logging() -> None:
    """Write uncaught exceptions to the session log (keep default stderr too)."""
    configure_logging()
    prev = sys.excepthook

    def _hook(exc_type, exc, tb):
        logging.getLogger("claynext").exception(
            "Uncaught exception",
            exc_info=(exc_type, exc, tb),
        )
        if prev is not None and prev is not sys.__excepthook__:
            prev(exc_type, exc, tb)
        else:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
