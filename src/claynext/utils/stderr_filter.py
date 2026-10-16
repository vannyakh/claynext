"""Filter benign FFmpeg / Media Foundation probe noise on Windows stderr."""
from __future__ import annotations

import os
import sys
import threading
from typing import TextIO

# Qt Multimedia's FFmpeg backend probes h264_mf / hevc_mf at startup.
# Many PCs have H.264 MF but no HEVC MF — FFmpeg then prints ERROR lines that
# look like failures even though the app falls back cleanly.
_DROP_FRAGMENTS = (
    b"hevc_mf @",
    b"could not find any MFT for the given media type",
    b"could not create MFT",
    b"[h264_mf @",  # informational "MFT name: 'H264 Encoder MFT'"
)

_installed = False
_real_stderr_fd: int | None = None


def _should_drop(line: bytes) -> bool:
    return any(frag in line for frag in _DROP_FRAGMENTS)


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
                    if not _should_drop(line):
                        os.write(write_fd, line)
            if buf and not _should_drop(buf):
                os.write(write_fd, buf)
    except Exception:
        pass


class _FilteredTextIO:
    """Python-level stderr filter (complements the OS fd pump)."""

    def __init__(self, real: TextIO):
        self._real = real

    def write(self, s: str) -> int:
        if not s:
            return 0
        data = s.encode("utf-8", errors="replace") if isinstance(s, str) else s
        if _should_drop(data if isinstance(data, bytes) else str(data).encode()):
            return len(s)
        # Drop only matching lines when multi-line batches arrive.
        if "\n" in s:
            kept = [ln for ln in s.splitlines(keepends=True) if not _should_drop(ln.encode("utf-8", "replace"))]
            if not kept:
                return len(s)
            return self._real.write("".join(kept))
        return self._real.write(s)

    def flush(self) -> None:
        self._real.flush()

    def fileno(self) -> int:
        return self._real.fileno()

    def isatty(self) -> bool:
        return self._real.isatty()

    def __getattr__(self, name: str):
        return getattr(self._real, name)


def install_ffmpeg_mf_stderr_filter() -> None:
    """Install once before QApplication — hides missing HEVC MF probe noise."""
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
