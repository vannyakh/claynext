"""
Optional Claynext studio features (uv extras) and persisted studio prefs.

Registry covers Demucs / Demucs-MLX stem beds, VoxCPM2, OmniVoice, and WhisperX ASR.
Settings live under Store tool ``studio``.
"""
from __future__ import annotations

import importlib.util
import platform
import threading
from typing import Any

from claynext.utils.config import DEFAULT_CONFIG

STUDIO_TOOL = "studio"

FEATURE_SETTING_KEYS = (
    "stem_separation",
    "demucs_model",
    "prefer_voxcpm",
    "prefer_whisperx",
    "transcript_ocr",
    "sglang_omni_url",
    "skill_dialogue_translation",
    "skill_khmer_natural_dialogue",
)

STEM_MODES = ("auto", "demucs", "ffmpeg")
DEMUCS_MODELS = (
    "htdemucs",
    "htdemucs_ft",
    "htdemucs_6s",
    "hdemucs_mmi",
)


def _package_present(name: str) -> bool:
    """True when the tool is already in this environment. Does not import it."""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _detect_demucs_mlx() -> bool:
    return _package_present("demucs_mlx")


def _detect_demucs() -> bool:
    return _package_present("demucs")


def _detect_voxcpm() -> bool:
    return _package_present("voxcpm")


def _detect_omnivoice() -> bool:
    return _package_present("omnivoice")


def _detect_whisperx() -> bool:
    return _package_present("whisperx")


def _detect_gender_audio() -> bool:
    # The gender extra is torch. Transformers is already part of Studio.
    return _package_present("torch") and _package_present("transformers")


def _mlx_platform_ok() -> bool:
    from claynext.models.stem_separation import demucs_mlx_supported
    return demucs_mlx_supported()


def torch_wheels_available() -> bool:
    """PyTorch 2.4+ has wheels for Apple Silicon, Windows, and Linux, not Intel macOS."""
    if platform.system() == "Darwin" and platform.machine().lower() in {"x86_64", "amd64", "i386"}:
        return False
    return True


def _detect_audio_separator() -> bool:
    try:
        from claynext.models.stem_separation import separator_available
        return separator_available()
    except Exception:
        return False


def declared_extras() -> set[str]:
    """Optional groups this project can actually install."""
    try:
        import tomllib

        from claynext.utils.paths import BASE_DIR

        with open(BASE_DIR / "pyproject.toml", "rb") as handle:
            data = tomllib.load(handle)
        groups = (data.get("project") or {}).get("optional-dependencies") or {}
        return {str(name) for name in groups}
    except Exception:
        return {str(item["extra"]) for item in FEATURE_REGISTRY}


def _extra_installable(extra: str) -> bool:
    return extra in declared_extras()


def _audio_separator_supported() -> bool:
    """UVR is not a compatible extra beside the Demucs torch pin."""
    return torch_wheels_available() and _extra_installable("audio-separator")


def _unsupported_reason(feature_id: str) -> str:
    if feature_id == "demucs_mlx":
        return "Apple Silicon only. Demucs (PyTorch) is the cross-platform stem tool."
    if feature_id == "audio_separator":
        return "Use Demucs. It is the compatible stem tool on macOS, Windows, and Linux."
    if not torch_wheels_available():
        return "PyTorch has no Intel macOS build, so this feature cannot be installed here."
    return "This platform cannot install this feature."


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
        "hint": "Cross-platform stem tool for macOS, Windows, and Linux. Installs once.",
        "detect": _detect_demucs,
        "supported": torch_wheels_available,
    },
    {
        "id": "audio_separator",
        "label": "Audio Separator (UVR)",
        "category": "audio",
        "extra": "audio-separator",
        "hint": "Use Demucs. It is the compatible stem tool on macOS, Windows, and Linux.",
        "detect": _detect_audio_separator,
        "supported": _audio_separator_supported,
    },
    {
        "id": "voxcpm",
        "label": "VoxCPM2",
        "category": "tts",
        "extra": "voxcpm",
        "hint": "Local speech with openbmb/VoxCPM2. uv sync --extra voxcpm",
        "detect": _detect_voxcpm,
        "supported": torch_wheels_available,
    },
    {
        "id": "omnivoice",
        "label": "OmniVoice",
        "category": "tts",
        "extra": "omnivoice",
        "hint": "Local speech with k2-fsa/OmniVoice. uv sync --extra omnivoice",
        "detect": _detect_omnivoice,
        "supported": torch_wheels_available,
    },
    {
        "id": "whisperx",
        "label": "WhisperX + diarization",
        "category": "asr",
        "extra": "whisperx",
        "hint": "Aligned ASR with speaker diarization. uv sync --extra whisperx",
        "detect": _detect_whisperx,
        "supported": torch_wheels_available,
    },
    {
        "id": "gender_audio",
        "label": "Common-Voice Gender (ASR)",
        "category": "asr",
        "extra": "gender",
        "hint": "Wav2Vec2 audio gender for dub casting. uv sync --extra gender",
        "detect": _detect_gender_audio,
        "supported": torch_wheels_available,
    },
]


def list_features() -> list[dict[str, Any]]:
    """Return registry entries (without callables), each with live status fields."""
    return [feature_status(item["id"]) for item in FEATURE_REGISTRY]


def feature_for_extra(extra: str) -> dict[str, Any] | None:
    """Status of the feature that owns a uv extra name, if one is registered."""
    key = (extra or "").strip()
    if not key:
        return None
    for item in FEATURE_REGISTRY:
        if item["extra"] == key or item["id"] == key:
            return feature_status(item["id"])
    return None


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
    hint = item["hint"] if supported else _unsupported_reason(item["id"])
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
        "hint": hint,
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


def transcript_ocr_enabled() -> bool:
    """Burned-in caption check before speech transcription. Off keeps normal ASR."""
    return get_feature_setting("transcript_ocr", "0") == "1"


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
    if backend == "separator":
        return "Stem bed · UVR vocals / effects"
    if mode == "demucs":
        return "Stem bed · Demucs required · uv sync --extra demucs-mlx or demucs"
    return "Stem bed · FFmpeg fallback · uv sync --extra demucs-mlx or demucs"


def save_feature_defaults() -> None:
    """Write DEFAULT_CONFIG feature keys into the studio store."""
    for key in FEATURE_SETTING_KEYS:
        set_feature_setting(key, str(DEFAULT_CONFIG.get(key, "")))


# One uv sync at a time. Parallel syncs rewrite the same environment and fail.
_UV_SYNC = threading.Lock()


def retained_extras(include: str = "") -> list[str]:
    """Extras to keep. A new install must not remove tools that are already ready."""
    names: set[str] = set()
    saved = get_feature_setting("installed_extras", "")
    for part in str(saved or "").split(","):
        part = part.strip()
        if part:
            names.add(part)
    for item in FEATURE_REGISTRY:
        if not bool(item["supported"]()):
            continue
        try:
            if item["detect"]():
                names.add(str(item["extra"]))
        except Exception:
            pass
    if include:
        names.add(include.strip())
    declared = declared_extras()
    ordered: list[str] = []
    for item in FEATURE_REGISTRY:
        extra_name = str(item["extra"])
        if extra_name in names and extra_name in declared and extra_name not in ordered:
            ordered.append(extra_name)
    if include and include not in ordered and include in declared:
        ordered.append(include)
    return ordered


def remember_extras(extras: list[str]) -> None:
    declared = declared_extras()
    names = [name for name in extras if name in declared]
    set_feature_setting("installed_extras", ",".join(names))


def install_uv_extra(extra: str, progress_callback=None) -> dict[str, Any]:
    """
    Install one extra and keep every tool that is already installed.

    ``uv sync --extra`` alone removes the other extras, so each Install click
    undoes the last one. ``--inexact`` plus the saved extra list installs once.
    """
    import os
    import re
    import shutil
    import subprocess

    from claynext.utils.paths import BASE_DIR

    extra = (extra or "").strip()
    if not extra:
        raise ValueError("Missing uv extra name")
    for item in FEATURE_REGISTRY:
        if extra in {item["id"], item["extra"]} and not bool(item["supported"]()):
            raise RuntimeError(_unsupported_reason(item["id"]))

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

    _progress(2, f"Waiting to install {extra}…")
    with _UV_SYNC:
        keep = retained_extras(extra)
        _progress(4, f"Starting {extra}…")
        cmd = [uv, "sync", "--inexact"]
        for name in keep:
            cmd.extend(["--extra", name])
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
            pct = min(92, 8 + lines * 3)
            m = pct_re.search(line)
            if m:
                pct = max(pct, min(95, int(m.group(1))))
            _progress(pct, last_msg)

        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"uv sync --extra {extra} failed (exit {code}): {last_msg}")
        remember_extras(keep)
    _progress(100, "Installed")
    return {"extra": extra, "ok": True, "kept": keep}

