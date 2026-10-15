"""Pause / continue / cancel gate shared between the GUI and a background job."""
from __future__ import annotations

import threading


class JobCancelled(RuntimeError):
    pass


class JobControl:
    """The job calls ``checkpoint()`` between steps; the GUI flips pause / cancel."""

    def __init__(self):
        self._running = threading.Event()
        self._running.set()
        self._cancelled = False

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def pause(self):
        self._running.clear()

    def resume(self):
        self._running.set()

    def cancel(self):
        self._cancelled = True
        self._running.set()

    def checkpoint(self):
        while not self._running.wait(0.2):
            pass
        if self._cancelled:
            raise JobCancelled("Dub stopped")
