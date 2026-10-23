"""Drop known-benign console lines without hiding real errors."""
from __future__ import annotations

import re

# Exact libmalloc sentence. A different malloc message stays visible.
_MALLOC_EXACT = (
    "MallocStackLogging: can't turn off malloc stack logging because it was not enabled."
)
_MALLOC_LINE = re.compile(
    rf"^(?:[\w./+-]+\(\d+\)\s+)?{re.escape(_MALLOC_EXACT)}\s*$"
)
# The warning is sometimes glued to a tqdm meter that never printed a newline.
_MALLOC_EMBEDDED = re.compile(
    rf"(?:[\w./+-]+\(\d+\)\s+)?{re.escape(_MALLOC_EXACT)}"
)
# Default tqdm meter: "  0%|          | 0/346 [00:00<?, ?it/s]"
# Optional "desc:" prefix. The bracketed timer distinguishes it from prose.
_TQDM_FRAGMENT = re.compile(
    r"^\s*(?:[^:\r\n]{0,120}:\s*)?\d{1,3}%\|[^|\r\n]*\|\s*\d+/\d+"
    r"(?:\s*\[[^\]]*\])?\s*$"
)
_COUNT_SUFFIX = re.compile(r"\s+\d+/\d+\s*$")

# Qt's FFmpeg backend probes Media Foundation codecs that many PCs lack.
_FFMPEG_NOISE = (
    "hevc_mf @",
    "could not find any MFT for the given media type",
    "could not create MFT",
    "[h264_mf @",
)


def is_malloc_stack_noise(text: str) -> bool:
    return bool(_MALLOC_LINE.match((text or "").strip()))


def is_tqdm_fragment(text: str) -> bool:
    return bool(_TQDM_FRAGMENT.match(text or ""))


def is_ffmpeg_probe_noise(text: str) -> bool:
    return any(fragment in (text or "") for fragment in _FFMPEG_NOISE)


def strip_count_suffix(message: str) -> str:
    """Drop a trailing ``12/346`` so stage changes can be compared."""
    return _COUNT_SUFFIX.sub("", (message or "").strip())


def status_worth_logging(previous: str, message: str) -> bool:
    """True when a status line is a new stage, not the next tick of the same count."""
    text = (message or "").strip()
    if not text or text == (previous or "").strip():
        return False
    if previous and strip_count_suffix(previous) == strip_count_suffix(text):
        return False
    return True


def _clean_part(part: str) -> str:
    text = _MALLOC_EMBEDDED.sub("", part).strip()
    if not text or is_tqdm_fragment(text) or is_ffmpeg_probe_noise(text):
        return ""
    return text


def sanitize_console_text(text: str) -> str:
    """Remove malloc-stack and tqdm fragments. Keep every other line."""
    if not text:
        return text
    newline = text.endswith("\n")
    kept: list[str] = []
    for part in re.split(r"[\r\n]", text):
        cleaned = _clean_part(part)
        if cleaned:
            kept.append(cleaned)
    if not kept:
        return ""
    out = "\n".join(kept)
    if newline:
        out += "\n"
    return out


def sanitize_console_bytes(line: bytes) -> bytes:
    if not line:
        return line
    text = line.decode("utf-8", "replace")
    cleaned = sanitize_console_text(text)
    if cleaned == text:
        return line
    if not cleaned:
        return b""
    return cleaned.encode("utf-8", "replace")
