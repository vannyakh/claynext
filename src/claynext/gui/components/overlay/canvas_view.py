"""Preview binding, pan, playhead, and the video transform frame."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtWidgets import QWidget

from claynext.gui.components.overlay.const import HANDLE_KINDS, HANDLE_R
from claynext.models.canvas import clean_canvas, video_box
from claynext.models.text_style import is_animated


class CanvasView:
    def bind_preview(self, preview: QWidget):
        """Route wheel zoom / Hand pan into the media preview under this canvas."""
        if preview is self._preview:
            return
        if self._preview is not None and hasattr(self._preview, "view_tool_changed"):
            try:
                self._preview.view_tool_changed.disconnect(self.sync_view_tool)
            except (TypeError, RuntimeError):
                pass
        self._preview = preview
        if hasattr(preview, "view_tool"):
            self._view_tool = preview.view_tool()
        if hasattr(preview, "view_tool_changed"):
            preview.view_tool_changed.connect(self.sync_view_tool)
        self._sync_tool_cursor()

    def set_content_rect(self, rect: QRect):
        """Map overlay items to the media canvas frame inside the wrapper panel."""
        r = QRect(rect) if rect is not None else QRect()
        if r.width() < 1 or r.height() < 1:
            r = self.rect()
        if r == self._content:
            return
        self._content = QRect(r)
        self.update()

    def content_rect(self) -> QRect:
        r = self._content
        return QRect(r) if r.width() > 0 and r.height() > 0 else self.rect()

    def _frame_wh(self) -> tuple[int, int]:
        r = self.content_rect()
        return max(1, r.width()), max(1, r.height())

    def _to_content(self, pos: QPointF) -> QPointF:
        o = self.content_rect().topLeft()
        return QPointF(pos.x() - o.x(), pos.y() - o.y())

    def _from_content(self, pos: QPointF) -> QPointF:
        o = self.content_rect().topLeft()
        return QPointF(pos.x() + o.x(), pos.y() + o.y())

    def _in_content(self, pos: QPointF | QPoint) -> bool:
        pt = pos.toPoint() if isinstance(pos, QPointF) else QPoint(pos)
        return self.content_rect().contains(pt)

    def view_tool(self) -> str:
        return self._view_tool

    def set_view_tool(self, tool: str, *, emit: bool = True):
        tool = "hand" if tool == "hand" else "move"
        if tool == self._view_tool:
            self._sync_tool_cursor()
            return
        self._view_tool = tool
        if self._panning and tool != "hand":
            self._end_pan()
        self._sync_tool_cursor()
        # Preview owns the signal that updates the V/H transport buttons.
        if self._preview is not None and hasattr(self._preview, "set_view_tool"):
            self._preview.set_view_tool(tool, emit=True)
        elif emit:
            self.view_tool_changed.emit(tool)

    def sync_view_tool(self, tool: str):
        tool = "hand" if tool == "hand" else "move"
        if tool == self._view_tool:
            self._sync_tool_cursor()
            return
        self._view_tool = tool
        if self._panning and tool != "hand":
            self._end_pan()
        self._sync_tool_cursor()

    def _hand_active(self) -> bool:
        return self._view_tool == "hand"

    def _preview_zoomed(self) -> bool:
        preview = self._preview
        if preview is None:
            return False
        if hasattr(preview, "is_zoomed"):
            return bool(preview.is_zoomed())
        return False

    def _map_to_preview(self, pos: QPoint | QPointF) -> QPoint:
        pt = pos.toPoint() if isinstance(pos, QPointF) else QPoint(pos)
        if self._preview is None:
            return pt
        return self._preview.mapFromGlobal(self.mapToGlobal(pt))

    def _sync_tool_cursor(self):
        if self._panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._hand_active():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

    def _begin_pan(self, pos: QPoint | QPointF) -> bool:
        preview = self._preview
        if preview is None or not hasattr(preview, "begin_hand_pan"):
            return False
        ok = preview.begin_hand_pan(self._map_to_preview(pos))
        self._panning = bool(ok)
        if self._panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        return self._panning

    def _update_pan(self, pos: QPoint | QPointF):
        preview = self._preview
        if not self._panning or preview is None or not hasattr(preview, "update_hand_pan"):
            return
        preview.update_hand_pan(self._map_to_preview(pos))

    def _end_pan(self):
        preview = self._preview
        if preview is not None and hasattr(preview, "end_hand_pan"):
            preview.end_hand_pan()
        self._panning = False
        self._sync_tool_cursor()

    def set_playhead(self, ms: int):
        """Timeline time, so text animations show where the playhead is."""
        ms = int(ms)
        if ms == self._playhead_ms:
            return
        self._playhead_ms = ms
        if any(it.kind in HANDLE_KINDS and is_animated(it.style()) for it in self.items):
            self.update()

    def preview_animation(self, item_id: str, slot: str):
        """Play just the chosen in / out / loop animation once on the canvas."""
        self._demo = (item_id, slot, 0)
        self._demo_clock.restart()
        self._demo_timer.start()
        self.update()

    def _demo_span(self, style: dict, slot: str) -> tuple[int, int, int]:
        """(start, end, clip length) of the fake clip used for a demo."""
        if slot == "anim_loop":
            period = style["anim_loop_ms"]
            return 0, period * 2, period * 2 + 1
        length = style["anim_in_ms"] if slot == "anim_in" else style["anim_out_ms"]
        dur = length * 2 + 600
        return (0, length + 400, dur) if slot == "anim_in" else (dur - length - 400, dur, dur)

    def _tick_demo(self):
        if self._demo is None:
            self._demo_timer.stop()
            return
        item = next((it for it in self.items if it.id == self._demo[0]), None)
        if item is None:
            self._demo = None
            self._demo_timer.stop()
            return
        start, end, _dur = self._demo_span(item.style(), self._demo[1])
        if self._demo_clock.elapsed() > end - start:
            self._demo = None
            self._demo_timer.stop()
        self.update()

    def set_video_frame(self, ratio: float | None, canvas: dict | None):
        """Where the footage sits on the canvas, for the transform handles."""
        self._video_ratio = ratio if ratio and ratio > 0 else None
        self._video_canvas = clean_canvas(canvas)
        self.update()

    def set_video_edit(self, on: bool):
        if self._video_edit != bool(on):
            self._video_edit = bool(on)
            self.update()

    def _video_rect(self) -> QRectF | None:
        if not self._video_ratio:
            return None
        fw, fh = self._frame_wh()
        x, y, w, h = video_box(fw, fh, self._video_ratio, self._video_canvas)
        origin = self.content_rect().topLeft()
        return QRectF(origin.x() + x, origin.y() + y, w, h)

    def _video_corner_at(self, pos: QPointF) -> int:
        rect = self._video_rect()
        if rect is None:
            return -1
        corners = (rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft())
        for index, corner in enumerate(corners):
            if abs(pos.x() - corner.x()) <= HANDLE_R + 4 and abs(pos.y() - corner.y()) <= HANDLE_R + 4:
                return index
        return -1
