import sys
import traceback
from PySide6.QtCore import QRunnable, QObject, Signal, Slot


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
    result = Signal(object)
    finished = Signal()
    error = Signal(str, str)


class Worker(QRunnable):
    """
    Generic QRunnable worker thread for executing functions asynchronously.
    """
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
        # Inject progress callback into kwargs if supported
        def _emit_progress(val=0, msg=""):
            try:
                self.signals.progress.emit(int(val), str(msg))
            except Exception:
                pass
        
        _emit_progress.emit = _emit_progress
        self.kwargs['progress_callback'] = _emit_progress

    @Slot()
    def run(self):
        try:
            self.signals.started.emit()
            res = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(res)
        except Exception as e:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            self.signals.error.emit(str(e), tb_str)
        finally:
            self.signals.finished.emit()
