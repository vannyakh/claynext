"""
Optional Claynext studio features (uv extras) and persisted studio prefs.

Registry covers Demucs / Demucs-MLX stem beds, VoxCPM TTS, and WhisperX ASR.
Settings live under Store tool ``studio``.
"""
from __future__ import annotations

from typing import Any

from claynext.utils.config import DEFAULT_CONFIG

STUDIO_TOOL = "studio"

FEATURE_SETTING_KEYS = (
    "stem_separation",
    "demucs_model",
    "prefer_voxcpm",
    "prefer_whisperx",
)

STEM_MODES = ("auto", "demucs", "ffmpeg")
DEMUCS_MODELS = (
    "htdemucs",
    "htdemucs_ft",
    "htdemucs_6s",
    "hdemucs_mmi",
)


def _detect_demucs_mlx() -> bool:
    try:
        import demucs_mlx  # noqa: F401
        return True
    except Exception:
        return False


def _detect_demucs() -> bool:
    try:
        import demucs.api  # noqa: F401
        return True
    except Exception:
        return False


def _detect_voxcpm() -> bool:
    try:
        from claynext.models.tts_service import TTSEngine
        return TTSEngine.voxcpm_available()
    except Exception:
        return False


def _detect_whisperx() -> bool:
    try:
        from claynext.models.dubbing_plan import whisperx_available
        return whisperx_available()
    except Exception:
        return False


def _detect_gender_audio() -> bool:
    try:
        from claynext.models.gender_audio import gender_model_available
        return gender_model_available()
    except Exception:
        return False


def _mlx_platform_ok() -> bool:
    from claynext.models.stem_separation import demucs_mlx_supported
    return demucs_mlx_supported()


FEATURE_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "demucs_mlx",
        "label": "Demucs MLX",
        "category": "audio",
        "extra": "demucs-mlx",
        "hint": "Apple Silicon stem isolation (vocals / music / effects). uv sync --extra demucs-mlx",
        "detect": _detect_demucs_mlx,
        "supported": _mlx_platform_ok,
    },
    {
        "id": "demucs",
        "label": "Demucs (PyTorch)",
        "category": "audio",
        "extra": "demucs",
        "hint": "Meta htdemucs stem separation. uv sync --extra demucs",
        "detect": _detect_demucs,
        "supported": lambda: True,
    },
    {
        "id": "voxcpm",
        "label": "VoxCPM TTS",
        "category": "tts",
        "extra": "voxcpm",
        "hint": "Local multilingual neural TTS. uv sync --extra voxcpm",
        "detect": _detect_voxcpm,
        "supported": lambda: True,
    },
    {
        "id": "whisperx",
        "label": "WhisperX + diarization",
        "category": "asr",
        "extra": "whisperx",
        "hint": "Aligned ASR with speaker diarization. uv sync --extra whisperx",
        "detect": _detect_whisperx,
        "supported": lambda: True,
    },
    {
        "id": "gender_audio",
        "label": "Common-Voice Gender (ASR)",
        "category": "asr",
        "extra": "gender",
        "hint": "Wav2Vec2 audio gender for dub casting. uv sync --extra gender",
        "detect": _detect_gender_audio,
        "supported": lambda: True,
    },
]


def list_features() -> list[dict[str, Any]]:
    """Return registry entries (without callables), each with live status fields."""
    return [feature_status(item["id"]) for item in FEATURE_REGISTRY]


def _entry(feature_id: str) -> dict[str, Any] | None:
    for item in FEATURE_REGISTRY:
        if item["id"] == feature_id:
            return item
    return None


def feature_status(feature_id: str) -> dict[str, Any]:
    """
    Status for one optional feature.

    Returns ``id``, ``label``, ``category``, ``extra``, ``hint``,
    ``installed``, ``supported``, ``status`` (Ready | Not installed | Unsupported).
    """
    item = _entry(feature_id)
    if item is None:
        return {
            "id": feature_id,
            "label": feature_id,
            "category": "",
            "extra": "",
            "hint": "",
            "installed": False,
            "supported": False,
            "status": "Unknown",
        }
    supported = bool(item["supported"]())
    installed = bool(item["detect"]()) if supported else False
    if not supported:
        status = "Unsupported"
    elif installed:
        status = "Ready"
    else:
        status = "Not installed"
    return {
        "id": item["id"],
        "label": item["label"],
        "category": item["category"],
        "extra": item["extra"],
        "hint": item["hint"],
        "installed": installed,
        "supported": supported,
        "status": status,
    }


def stem_backend() -> str | None:
    """Active Demucs backend: ``mlx``, ``torch``, or ``None``."""
    from claynext.models.stem_separation import backend_available
    return backend_available()


def get_feature_setting(key: str, default: str | None = None) -> str:
    from claynext.controllers.store import get_store

    if default is None:
        default = str(DEFAULT_CONFIG.get(key, ""))
    return get_store().get_setting(STUDIO_TOOL, key, default)


def set_feature_setting(key: str, value: str) -> None:
    from claynext.controllers.store import get_store

    get_store().set_setting(STUDIO_TOOL, key, str(value))


def stem_separation_mode() -> str:
    mode = (get_feature_setting("stem_separation") or "auto").strip().lower()
    return mode if mode in STEM_MODES else "auto"


def demucs_model_name() -> str:
    name = (get_feature_setting("demucs_model") or "htdemucs").strip()
    return name if name in DEMUCS_MODELS else "htdemucs"


def prefer_demucs_bed() -> bool:
    """True when settings allow Demucs for the music/effects bed."""
    mode = stem_separation_mode()
    if mode == "ffmpeg":
        return False
    if mode == "demucs":
        return stem_backend() is not None
    # auto
    return stem_backend() is not None


def stem_status_label() -> str:
    """Short UI line for Start Dub / Features."""
    mode = stem_separation_mode()
    backend = stem_backend()
    if mode == "ffmpeg":
        return "Stem bed · FFmpeg mid-side (forced)"
    if backend == "mlx":
        return f"Stem bed · Demucs MLX ({demucs_model_name()})"
    if backend == "torch":
        return f"Stem bed · Demucs {demucs_model_name()}"
    if mode == "demucs":
        return "Stem bed · Demucs required · uv sync --extra demucs-mlx or demucs"
    return "Stem bed · FFmpeg fallback · uv sync --extra demucs-mlx or demucs"


def save_feature_defaults() -> None:
    """Write DEFAULT_CONFIG feature keys into the studio store."""
    for key in FEATURE_SETTING_KEYS:
        set_feature_setting(key, str(DEFAULT_CONFIG.get(key, "")))


def install_uv_extra(extra: str, progress_callback=None) -> dict[str, Any]:
    """
    Run ``uv sync --extra <extra>`` from the project root (background-safe).

    ``progress_callback(percent: int, message: str)`` is optional.
    """
    import os
    import re
    import shutil
    import subprocess

    from claynext.utils.paths import BASE_DIR

    extra = (extra or "").strip()
    if not extra:
        raise ValueError("Missing uv extra name")

    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv was not found on PATH. Install uv, then try again.")

    def _progress(pct: int, msg: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(max(0, min(100, int(pct))), str(msg or ""))
        except Exception:
            pass

    _progress(2, f"Starting {extra}…")
    cmd = [uv, "sync", "--extra", extra]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    assert proc.stdout is not None
    lines = 0
    last_msg = f"Installing {extra}…"
    ansi = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    pct_re = re.compile(r"(\d{1,3})\s*%")
    for raw in proc.stdout:
        line = ansi.sub("", raw).strip()
        if not line:
            continue
        lines += 1
        last_msg = line[:120]
        pct = min(92, 4 + lines * 3)
        m = pct_re.search(line)
        if m:
            pct = max(pct, min(95, int(m.group(1))))
        _progress(pct, last_msg)

    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"uv sync --extra {extra} failed (exit {code}): {last_msg}")
    _progress(100, "Installed")
    return {"extra": extra, "ok": True}

