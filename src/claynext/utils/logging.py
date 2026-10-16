"""Console logging for Claynext CLI tools."""
from __future__ import annotations

import logging
import sys


def configure_logging(name: str = "claynext") -> logging.Logger:
    """Attach one stdout handler. Safe to call more than once."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    return logging.getLogger(name)
