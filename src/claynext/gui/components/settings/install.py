"""Background installs for catalog models. Several may run, up to the core plan."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThreadPool, Signal

from claynext.adapters.resources import download_slots
from claynext.gui.worker import Worker
from claynext.models.hf_hub import install_model


class ModelInstall(QObject):
    """Runs model downloads off the UI thread. Each repo keeps its own percent."""

    progress = Signal(str, int, str)
    finished = Signal(str, str)
    failed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._queued: list[str] = []
        self._active: set[str] = set()
        self._pct: dict[str, int] = {}

    @property
    def jobs(self) -> dict[str, int]:
        """Repo id to percent for every download that is queued or running."""
        out = {repo: self._pct.get(repo, 0) for repo in self._active}
        for repo in self._queued:
            out[repo] = -1
        return out

    def start(self, repo_id: str) -> bool:
        repo_id = (repo_id or "").strip()
        if not repo_id or repo_id in self._active or repo_id in self._queued:
            return False
        self._queued.append(repo_id)
        self._pct[repo_id] = 0
        self._pump()
        return True

    def _pump(self) -> None:
        slots = max(1, download_slots())
        while self._queued and len(self._active) < slots:
            repo_id = self._queued.pop(0)
            self._active.add(repo_id)
            self._start(repo_id)

    def _start(self, repo_id: str) -> None:
        def _task(progress_callback=None):
            return install_model(repo_id, progress_callback=progress_callback)

        worker = Worker(_task)
        worker.signals.progress.connect(
            lambda pct, msg, rid=repo_id: self._on_progress(rid, pct, msg)
        )
        worker.signals.result.connect(lambda path, rid=repo_id: self._done(rid, path))
        worker.signals.error.connect(lambda err, _tb, rid=repo_id: self._error(rid, err))
        self._pool.start(worker)

    def _on_progress(self, repo_id: str, pct: int, msg: str) -> None:
        self._pct[repo_id] = max(0, min(99, int(pct)))
        self.progress.emit(repo_id, self._pct[repo_id], str(msg or ""))

    def _finish(self, repo_id: str) -> None:
        self._active.discard(repo_id)
        self._pct.pop(repo_id, None)
        self._pump()

    def _done(self, repo_id: str, path: str) -> None:
        self._finish(repo_id)
        self.finished.emit(repo_id, str(path or ""))

    def _error(self, repo_id: str, err_msg: str) -> None:
        self._finish(repo_id)
        self.failed.emit(repo_id, str(err_msg or "Install failed"))
