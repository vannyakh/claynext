"""Turn library tqdm bars into one status line.

The first paint of a tqdm bar is ``0/N`` with elapsed ``00:00`` and rate
``?it/s``. That is the opening frame of the loop, before the first step
finishes. Callers keep the job percent and replace the message with
``Stage 0/N``.
"""
from __future__ import annotations

import contextvars
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from claynext.utils.console_noise import strip_count_suffix

ProgressFn = Callable[..., object]

_listener: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar(
    "claynext_library_progress",
    default=None,
)
_stage: contextvars.ContextVar[str] = contextvars.ContextVar(
    "claynext_library_stage",
    default="",
)
_installed = False


def library_status(bar: object) -> str:
    """``Transcribing 0/346`` from a tqdm instance."""
    total = getattr(bar, "total", None)
    try:
        done = int(getattr(bar, "n", 0) or 0)
    except (TypeError, ValueError):
        done = 0
    desc = str(getattr(bar, "desc", "") or "").strip().rstrip(":")
    label = desc or _stage.get() or "Working"
    try:
        total_n = int(total) if total else 0
    except (TypeError, ValueError):
        total_n = 0
    if total_n > 0:
        return f"{label} {done}/{total_n}"
    return f"{label} {done}"


def install_quiet_tqdm() -> None:
    """Stop tqdm from drawing a bar or starting a lock process."""
    global _installed
    if _installed:
        return
    try:
        import threading

        from tqdm import std
    except Exception:
        return

    def display(self, msg=None, pos=None):  # noqa: ARG001
        listener = _listener.get()
        if listener is not None:
            try:
                listener(library_status(self))
            except Exception:
                pass
        return False

    std.tqdm.display = display  # type: ignore[method-assign]
    # The default lock is a multiprocessing lock and starts a Python
    # resource-tracker process on macOS.
    try:
        std.tqdm.set_lock(threading.RLock())
    except Exception:
        pass
    _installed = True


@contextmanager
def library_stage(name: str) -> Iterator[None]:
    """Label the next library bar when the bar itself has no description."""
    token = _stage.set(name)
    try:
        yield
    finally:
        _stage.reset(token)


@contextmanager
def bind_job_progress(callback: ProgressFn | None) -> Iterator[ProgressFn]:
    """Send library bars to ``callback(percent, message)`` at the current percent."""
    held = {"pct": 0}
    stage_token = _stage.set("")

    def wrapped(val: object = 0, msg: object = "") -> object:
        try:
            held["pct"] = max(0, min(100, int(float(val))))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
        text = str(msg or "")
        if text and text == strip_count_suffix(text):
            _stage.set(text)
        if callback is not None:
            return callback(val, msg)
        return None

    def on_library(message: str) -> None:
        if callback is not None:
            callback(held["pct"], message)

    listener_token = _listener.set(on_library)
    try:
        yield wrapped
    finally:
        _listener.reset(listener_token)
        _stage.reset(stage_token)
