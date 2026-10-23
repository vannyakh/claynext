"""Filter benign stderr: codec probes, malloc-stack noise, and tqdm bars."""
from __future__ import annotations

import os
import sys
import threading
from typing import TextIO

from claynext.utils.console_noise import sanitize_console_bytes, sanitize_console_text

_installed = False
_real_stderr_fd: int | None = None


def _pump_filtered(read_fd: int, write_fd: int) -> None:
    try:
        with os.fdopen(read_fd, "rb", closefd=True) as pipe:
            buf = b""
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line += b"\n"
                    kept = sanitize_console_bytes(line)
                    if kept:
                        os.write(write_fd, kept)
            if buf:
                kept = sanitize_console_bytes(buf)
                if kept:
                    os.write(write_fd, kept)
    except Exception:
        pass


class _FilteredTextIO:
    """Python-level stderr filter (complements the OS fd pump)."""

    def __init__(self, real: TextIO):
        self._real = real

    def write(self, s: str) -> int:
        if not s:
            return 0
        text = s if isinstance(s, str) else s.decode("utf-8", "replace")
        cleaned = sanitize_console_text(text)
        if not cleaned:
            return len(s)
        return self._real.write(cleaned)

    def flush(self) -> None:
        self._real.flush()

    def fileno(self) -> int:
        return self._real.fileno()

    def isatty(self) -> bool:
        return self._real.isatty()

    def __getattr__(self, name: str):
        return getattr(self._real, name)


def install_ffmpeg_mf_stderr_filter() -> None:
    """Install once before QApplication.

    Hides missing HEVC probe lines, the macOS malloc-stack warning, and raw
    tqdm meters. Library progress is reported through the job status callback.
    """
    global _installed, _real_stderr_fd
    if _installed:
        return
    _installed = True

    # Soften Qt's own FFmpeg category chatter when unset by the user.
    os.environ.setdefault(
        "QT_LOGGING_RULES",
        "qt.multimedia.ffmpeg.debug=false;qt.multimedia.ffmpeg.info=false",
    )

    try:
        sys.stderr = _FilteredTextIO(sys.stderr)  # type: ignore[assignment]
    except Exception:
        pass

    # FFmpeg (inside Qt) writes via C stderr (fd 2), bypassing sys.stderr.
    try:
        r_fd, w_fd = os.pipe()
        _real_stderr_fd = os.dup(2)
        os.dup2(w_fd, 2)
        os.close(w_fd)
        thread = threading.Thread(
            target=_pump_filtered,
            args=(r_fd, _real_stderr_fd),
            name="claynext-stderr-filter",
            daemon=True,
        )
        thread.start()
    except Exception:
        # Console redirect unavailable (e.g. some frozen builds) — Python filter still helps.
        pass

    # After the filter is up, so unsetting the variable cannot print the warning.
    try:
        from claynext.utils.library_progress import install_quiet_tqdm
        from claynext.utils.process_env import scrub_malloc_stack_logging

        scrub_malloc_stack_logging()
        install_quiet_tqdm()
    except Exception:
        pass
