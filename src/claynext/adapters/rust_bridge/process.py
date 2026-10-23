"""Shared helpers for locating and invoking Claynext Rust backend binaries."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

from claynext.utils.paths import BASE_DIR
from claynext.utils.process_env import child_environ

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
        env=child_environ(),
    )


def _run_rust_stream(
    binary: Path,
    args: list[str],
    on_line,
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a Rust CLI and deliver each stdout line as it is written.

    Export and mux print JSON progress lines. stderr is drained on a side
    thread so a long encode cannot stall on a full pipe.
    """
    _ensure_bundled_ffmpeg_env()
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        [str(binary), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
        env=child_environ(),
    )
    stderr_parts: list[str] = []

    def _drain_stderr() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            stderr_parts.append(line)

    thread = threading.Thread(target=_drain_stderr, daemon=True)
    thread.start()
    stdout_parts: list[str] = []
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                stdout_parts.append(line)
                try:
                    on_line(line)
                except Exception:
                    logger.debug("progress line handler failed", exc_info=True)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        raise
    finally:
        thread.join(timeout=2)
    return subprocess.CompletedProcess(
        [str(binary), *args],
        proc.returncode if proc.returncode is not None else 1,
        "".join(stdout_parts),
        "".join(stderr_parts),
    )


