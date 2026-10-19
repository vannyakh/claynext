"""Video surface that paints graded player frames."""
from __future__ import annotations

import time

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtMultimedia import QVideoSink

from claynext.models.adjust import clean_adjust
from claynext.models.fx import TIMED_EFFECTS

from claynext.gui.components.media_preview.image import fx_image, grade_image

class _VideoSurface(QWidget):
    """Paints player frames itself so the canvas can clip, move, scale, and grade them."""

    frame_image = Signal(QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sink = QVideoSink(self)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._frame = QImage()
        self._cache: tuple[tuple | None, QImage] = (None, QImage())
        self._adjust: dict = {}
        self._fx: list[dict] = []
        self._fx_ms = 0
        self._frame_clock = 0.0
        self._mode = Qt.AspectRatioMode.KeepAspectRatio

    def videoSink(self) -> QVideoSink:
        return self._sink

    def setAspectRatioMode(self, mode: Qt.AspectRatioMode):
        self._mode = mode
        self._cache = (None, QImage())
        self.update()

    def set_adjust(self, adjust: dict | None):
        self._adjust = clean_adjust(adjust)
        self._cache = (None, QImage())
        self.update()

    def set_effects(self, spans: list[dict], now_ms: int):
        """Effect / filter / transition clips under the playhead at timeline time `now_ms`."""
        active = [row for row in spans or [] if row.get("start_ms", 0) <= now_ms < row.get("end_ms", 0)]
        # Transitions and timed effects change every frame (progress / motion).
        timed = any(
            str(r.get("kind") or "") == "transition" or r.get("effect") in TIMED_EFFECTS
            for r in active
        )
        if active == self._fx and (now_ms == self._fx_ms or not timed):
            return
        self._fx, self._fx_ms = active, int(now_ms)
        self._cache = (None, QImage())
        self.update()

    def _on_frame(self, frame):
        if not self.isVisible() or not frame.isValid():
            return
        now = time.monotonic()
        # Leave time for scrolling and the rest of the window. 30fps is enough for preview.
        if now - self._frame_clock < 0.033:
            return
        self._frame_clock = now
        image = frame.toImage()
        if image.isNull():
            return
        self._frame = image
        self._cache = (None, QImage())
        self.update()
        self.frame_image.emit(image)

    def _target(self) -> QRect:
        size = self._frame.size().scaled(self.size(), self._mode)
        return QRect((self.width() - size.width()) // 2, (self.height() - size.height()) // 2, size.width(), size.height())

    def paintEvent(self, _event):
        if self._frame.isNull():
            return
        target = self._target()
        key = (target.width(), target.height(), repr(self._fx), self._fx_ms if self._fx else 0)
        if self._cache[0] != key:
            image = self._frame.scaled(
                target.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation
            )
            self._cache = (key, fx_image(grade_image(image, self._adjust), self._fx, self._fx_ms))
        p = QPainter(self)
        p.drawImage(target.topLeft(), self._cache[1])
        p.end()
