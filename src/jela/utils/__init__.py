"""Path helpers, studio defaults, and CLI logging."""
from jela.utils.config import APP_NAME, APP_VERSION, DEFAULT_CONFIG
from jela.utils.logging import configure_logging
from jela.utils.paths import (
    CACHE_DIR,
    DATA_DIR,
    MODELS_DIR,
    OUTPUTS_DIR,
    PLAYBACK_DIR,
    ensure_data_dirs,
)

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "CACHE_DIR",
    "DATA_DIR",
    "DEFAULT_CONFIG",
    "MODELS_DIR",
    "OUTPUTS_DIR",
    "PLAYBACK_DIR",
    "configure_logging",
    "ensure_data_dirs",
]
