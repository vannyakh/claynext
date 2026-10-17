"""Shared CLI helpers (progress, I/O, exit helpers)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable


def die(message: str, code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def progress_printer(pct: int, msg: str = "") -> None:
    """Human-friendly progress line for long-running tools."""
    text = str(msg or "").strip()
    if text:
        print(f"[{int(pct):3d}%] {text}", file=sys.stderr, flush=True)
    else:
        print(f"[{int(pct):3d}%]", file=sys.stderr, flush=True)


def require_file(path: str | Path, *, label: str = "file") -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        die(f"{label} not found: {p}")
    return p


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_segments(path: str | Path) -> list[dict[str, Any]]:
    from claynext.gui.views.studio.helpers import import_segments

    p = require_file(path, label="input")
    try:
        rows = import_segments(str(p))
    except Exception as exc:
        die(f"could not read segments: {exc}")
    if not rows:
        die("no subtitle / script lines found in input")
    return rows


def save_segments(path: str | Path, segments: list[dict[str, Any]], fmt: str | None = None) -> Path:
    from claynext.gui.views.studio.helpers import export_segments

    out = Path(path).expanduser().resolve()
    ensure_parent(out)
    kind = (fmt or out.suffix.lstrip(".") or "json").lower()
    if kind in {"json", "srt", "vtt"}:
        export_segments(str(out), kind, segments)
        return out
    # Fallback JSON dump
    out.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def make_progress(quiet: bool) -> Callable[[int, str], None] | None:
    if quiet:
        return None
    return progress_printer
