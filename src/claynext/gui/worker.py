"""
PySide6 QThreadPool worker thread for asynchronous tasks.
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """
    Defines signals available from a running worker thread.
    Supported signals:
    - started: emitted when task begins
    - progress: (int percent, str status_msg)
    - result: object data returned from task
    - finished: emitted when task completes
    - error: (str error_msg, str stack_trace)
    """
    started = Signal()
    progress = Signal(int, str)
    progress_fine = Signal(float, str)
    result = Signal(object)
    finished = Signal()
    error = Signal(str, str)


class Worker(QRunnable):
    """
    Generic QRunnable worker thread for executing functions asynchronously in Qt.
    """
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._progress_at = 0.0
        self._progress_pending: tuple[int, str, float] | None = None
        self._progress_timer: threading.Timer | None = None

        # Inject progress callback into kwargs if supported.
        # The GUI only needs a fresh status about ten times a second.
        def _emit_progress(val=0, msg=""):
            try:
                number = float(val)
            except (TypeError, ValueError):
                number = 0.0
            number = max(0.0, min(100.0, number))
            text = str(msg)
            slot = (int(number), text, number)
            now = time.monotonic()
            if slot[0] >= 100 or now - self._progress_at >= 0.1:
                self._flush_progress(slot)
            else:
                self._progress_pending = slot
                self._schedule_progress()

        _emit_progress.emit = _emit_progress
        self.kwargs["progress_callback"] = _emit_progress

    def _schedule_progress(self) -> None:
        if self._progress_timer is not None:
            return
        timer = threading.Timer(0.1, self._emit_pending_progress)
        timer.daemon = True
        self._progress_timer = timer
        timer.start()

    def _emit_pending_progress(self) -> None:
        self._progress_timer = None
        slot = self._progress_pending
        if slot is not None:
            self._flush_progress(slot)

    def _flush_progress(self, slot: tuple[int, str, float]) -> None:
        timer = self._progress_timer
        self._progress_timer = None
        if timer is not None:
            timer.cancel()
        self._progress_at = time.monotonic()
        self._progress_pending = None
        pct, text, fine = slot
        try:
            self.signals.progress.emit(pct, text)
            self.signals.progress_fine.emit(fine, text)
        except Exception:
            pass

    @Slot()
    def run(self):
        try:
            self.signals.started.emit()
            res = self.fn(*self.args, **self.kwargs)
            if self._progress_pending is not None:
                self._flush_progress(self._progress_pending)
            self.signals.result.emit(res)
        except Exception as e:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            self.signals.error.emit(str(e), tb_str)
        finally:
            timer = self._progress_timer
            self._progress_timer = None
            if timer is not None:
                timer.cancel()
            self.signals.finished.emit()

