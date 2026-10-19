"""Background install for one catalog model."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThreadPool, Signal

from claynext.gui.worker import Worker
from claynext.models.hf_hub import install_model


class ModelInstall(QObject):
    """Runs a model install off the UI thread and reports percent plus a message."""

    progress = Signal(int, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.repo_id: str | None = None
        self._pool = QThreadPool.globalInstance()

    @property
    def busy(self) -> bool:
        return self.repo_id is not None

    def start(self, repo_id: str) -> bool:
        if self.busy:
            return False
        self.repo_id = repo_id

        def _task(progress_callback=None):
            return install_model(repo_id, progress_callback=progress_callback)

        worker = Worker(_task)
        worker.signals.progress.connect(self.progress.emit)
        worker.signals.result.connect(self._done)
        worker.signals.error.connect(self._error)
        self._pool.start(worker)
        return True

    def _done(self, path: str) -> None:
        self.repo_id = None
        self.finished.emit(str(path or ""))

    def _error(self, err_msg: str, _stack: str) -> None:
        self.repo_id = None
        self.failed.emit(str(err_msg or "Install failed"))
