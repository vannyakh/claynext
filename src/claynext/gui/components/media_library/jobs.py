"""Background thumbnail and duration probes for the media library."""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from claynext.models.thumbnails import icon_for

class _ThumbSignals(QObject):
    ready = Signal(str, object)  # path, QIcon

class _ThumbJob(QRunnable):
    def __init__(self, path: str, size: int, signals: _ThumbSignals):
        super().__init__()
        self.path = path
        self.size = size
        self.signals = signals

    def run(self):
        try:
            ico = icon_for(self.path, size=self.size)
            if not ico.isNull():
                self.signals.ready.emit(self.path, ico)
        except Exception:
            pass

class _DurSignals(QObject):
    ready = Signal(str, float, dict)  # path, seconds, meta dict

class _DurJob(QRunnable):
    def __init__(self, path: str, signals: _DurSignals):
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self):
        try:
            from claynext.adapters.ffmpeg_service import probe_media
            info = probe_media(self.path)
            dur = float(info.get("duration") or 0.0)
            self.signals.ready.emit(self.path, dur, info)
        except Exception:
            try:
                self.signals.ready.emit(self.path, 0.0, {})
            except Exception:
                pass
