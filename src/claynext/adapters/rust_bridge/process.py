"""Shared helpers for locating and invoking Claynext Rust backend binaries."""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from claynext.utils.paths import BASE_DIR

logger = logging.getLogger("claynext.adapters.rust")

BACKENDS_DIR = BASE_DIR / "backends"
TARGET_DIR = BASE_DIR / "target" / "debug"
RELEASE_TARGET_DIR = BASE_DIR / "target" / "release"
LEGACY_TARGET_DIR = BACKENDS_DIR / "target" / "debug"
LEGACY_RELEASE_TARGET_DIR = BACKENDS_DIR / "target" / "release"


def _find_binary(bin_name: str) -> Path | None:
    ext = ".exe" if os.name == "nt" else ""
    full_name = f"{bin_name}{ext}"
    dirs: list[Path] = [RELEASE_TARGET_DIR, TARGET_DIR, LEGACY_RELEASE_TARGET_DIR, LEGACY_TARGET_DIR]
    # Honour cargo target override (CI / sandboxed builds).
    cargo_target = os.environ.get("CARGO_TARGET_DIR")
    if cargo_target:
        root = Path(cargo_target)
        dirs = [root / "release", root / "debug", *dirs]
    for candidate_dir in dirs:
        p = candidate_dir / full_name
        if p.is_file():
            return p
    return None


def _ensure_bundled_ffmpeg_env() -> None:
    """Point the Rust FFmpeg backend at imageio-ffmpeg when system PATH has no ffmpeg."""
    if os.environ.get("CLAYNEXT_FFMPEG_PATH"):
        return
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            os.environ["CLAYNEXT_FFMPEG_PATH"] = exe
            # ffprobe is optional; probe falls back to ffmpeg -i when missing.
    except Exception:
        pass


def _run_rust(
    binary: Path,
    args: list[str],
    *,
    timeout: float | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    _ensure_bundled_ffmpeg_env()
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
        timeout=timeout,
        creationflags=creationflags,
    )


