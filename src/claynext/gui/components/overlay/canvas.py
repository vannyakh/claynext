"""Preview overlay canvas: items sit on the video frame."""
from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from claynext.gui.components.overlay.canvas_geom import CanvasGeom
from claynext.gui.components.overlay.canvas_input import CanvasInput
from claynext.gui.components.overlay.canvas_items import CanvasItems
from claynext.gui.components.overlay.canvas_paint import CanvasPaint
from claynext.gui.components.overlay.canvas_view import CanvasView
from claynext.gui.components.overlay.item import OverlayItem
from claynext.models.canvas import clean_canvas


class OverlayCanvas(CanvasView, CanvasGeom, CanvasItems, CanvasPaint, CanvasInput, QWidget):
    item_selected = Signal(object)
    items_changed = Signal()
    item_edited = Signal(object)
    command = Signal(str)
    video_clicked = Signal()
    video_transform = Signal(dict)
    video_transform_done = Signal()
    view_tool_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("overlay_canvas")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.items: list[OverlayItem] = []
        self.selected_id = ""
        self._drag_id = ""
        self._drag_off = QPointF(0, 0)
        self._pix: dict[str, QPixmap] = {}
        self._live_caption = ""
        self._live_span = (0, 0)
        self._live_has_lines = False
        self._video_ratio: float | None = None
        self._video_canvas = clean_canvas(None)
        self._video_edit = False
        self._video_drag = ""
        self._video_start = (QPointF(), dict(self._video_canvas), 1.0)
        self._snap = (False, False)
        self._playhead_ms = 0
        self._drag_mode = ""
        self._drag_start: tuple = ()
        self._demo: tuple[str, str, int] | None = None
        self._demo_clock = QElapsedTimer()
        self._demo_timer = QTimer(self)
        self._demo_timer.setInterval(16)
        self._demo_timer.timeout.connect(self._tick_demo)
        self._preview: QWidget | None = None
        self._view_tool = "move"
        self._panning = False
        self._tool_hot = ""
        # Project canvas area inside the full wrapper panel (letterbox is outside this).
        self._content = QRect()

