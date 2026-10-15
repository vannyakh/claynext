"""Application identity and default studio settings."""
from __future__ import annotations

import os

from claynext.utils.paths import (
    BASE_DIR,
    CACHE_DIR,
    DATA_DIR,
    DUB_CACHE,
    LOGS_DIR,
    MODELS_DIR,
    OUTPUTS_DIR,
    PLAYBACK_DIR,
    PRESET_DIR,
    PROJECT_DIR,
    PROXY_DIR,
    STUDIO_CACHE,
    THUMB_DIR,
    VOICEOVER_DIR,
    ensure_data_dirs,
)

APP_NAME = "Claynext Studio"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Claynext"

DEFAULT_CONFIG = {
    "theme": "Dark Cyber",
    "device": "CPU Threadpool (Fallback)",
    "asr_model": "whisper-medium",
    "tts_model": "qwen-tts-v1",
    "ocr_engine": "easyocr-multilingual",
    "translate_engine": "nmt-v2",
    "whisper_language": "Auto Detect",
    "save_directory": str(OUTPUTS_DIR),
    "models_directory": str(MODELS_DIR),
    # Studio optional features (Store tool "studio")
    "stem_separation": "auto",  # auto | demucs | ffmpeg
    "demucs_model": "htdemucs",
    "prefer_voxcpm": "0",
    "prefer_whisperx": "1",
    "ui_language": "English (US)",
    "check_updates": "1",
    "auto_open_exports": "1",
    "keep_awake": "1",
    "notify_on_complete": "1",
    "worker_threads": "4",
    "ui_animations": "1",
    "accent": "Indigo / Purple (#6366f1)",
}

__all__ = [
    "APP_AUTHOR",
    "APP_NAME",
    "APP_VERSION",
    "BASE_DIR",
    "CACHE_DIR",
    "DATA_DIR",
    "DEFAULT_CONFIG",
    "DUB_CACHE",
    "LOGS_DIR",
    "MODELS_DIR",
    "OUTPUTS_DIR",
    "PLAYBACK_DIR",
    "PRESET_DIR",
    "PROJECT_DIR",
    "PROXY_DIR",
    "STUDIO_CACHE",
    "THUMB_DIR",
    "VOICEOVER_DIR",
    "ensure_data_dirs",
]


def _default_device() -> str:
    if os.environ.get("CUDA_VISIBLE_DEVICES", "").strip():
        return "CUDA (NVIDIA GPU)"
    return DEFAULT_CONFIG["device"]


DEFAULT_CONFIG["device"] = _default_device()
