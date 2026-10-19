"""Project data paths. Importing this module creates the directories."""
from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repo root when running from source, otherwise the nearest parent with pyproject.toml."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "claynext").is_dir():
            return parent
    return here.parents[3]


BASE_DIR = project_root()
APP_DIR = BASE_DIR
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
OUTPUTS_DIR = DATA_DIR / "outputs"
CACHE_DIR = DATA_DIR / "cache"
PLAYBACK_DIR = CACHE_DIR / "playback"
PROXY_DIR = CACHE_DIR / "proxies"
THUMB_DIR = CACHE_DIR / "thumbnails"
STUDIO_CACHE = CACHE_DIR / "studio"
# Alias kept for older call sites (pipeline work dir).
DUB_CACHE = STUDIO_CACHE
PRESET_DIR = DATA_DIR / "presets" / "studio"
PROJECT_DIR = DATA_DIR / "projects"
VOICEOVER_DIR = PROJECT_DIR / "voiceover"
LOGS_DIR = DATA_DIR / "logs"
FONT_DIR = DATA_DIR / "fonts" / "google"

DATA_DIRS = (
    DATA_DIR,
    MODELS_DIR,
    OUTPUTS_DIR,
    CACHE_DIR,
    PLAYBACK_DIR,
    PROXY_DIR,
    THUMB_DIR,
    STUDIO_CACHE,
    PRESET_DIR,
    PROJECT_DIR,
    VOICEOVER_DIR,
    LOGS_DIR,
    FONT_DIR,
)


def ensure_data_dirs() -> None:
    for folder in DATA_DIRS:
        folder.mkdir(parents=True, exist_ok=True)


ensure_data_dirs()
