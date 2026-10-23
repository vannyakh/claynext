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
    "voice_training_enabled",
    "khmer_spoken_enabled",
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
        "hint": "Apple Silicon stem isolation (vocals / music / effects).",
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
        "hint": "Local speech with openbmb/VoxCPM2.",
        "detect": _detect_voxcpm,
        "supported": torch_wheels_available,
    },
    {
        "id": "omnivoice",
        "label": "OmniVoice",
        "category": "tts",
        "extra": "omnivoice",
        "hint": "Local speech with k2-fsa/OmniVoice.",
        "detect": _detect_omnivoice,
        "supported": torch_wheels_available,
    },
    {
        "id": "whisperx",
        "label": "WhisperX + diarization",
        "category": "asr",
        "extra": "whisperx",
        "hint": "Aligned ASR with speaker diarization.",
        "detect": _detect_whisperx,
        "supported": torch_wheels_available,
    },
    {
        "id": "gender_audio",
        "label": "Common-Voice Gender (ASR)",
        "category": "asr",
        "extra": "gender",
        "hint": "Wav2Vec2 audio gender for dub casting.",
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
        return "Stem bed · Demucs required · Settings → Features → Install all missing"
    return "Stem bed · FFmpeg fallback · Settings → Features → Install all missing"


def save_feature_defaults() -> None:
    """Write DEFAULT_CONFIG feature keys into the studio store."""
    for key in FEATURE_SETTING_KEYS:
        set_feature_setting(key, str(DEFAULT_CONFIG.get(key, "")))


# One uv sync at a time. Parallel syncs rewrite the same environment and fail.
_UV_SYNC = threading.Lock()


# Studio prefs an optional extra is allowed to turn on. The value is applied
# only when DEFAULT_CONFIG already enables that key. Burned-in caption OCR
# (transcript_ocr) and Prefer VoxCPM (prefer_voxcpm) stay opt-in.
_EXTRA_BACKED_PREFS: dict[str, str] = {
    "whisperx": "prefer_whisperx",
}


def dev_environment_extras() -> list[str]:
    """Optional extras this machine can install, in registry order.

    Names come from ``pyproject.toml`` optional-dependencies and the feature
    registry. Unsupported extras (for example Demucs MLX off Apple Silicon)
    are left out.
    """
    declared = declared_extras()
    ordered: list[str] = []
    for item in FEATURE_REGISTRY:
        extra_name = str(item.get("extra") or "")
        if not extra_name or extra_name in ordered or extra_name not in declared:
            continue
        try:
            supported = bool(item["supported"]())
        except Exception:
            supported = False
        if not supported:
            continue
        ordered.append(extra_name)
    return ordered


def format_uv_sync_command(extras: list[str]) -> str:
    """``uv sync --inexact`` with every extra that should stay installed.

    Syncing one extra on its own removes the other extras from the environment.
    """
    parts = ["uv", "sync", "--inexact"]
    for name in extras:
        parts.extend(["--extra", name])
    return " ".join(parts)


def dev_environment_sync_command() -> str:
    """Install command for the full optional development environment."""
    return format_uv_sync_command(dev_environment_extras())


def missing_dev_extras() -> list[str]:
    """Supported extras that are not importable yet."""
    missing: list[str] = []
    for extra in dev_environment_extras():
        status = feature_for_extra(extra)
        if status and status.get("supported") and not status.get("installed"):
            missing.append(extra)
    return missing


def dev_environment_preference_keys() -> dict[str, str]:
    """Safe prefs a full-environment install may turn on.

    A key is included only when the project default is already on and an
    installable extra backs it. Off-by-default flags are omitted.
    """
    supported = set(dev_environment_extras())
    updates: dict[str, str] = {}
    for extra, key in _EXTRA_BACKED_PREFS.items():
        if extra not in supported:
            continue
        default = str(DEFAULT_CONFIG.get(key, "0"))
        if default != "1":
            continue
        updates[key] = "1"
    return updates


def apply_dev_environment_preferences(installed: list[str] | None = None) -> dict[str, str]:
    """Turn on safe, default-on prefs for extras that are actually installed.

    Reads each current setting first. Does not enable burned-in caption OCR
    or Prefer VoxCPM. Stem mode is left as saved; Auto already uses Demucs
    when that extra is present.
    """
    present = set(installed if installed is not None else dev_environment_extras())
    applied: dict[str, str] = {}
    for extra, key in _EXTRA_BACKED_PREFS.items():
        if extra not in present:
            continue
        if key not in dev_environment_preference_keys():
            continue
        status = feature_for_extra(extra)
        if not status or not status.get("installed"):
            continue
        value = dev_environment_preference_keys()[key]
        current = get_feature_setting(key, str(DEFAULT_CONFIG.get(key, "0")))
        if current == value:
            continue
        set_feature_setting(key, value)
        applied[key] = value
    return applied


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


def _uv_binary() -> str:
    import shutil

    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv was not found on PATH. Install uv, then try again.")
    return uv


def _report_progress(progress_callback, pct: int, msg: str) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(max(0, min(100, int(pct))), str(msg or ""))
    except Exception:
        pass


def _refresh_import_state() -> None:
    import importlib

    importlib.invalidate_caches()


def _uv_sync_locked(uv: str, extras: list[str], progress_callback, *, label: str) -> dict[str, Any]:
    """Run one ``uv sync --inexact`` for ``extras``. Caller holds ``_UV_SYNC``."""
    import os
    import re
    import subprocess

    from claynext.utils.paths import BASE_DIR

    if not extras:
        raise ValueError("No extras to install")

    _report_progress(progress_callback, 4, f"Starting {label}…")
    cmd = [uv, "sync", "--inexact"]
    for name in extras:
        cmd.extend(["--extra", name])
    from claynext.utils.process_env import child_environ

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
        env=child_environ(),
    )
    assert proc.stdout is not None
    lines = 0
    last_msg = f"Installing {label}…"
    ansi = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    pct_re = re.compile(r"(\d{1,3})\s*%")
    for raw in proc.stdout:
        line = ansi.sub("", raw).strip()
        if not line:
            continue
        lines += 1
        last_msg = line[:160]
        pct = min(92, 8 + lines)
        match = pct_re.search(line)
        if match:
            pct = max(pct, min(95, int(match.group(1))))
        _report_progress(progress_callback, pct, last_msg)

    code = proc.wait()
    command = format_uv_sync_command(extras)
    if code != 0:
        raise RuntimeError(f"{command} failed (exit {code}): {last_msg}")
    remember_extras(extras)
    _refresh_import_state()
    return {
        "ok": True,
        "kept": list(extras),
        "command": command,
        "failed": [],
        "still_missing": [],
    }


def _install_extras_best_effort(
    uv: str,
    extras: list[str],
    progress_callback,
) -> dict[str, Any]:
    """Install extras one at a time after a combined sync fails. Lock is held."""
    have: list[str] = []
    for extra in extras:
        status = feature_for_extra(extra)
        if status and status.get("installed"):
            have.append(extra)
    failed: list[dict[str, str]] = []
    for extra in extras:
        if extra in have:
            continue
        try:
            _uv_sync_locked(uv, have + [extra], progress_callback, label=extra)
            have.append(extra)
        except RuntimeError as exc:
            failed.append({"extra": extra, "error": str(exc)})
    return {
        "ok": not failed,
        "kept": have,
        "failed": failed,
        "command": format_uv_sync_command(extras),
        "still_missing": [item["extra"] for item in failed],
    }


def _finish_install_result(
    result: dict[str, Any],
    *,
    apply_preferences: bool,
) -> dict[str, Any]:
    _refresh_import_state()
    still = missing_dev_extras()
    failed = list(result.get("failed") or [])
    known = {str(item.get("extra") or "") for item in failed}
    for name in still:
        if name in known:
            continue
        failed.append({
            "extra": name,
            "error": f"{name} is still not importable after install.",
        })
    result["failed"] = failed
    result["still_missing"] = still
    result["ok"] = not failed
    installed = [name for name in result.get("kept") or [] if name not in set(still)]
    result["applied_preferences"] = (
        apply_dev_environment_preferences(installed) if apply_preferences else {}
    )
    return result


def install_uv_extra(extra: str, progress_callback=None) -> dict[str, Any]:
    """
    Install one extra and keep every tool that is already installed.

    ``uv sync --extra`` alone removes the other extras, so each Install click
    undoes the last one. ``--inexact`` plus the saved extra list installs once.
    """
    extra = (extra or "").strip()
    if not extra:
        raise ValueError("Missing uv extra name")
    for item in FEATURE_REGISTRY:
        if extra in {item["id"], item["extra"]} and not bool(item["supported"]()):
            raise RuntimeError(_unsupported_reason(item["id"]))

    uv = _uv_binary()
    _report_progress(progress_callback, 2, f"Waiting to install {extra}…")
    with _UV_SYNC:
        keep = retained_extras(extra)
        result = _uv_sync_locked(uv, keep, progress_callback, label=extra)
    _report_progress(progress_callback, 100, "Installed")
    result["extra"] = extra
    return result


def install_dev_environment(progress_callback=None, *, apply_preferences: bool = True) -> dict[str, Any]:
    """Install every supported optional extra in one ``uv sync --inexact``.

    The command lists every extra that should stay installed, including ones
    that are already present. If one extra cannot resolve, the rest are
    installed one at a time and the failure is returned on ``failed``.
    """
    extras = dev_environment_extras()
    if not extras:
        raise RuntimeError("This platform cannot install the optional development extras.")
    command = format_uv_sync_command(extras)
    if not missing_dev_extras():
        result = _finish_install_result(
            {
                "ok": True,
                "kept": extras,
                "command": command,
                "failed": [],
                "still_missing": [],
            },
            apply_preferences=apply_preferences,
        )
        _report_progress(progress_callback, 100, "Installed")
        return result

    uv = _uv_binary()
    _report_progress(progress_callback, 2, "Waiting to install the development environment…")
    with _UV_SYNC:
        extras = dev_environment_extras()
        command = format_uv_sync_command(extras)
        try:
            result = _uv_sync_locked(
                uv, extras, progress_callback, label="development environment",
            )
        except RuntimeError:
            result = _install_extras_best_effort(uv, extras, progress_callback)
        result["command"] = command
    result = _finish_install_result(result, apply_preferences=apply_preferences)
    if result.get("ok"):
        _report_progress(progress_callback, 100, "Installed")
    else:
        _report_progress(progress_callback, 100, "Installed with gaps")
    return result

