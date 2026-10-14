"""Draggable text / caption / logo / image overlays on the dub preview."""
from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass, field, asdict, fields

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QColorDialog, QFrame, QSizePolicy, QToolButton,
)
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPoint, QPointF, QElapsedTimer, QTimer, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QPixmap, QCursor, QTransform, QIcon,
)

from jela.constants.theme_constants import (
    COLOR_ACCENT_CYAN, COLOR_ACCENT_PURPLE, COLOR_BG_DARK, COLOR_BG_INPUT,
    COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BORDER, COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
)
from jela.core.icons import icon
from jela.core.text_style import SCALE_RANGE, anim_frame, clean_text_style, is_animated
from jela.core.video_canvas import clean_canvas, video_box
from jela.gui.components.scrub_spin import ScrubSpinBox
from jela.gui.components.shape_render import paint_shape, shape_px, shape_size
from jela.gui.components.text_render import caption_width, fit_caption, item_box, paint_text, wrap_text

TEXT_KINDS = {"text", "caption"}
HANDLE_KINDS = TEXT_KINDS | {"shape"}


@dataclass
class OverlayItem:
    id: str
    kind: str
    x: float = 0.5
    y: float = 0.5
    w: float = 0.28
    h: float = 0.10
    rotation: float = 0.0
    color: str = "#f8fafc"
    opacity: int = 100
    text: str = "Text"
    font_size: int = 20
    path: str = ""
    live: bool = False
    font: str = "Arial"
    scale: int = 100
    bold: bool = False
    italic: bool = False
    underline: bool = False
    case: str = "none"
    align: str = "center"
    letter: int = 0
    stroke_on: bool = False
    stroke_color: str = "#000000"
    stroke_width: int = 3
    bg_on: bool = False
    bg_color: str = "#000000"
    bg_opacity: int = 70
    shadow_on: bool = False
    shadow_color: str = "#000000"
    shadow_dist: int = 2
    anim_in: str = "none"
    anim_in_ms: int = 500
    anim_out: str = "none"
    anim_out_ms: int = 500
    anim_loop: str = "none"
    anim_loop_ms: int = 1200
    highlight_color: str = "#facc15"
    caption_fit: bool = True
    caption_width: int = 80
    preset: str = ""
    shape: str = "rect"
    blur_on: bool = False
    blur_radius: int = 20
    lock_aspect: bool = True
    start_ms: int = 0
    duration_ms: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def style(self) -> dict:
        return clean_text_style(asdict(self))

    @classmethod
    def from_dict(cls, data: dict) -> "OverlayItem":
        src = dict(data or {})
        kind = str(src.get("kind") or "text")
        if kind in TEXT_KINDS and "stroke_on" not in src:
            src.setdefault("bold", kind == "text")
            if kind == "caption":
                src.setdefault("bg_on", True)
                src.setdefault("bg_opacity", 47)
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in src.items() if k in known}
        payload.setdefault("id", uuid.uuid4().hex[:10])
        payload.setdefault("kind", "text")
        return cls(**payload)


def default_item(kind: str) -> OverlayItem:
    presets = {
        "text": OverlayItem(id=uuid.uuid4().hex[:10], kind="text", x=0.5, y=0.35, w=0.5, h=0.12, text="Title", font_size=28, color="#fbbf24", bold=True),
        "caption": OverlayItem(id=uuid.uuid4().hex[:10], kind="caption", x=0.5, y=0.84, w=0.7, h=0.10, text="Caption", font_size=18, color="#f8fafc", live=True, bg_on=True, bg_opacity=47),
        "logo": OverlayItem(id=uuid.uuid4().hex[:10], kind="logo", x=0.88, y=0.10, w=0.14, h=0.14, text="LOGO", font_size=14, color="#ffffff"),
        "image": OverlayItem(id=uuid.uuid4().hex[:10], kind="image", x=0.22, y=0.18, w=0.22, h=0.22, text="Image", font_size=12, color="#e2e8f0"),
        "shape": OverlayItem(id=uuid.uuid4().hex[:10], kind="shape", w=shape_size("rect")[0], h=shape_size("rect")[1], text="Element"),
    }
    return presets.get(kind, presets["text"])


_HANDLE_R = 5
_SNAP_PCT = 2
_ROTATE_GAP = 18
_ROTATE_SNAP = 4.0


class OverlayCanvas(QWidget):
    item_selected = Signal(object)
    items_changed = Signal()
    item_edited = Signal(object)
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
        # Project canvas area inside the full wrapper panel (letterbox is outside this).
        self._content = QRect()

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

    def _frame_for(self, item: OverlayItem, style: dict) -> dict:
        if self._demo is not None and self._demo[0] == item.id:
            slot = self._demo[1]
            solo = dict(style, anim_in="none", anim_out="none", anim_loop="none")
            solo[slot] = style[slot]
            start, end, dur = self._demo_span(style, slot)
            return anim_frame(solo, min(end, start + self._demo_clock.elapsed()), dur)
        if item.id == self._drag_id:
            return anim_frame(style, 0, 0)
        if self._is_live(item) and self._live_span[1] > self._live_span[0]:
            start, end = self._live_span
            return anim_frame(style, self._playhead_ms - start, end - start)
        if item.duration_ms <= 0:
            return anim_frame(style, 0, 0)
        return anim_frame(style, self._playhead_ms - item.start_ms, item.duration_ms)

    def _is_live(self, item: OverlayItem) -> bool:
        return item.kind == "caption" and item.live and bool(self._live_caption)

    def _caption_layout(self, item: OverlayItem) -> tuple[dict, str]:
        """Style (font may shrink to fit width) and wrapped text for a caption draw."""
        style = item.style()
        if self._is_live(item):
            raw = self._live_caption
        elif item.kind == "caption" and item.live and self._live_has_lines:
            return style, ""
        else:
            raw = item.text or ""
        if item.kind != "caption" or not raw.strip():
            return style, raw
        fw, fh = self._frame_wh()
        aspect = fw / fh
        limit = caption_width(item.x, aspect, style)
        if style.get("caption_fit"):
            return fit_caption(style, raw, limit)
        return style, wrap_text(style, raw, limit)

    def _shown_text(self, item: OverlayItem) -> str:
        """Text drawn for `item`; a live caption between dubbed lines draws nothing."""
        if item.kind == "caption":
            return self._caption_layout(item)[1]
        return item.text or ""

    def _text_geom(self, item: OverlayItem) -> tuple[QPointF, QRectF, dict, str]:
        """Centre on the canvas, unrotated box around (0, 0), style, and drawn text."""
        if item.kind == "caption":
            style, text = self._caption_layout(item)
        else:
            style = item.style()
            text = item.text or ""
        fw, fh = self._frame_wh()
        center = self._from_content(QPointF(item.x * fw, item.y * fh))
        return center, self._box_for(item, style, text), style, text

    def _box_for(self, item: OverlayItem, style: dict, text: str = "") -> QRectF:
        _fw, fh = self._frame_wh()
        if item.kind == "shape":
            w, h = shape_px(style, item.w, item.h, fh)
            return QRectF(-w / 2, -h / 2, w, h)
        return item_box(style, text or " ", fh)

    def aligned_position(self, item: OverlayItem, where: str, margin: float = 0.04) -> tuple[float, float]:
        """Centre (x, y) that puts the text box against a canvas edge or on a centre line."""
        w, h = self._frame_wh()
        _center, box, _style, _text = self._text_geom(item)
        box = QTransform().rotate(item.rotation).mapRect(box)
        half_w, half_h = box.width() / 2 / w, box.height() / 2 / h
        x, y = float(item.x), float(item.y)
        if where == "left":
            x = margin + half_w
        elif where == "right":
            x = 1 - margin - half_w
        elif where == "hcenter":
            x = 0.5
        elif where == "top":
            y = margin + half_h
        elif where == "bottom":
            y = 1 - margin - half_h
        elif where == "vcenter":
            y = 0.5
        return min(0.98, max(0.02, x)), min(0.98, max(0.02, y))

    @staticmethod
    def _local(pos: QPointF, center: QPointF, rotation: float) -> QPointF:
        return QTransform().rotate(-rotation).map(pos - center)

    def _text_handle_at(self, item: OverlayItem, pos: QPointF) -> str:
        center, box, _style, _text = self._text_geom(item)
        local = self._local(pos, center, item.rotation)
        reach = _HANDLE_R + 5
        knob = QPointF(0, box.bottom() + _ROTATE_GAP)
        if (local - knob).manhattanLength() <= reach + 3:
            return "rotate"
        if abs(local.x() - box.left()) <= reach and abs(local.y() - box.top()) <= reach:
            return "handle_tl"
        if abs(local.x() - box.right()) <= reach and abs(local.y() - box.top()) <= reach:
            return "handle_tr"
        if abs(local.x() - box.right()) <= reach and abs(local.y() - box.bottom()) <= reach:
            return "handle_br"
        if abs(local.x() - box.left()) <= reach and abs(local.y() - box.bottom()) <= reach:
            return "handle_bl"
        if item.kind == "shape":
            if abs(local.y() - box.top()) <= reach and abs(local.x()) <= reach + 8:
                return "handle_top"
            if abs(local.y() - box.bottom()) <= reach and abs(local.x()) <= reach + 8:
                return "handle_bottom"
            if abs(local.x() - box.left()) <= reach and abs(local.y()) <= reach + 8:
                return "handle_left"
            if abs(local.x() - box.right()) <= reach and abs(local.y()) <= reach + 8:
                return "handle_right"
        return ""

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
            if abs(pos.x() - corner.x()) <= _HANDLE_R + 4 and abs(pos.y() - corner.y()) <= _HANDLE_R + 4:
                return index
        return -1

    def _paint_video_frame(self, p: QPainter):
        rect = self._video_rect()
        if rect is None or not self._video_edit:
            return
        snap_x, snap_y = self._snap
        if self._video_drag == "move" and (snap_x or snap_y):
            frame = self.content_rect()
            p.setPen(QPen(QColor(COLOR_ACCENT_CYAN), 1, Qt.PenStyle.DashLine))
            if snap_x:
                mid_x = frame.center().x()
                p.drawLine(QPointF(mid_x, frame.top()), QPointF(mid_x, frame.bottom()))
            if snap_y:
                mid_y = frame.center().y()
                p.drawLine(QPointF(frame.left(), mid_y), QPointF(frame.right(), mid_y))
        p.setPen(QPen(QColor(COLOR_TEXT_MAIN), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect)
        p.setPen(QPen(QColor(COLOR_BG_DARK), 1))
        p.setBrush(QColor(COLOR_TEXT_MAIN))
        for corner in (rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()):
            p.drawEllipse(corner, _HANDLE_R, _HANDLE_R)

    def set_items(self, rows: list[dict] | list[OverlayItem]):
        parsed = []
        for row in rows or []:
            parsed.append(row if isinstance(row, OverlayItem) else OverlayItem.from_dict(row))
        prev = self.selected_id
        self.items = parsed
        # Keep selection if the item still exists; never auto-pick the first overlay
        # (that was stealing focus to Text properties during playhead sync).
        if not any(it.id == self.selected_id for it in parsed):
            self.selected_id = ""
        self.update()
        self.items_changed.emit()
        # Only notify when the selected item identity actually changed.
        if self.selected_id != prev:
            self.item_selected.emit(self.selected_item())

    def dumps(self) -> list[dict]:
        return [it.to_dict() for it in self.items]

    def selected_item(self) -> OverlayItem | None:
        return next((it for it in self.items if it.id == self.selected_id), None)

    def add_item(self, kind: str, **kwargs) -> OverlayItem:
        item = default_item(kind)
        for k, v in kwargs.items():
            if hasattr(item, k):
                setattr(item, k, v)
        self.items.append(item)
        self.selected_id = item.id
        self.update()
        self.items_changed.emit()
        self.item_selected.emit(item)
        return item

    def remove_selected(self):
        self.items = [it for it in self.items if it.id != self.selected_id]
        self.selected_id = self.items[-1].id if self.items else ""
        self.update()
        self.items_changed.emit()
        self.item_selected.emit(self.selected_item())

    def update_selected(self, **fields):
        item = self.selected_item()
        if not item:
            return
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
        self.update()
        self.items_changed.emit()

    def set_live_caption(self, text: str, start_ms: int = 0, end_ms: int = 0, has_lines: bool = False):
        """The dubbed line under the playhead and its span, so live captions animate per line.
        Without any dubbed lines a live caption shows its own text as a placeholder."""
        state = (text or "", (int(start_ms), int(end_ms)), bool(has_lines))
        if state == (self._live_caption, self._live_span, self._live_has_lines):
            return
        self._live_caption, self._live_span, self._live_has_lines = state
        self.update()

    def _rect_for(self, item: OverlayItem) -> QRect:
        rw, rh = self._frame_wh()
        w = max(36, int(item.w * rw))
        h = max(24, int(item.h * rh))
        center = self._from_content(QPointF(item.x * rw, item.y * rh))
        cx, cy = int(center.x()), int(center.y())
        return QRect(cx - w // 2, cy - h // 2, w, h)

    def _item_at(self, pos: QPoint) -> OverlayItem | None:
        for item in reversed(self.items):
            if item.kind in HANDLE_KINDS:
                center, box, _style, _text = self._text_geom(item)
                if box.adjusted(-4, -4, 4, 4).contains(self._local(QPointF(pos), center, item.rotation)):
                    return item
            elif self._rect_for(item).adjusted(-4, -4, 4, 4).contains(pos):
                return item
        return None

    def _current_video_frame(self):
        if self._preview is not None:
            if hasattr(self._preview, "current_frame_image"):
                img = self._preview.current_frame_image()
                if img is not None and not img.isNull():
                    return img
            if hasattr(self._preview, "video") and hasattr(self._preview.video, "_frame"):
                img = self._preview.video._frame
                if not img.isNull():
                    return img
            if hasattr(self._preview, "poster") and self._preview.poster.pixmap():
                return self._preview.poster.pixmap().toImage()
        return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        frame = self.content_rect()
        p.setClipRect(frame)
        _fw, fh = self._frame_wh()
        self._paint_video_frame(p)
        curr_frame_img = self._current_video_frame()
        canvas_rect_f = QRectF(frame)
        for item in self.items:
            if item.kind in TEXT_KINDS:
                center, box, style, shown = self._text_geom(item)
                if shown.strip():
                    paint_text(p, style, shown, center, fh, item.rotation, self._frame_for(item, style))
                if item.id == self.selected_id:
                    self._paint_text_chrome(p, item, center, box)
                continue
            if item.kind == "shape":
                center, box, style, _text = self._text_geom(item)
                paint_shape(
                    p,
                    style,
                    item.shape,
                    (box.width(), box.height()),
                    center,
                    fh,
                    item.rotation,
                    self._frame_for(item, style),
                    bg_image=curr_frame_img,
                    canvas_rect=canvas_rect_f,
                )
                if item.id == self.selected_id:
                    self._paint_text_chrome(p, item, center, box)
                continue
            rect = self._rect_for(item)
            p.save()
            p.translate(rect.center())
            p.rotate(item.rotation)
            p.translate(-rect.center())
            p.setOpacity(max(0.08, item.opacity / 100.0))
            self._paint_item(p, item, rect)
            p.restore()
            if item.id == self.selected_id:
                p.setPen(QPen(QColor("#38bdf8"), 1.4, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 6, 6)
        p.end()

    def _paint_text_chrome(self, p: QPainter, item: OverlayItem, center: QPointF, box: QRectF):
        snap_x, snap_y = self._snap
        if self._drag_mode == "move" and (snap_x or snap_y):
            frame = self.content_rect()
            p.setPen(QPen(QColor(COLOR_ACCENT_CYAN), 1, Qt.PenStyle.DashLine))
            if snap_x:
                mid_x = frame.center().x()
                p.drawLine(QPointF(mid_x, frame.top()), QPointF(mid_x, frame.bottom()))
            if snap_y:
                mid_y = frame.center().y()
                p.drawLine(QPointF(frame.left(), mid_y), QPointF(frame.right(), mid_y))
        p.save()
        p.translate(center)
        p.rotate(item.rotation)
        p.setPen(QPen(QColor(COLOR_TEXT_MAIN), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(box)
        p.setPen(QPen(QColor(COLOR_BG_DARK), 1))
        p.setBrush(QColor(COLOR_TEXT_MAIN))
        for corner in (box.topLeft(), box.topRight(), box.bottomRight(), box.bottomLeft()):
            p.drawEllipse(corner, _HANDLE_R, _HANDLE_R)
        if item.kind == "shape":
            for mid_x, mid_y, pw, ph in (
                (0, box.top(), 10, 4),
                (0, box.bottom(), 10, 4),
                (box.left(), 0, 4, 10),
                (box.right(), 0, 4, 10),
            ):
                p.drawRoundedRect(QRectF(mid_x - pw / 2, mid_y - ph / 2, pw, ph), 1.5, 1.5)
        knob = QPointF(0, box.bottom() + _ROTATE_GAP)
        p.setPen(QPen(QColor(COLOR_TEXT_MAIN), 1.2))
        p.drawLine(QPointF(0, box.bottom()), knob - QPointF(0, _HANDLE_R + 1))
        p.setBrush(QColor(COLOR_BG_DARK))
        p.drawEllipse(knob, _HANDLE_R + 2, _HANDLE_R + 2)
        p.drawArc(QRectF(knob.x() - 3.5, knob.y() - 3.5, 7, 7), 30 * 16, 280 * 16)
        p.restore()
        if self._drag_mode == "rotate":
            p.setPen(QColor(COLOR_TEXT_MAIN))
            p.drawText(QRectF(center.x() - 30, center.y() + box.bottom() + _ROTATE_GAP + 10, 60, 16),
                       Qt.AlignmentFlag.AlignCenter, f"{item.rotation:.0f}°")

    def _paint_item(self, p: QPainter, item: OverlayItem, rect: QRect):
        color = QColor(item.color)
        if item.kind in {"logo", "image"} and item.path and os.path.isfile(item.path):
            pix = self._pix.get(item.path)
            if pix is None:
                pix = QPixmap(item.path)
                self._pix[item.path] = pix
            if not pix.isNull():
                scaled = pix.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                x = rect.x() + (rect.width() - scaled.width()) // 2
                y = rect.y() + (rect.height() - scaled.height()) // 2
                p.drawPixmap(x, y, scaled)
                return
        if item.kind in {"caption", "text", "logo"}:
            fill = QColor(0, 0, 0, 120 if item.kind == "caption" else 40)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(rect, 8, 8)
        text = self._live_caption if (item.kind == "caption" and item.live and self._live_caption) else item.text
        font = QFont()
        font.setPixelSize(max(10, int(item.font_size)))
        font.setBold(item.kind != "caption")
        p.setFont(font)
        p.setPen(color)
        p.drawText(rect.adjusted(8, 4, -8, -4), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text or item.kind)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        preview = self._preview
        if delta != 0 and preview is not None:
            if hasattr(preview, "apply_wheel_zoom"):
                preview.apply_wheel_zoom(event.globalPosition().toPoint(), delta)
            elif hasattr(preview, "zoom_by"):
                from jela.gui.components.media_preview import ZOOM_WHEEL_FACTOR

                factor = ZOOM_WHEEL_FACTOR if delta > 0 else (1.0 / ZOOM_WHEEL_FACTOR)
                preview.zoom_by(factor, self._map_to_preview(event.position()))
            event.accept()
            return
        event.ignore()

    def mousePressEvent(self, event):
        # Middle-drag or Hand tool pans the zoomed preview frame.
        want_pan = event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._hand_active()
        )
        if want_pan:
            if self._begin_pan(event.position()):
                event.accept()
                return
            if self._hand_active() and event.button() == Qt.MouseButton.LeftButton:
                # Hand tool at 100% zoom — don't steal Move selection.
                event.accept()
                return
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if self._hand_active():
            event.accept()
            return
        pos = event.position()
        picked = self.selected_item()
        handle = self._text_handle_at(picked, pos) if picked and picked.kind in HANDLE_KINDS else ""
        if handle:
            center, box, _style, _text = self._text_geom(picked)
            self._drag_id = picked.id
            self._drag_mode = handle
            vec = pos - center
            local_pos = self._local(pos, center, picked.rotation)
            aspect = float(picked.w) / max(0.001, float(picked.h))
            lock = getattr(picked, "lock_aspect", True)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                lock = not lock
            self._drag_start = {
                "start_dist": max(1.0, (vec.x() ** 2 + vec.y() ** 2) ** 0.5),
                "start_angle": math.degrees(math.atan2(vec.y(), vec.x())),
                "start_scale": picked.scale,
                "start_rot": picked.rotation,
                "start_w": float(picked.w),
                "start_h": float(picked.h),
                "aspect": aspect,
                "lock": lock,
                "local_x": local_pos.x(),
                "local_y": local_pos.y(),
            }
            self.update()
            event.accept()
            return
        item = self._item_at(pos.toPoint()) if self._in_content(pos) else None
        if item:
            self.selected_id = item.id
            self._drag_id = item.id
            self._drag_mode = "move"
            fw, fh = self._frame_wh()
            c = self._from_content(QPointF(item.x * fw, item.y * fh))
            self._drag_off = QPointF(pos.x() - c.x(), pos.y() - c.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.item_selected.emit(self.selected_item())
            self.update()
            event.accept()
            return
        corner = self._video_corner_at(pos) if self._video_edit else -1
        rect = self._video_rect()
        on_video = corner >= 0 or (rect is not None and rect.contains(pos))
        if on_video:
            if not self._video_edit:
                self.selected_id = ""
                self.video_clicked.emit()
            center = rect.center()
            dist = max(1.0, ((pos.x() - center.x()) ** 2 + (pos.y() - center.y()) ** 2) ** 0.5)
            self._video_drag = "scale" if corner >= 0 else "move"
            self._video_start = (QPointF(pos), dict(self._video_canvas), dist)
            self.update()
            event.accept()
            return
        # Letterbox / wrapper margin outside the canvas frame — deselect overlays + timeline.
        self.selected_id = ""
        self.item_selected.emit(None)
        self.update()
        event.accept()

    def _drag_video(self, pos: QPointF):
        start_pos, start, start_dist = self._video_start
        state = dict(self._video_canvas)
        w, h = self._frame_wh()
        if self._video_drag == "move":
            x = start["x"] + (pos.x() - start_pos.x()) / w * 100
            y = start["y"] + (pos.y() - start_pos.y()) / h * 100
            snap_x, snap_y = abs(x) < _SNAP_PCT, abs(y) < _SNAP_PCT
            self._snap = (snap_x, snap_y)
            state["x"] = 0 if snap_x else round(x)
            state["y"] = 0 if snap_y else round(y)
        else:
            rect = self._video_rect()
            frame = self.content_rect()
            center = rect.center() if rect is not None else QPointF(frame.center())
            dist = ((pos.x() - center.x()) ** 2 + (pos.y() - center.y()) ** 2) ** 0.5
            state["scale"] = round(start["scale"] * dist / start_dist)
        self._video_canvas = clean_canvas(state)
        self.update()
        self.video_transform.emit({k: self._video_canvas[k] for k in ("scale", "x", "y")})

    def mouseMoveEvent(self, event):
        if self._panning:
            self._update_pan(event.position())
            event.accept()
            return
        if self._hand_active():
            self._sync_tool_cursor()
            event.accept()
            return
        if self._video_drag:
            self._drag_video(event.position())
            return
        if self._drag_id:
            item = next((it for it in self.items if it.id == self._drag_id), None)
            if item:
                self._drag_item(item, event.position())
                self.update()
            return
        picked = self.selected_item()
        handle = self._text_handle_at(picked, event.position()) if picked and picked.kind in HANDLE_KINDS else ""
        hit = self._item_at(event.position().toPoint())
        corner = self._video_corner_at(event.position()) if self._video_edit else -1
        rect = self._video_rect()
        if handle == "rotate":
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif handle in ("handle_tl", "handle_br"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in ("handle_tr", "handle_bl"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle in ("handle_top", "handle_bottom"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in ("handle_left", "handle_right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif hit:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif corner >= 0:
            diag = Qt.CursorShape.SizeFDiagCursor if corner in (0, 2) else Qt.CursorShape.SizeBDiagCursor
            self.setCursor(diag)
        elif self._video_edit and rect is not None and rect.contains(event.position()):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._end_pan()
            event.accept()
            return
        if self._video_drag:
            self._video_drag = ""
            self._snap = (False, False)
            self.update()
            self.video_transform_done.emit()
            return
        if self._drag_id:
            self._drag_id = ""
            self._drag_mode = ""
            self._snap = (False, False)
            self.unsetCursor()
            self.update()
            self.items_changed.emit()

    def _drag_item(self, item: OverlayItem, pos: QPointF):
        rw, rh = self._frame_wh()
        if self._drag_mode == "move" or item.kind not in HANDLE_KINDS:
            local = self._to_content(QPointF(pos.x() - self._drag_off.x(), pos.y() - self._drag_off.y()))
            x = local.x() / rw
            y = local.y() / rh
            snap_x = item.kind in HANDLE_KINDS and abs(x - 0.5) * 100 < _SNAP_PCT
            snap_y = item.kind in HANDLE_KINDS and abs(y - 0.5) * 100 < _SNAP_PCT
            self._snap = (snap_x, snap_y)
            item.x = 0.5 if snap_x else min(0.98, max(0.02, x))
            item.y = 0.5 if snap_y else min(0.98, max(0.02, y))
            self.item_edited.emit(item)
            return

        start = self._drag_start
        center = self._from_content(QPointF(item.x * rw, item.y * rh))
        vec = pos - center

        if self._drag_mode == "rotate":
            start_rot = start["start_rot"]
            start_angle = start["start_angle"]
            angle = start_rot + math.degrees(math.atan2(vec.y(), vec.x())) - start_angle
            angle = (angle + 180.0) % 360.0 - 180.0
            for target in (-180.0, -90.0, 0.0, 90.0, 180.0):
                if abs(angle - target) <= _ROTATE_SNAP:
                    angle = target
            item.rotation = round(angle, 1)
            self.item_edited.emit(item)
            return

        # Resizing handles
        local_pos = self._local(pos, center, item.rotation)
        lock = start.get("lock", True)
        aspect = start.get("aspect", 1.0)
        start_w = start["start_w"]
        start_h = start["start_h"]
        start_dist = start["start_dist"]

        if item.kind == "shape":
            k = max(1.0, (item.scale / 100.0) * rh)

            if self._drag_mode in ("handle_tl", "handle_tr", "handle_br", "handle_bl"):
                if lock:
                    # Locked: scale Width & Height proportionally together ("like scale")
                    dist = max(1.0, (vec.x() ** 2 + vec.y() ** 2) ** 0.5)
                    ratio = dist / start_dist
                    item.w = round(min(2.0, max(0.02, start_w * ratio)), 3)
                    item.h = round(min(2.0, max(0.02, start_h * ratio)), 3)
                else:
                    # Unlocked: freely resize width and height
                    new_box_w = max(8.0, 2.0 * abs(local_pos.x()))
                    new_box_h = max(8.0, 2.0 * abs(local_pos.y()))
                    item.w = round(min(2.0, max(0.02, new_box_w / k)), 3)
                    item.h = round(min(2.0, max(0.02, new_box_h / k)), 3)

            elif self._drag_mode in ("handle_left", "handle_right"):
                new_box_w = max(8.0, 2.0 * abs(local_pos.x()))
                new_w = round(min(2.0, max(0.02, new_box_w / k)), 3)
                item.w = new_w
                if lock and aspect > 0:
                    item.h = round(min(2.0, max(0.02, new_w / aspect)), 3)

            elif self._drag_mode in ("handle_top", "handle_bottom"):
                new_box_h = max(8.0, 2.0 * abs(local_pos.y()))
                new_h = round(min(2.0, max(0.02, new_box_h / k)), 3)
                item.h = new_h
                if lock and aspect > 0:
                    item.w = round(min(2.0, max(0.02, new_h * aspect)), 3)

            self.item_edited.emit(item)

        else:
            dist = max(1.0, (vec.x() ** 2 + vec.y() ** 2) ** 0.5)
            item.scale = int(max(SCALE_RANGE[0], min(SCALE_RANGE[1], round(start["start_scale"] * dist / start_dist))))
            self.item_edited.emit(item)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_V:
            self.set_view_tool("move")
            event.accept()
            return
        if key == Qt.Key.Key_H:
            self.set_view_tool("hand")
            event.accept()
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_selected()
            return
        super().keyPressEvent(event)


class PreviewStageHost(QWidget):
    """Video stage with a transparent overlay canvas on top."""

    def __init__(self, preview: QWidget, overlay: OverlayCanvas, parent=None):
        super().__init__(parent)
        self.setObjectName("preview_stage_wrap")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.preview = preview
        self.overlay = overlay
        preview.setParent(self)
        overlay.setParent(self)
        overlay.raise_()
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if hasattr(overlay, "bind_preview"):
            overlay.bind_preview(preview)
        if hasattr(preview, "aspect_changed"):
            preview.aspect_changed.connect(self.sync_overlay)
        if hasattr(preview, "setFocusPolicy"):
            preview.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def sync_overlay(self, _key=None):
        """Keep overlay full-wrapper; map items to the visible (possibly zoomed) frame."""
        box = self.rect()
        self.overlay.setGeometry(box)
        if hasattr(self.preview, "stage_geometry"):
            # stage_geometry follows view zoom/pan; item x/y stay normalized 0–1.
            self.overlay.set_content_rect(self.preview.stage_geometry())
        else:
            self.overlay.set_content_rect(box)
        self.overlay.raise_()

    # Back-compat for signal connections / callers.
    _sync_overlay_geom = sync_overlay

    def resizeEvent(self, event):
        super().resizeEvent(event)
        box = self.rect()
        self.preview.setGeometry(box)
        self.sync_overlay()
        self.overlay.raise_()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_V:
            if hasattr(self.overlay, "set_view_tool"):
                self.overlay.set_view_tool("move")
            elif hasattr(self.preview, "set_view_tool"):
                self.preview.set_view_tool("move")
            event.accept()
            return
        if key == Qt.Key.Key_H:
            if hasattr(self.overlay, "set_view_tool"):
                self.overlay.set_view_tool("hand")
            elif hasattr(self.preview, "set_view_tool"):
                self.preview.set_view_tool("hand")
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        # Letterbox areas around the frame still zoom the preview.
        delta = event.angleDelta().y()
        if delta != 0 and hasattr(self.preview, "apply_wheel_zoom"):
            self.preview.apply_wheel_zoom(event.globalPosition().toPoint(), delta)
            event.accept()
            return
        super().wheelEvent(event)


class OverlayInspector(QWidget):
    """Refactored Cyber Dark properties inspector for overlays (images, logos, text)."""

    changed = Signal()
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("overlay_inspector")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._item: OverlayItem | None = None
        self._block = False
        self._aspect_ratio = 1.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Header card with icon + type badge + optional filename
        self.header_card = QWidget()
        self.header_card.setObjectName("dub_props_header_card")
        h_lay = QHBoxLayout(self.header_card)
        h_lay.setContentsMargins(6, 4, 6, 4)
        h_lay.setSpacing(6)

        self.kind_icon = QLabel()
        self.kind_icon.setFixedSize(18, 18)
        self.kind_icon.setPixmap(icon("image", color=COLOR_ACCENT_PURPLE, size=16).pixmap(16, 16))

        self.kind_badge = QLabel("OVERLAY")
        self.kind_badge.setObjectName("dub_props_chip")
        self.kind_badge.setStyleSheet(
            f"background-color: rgba(139, 92, 246, 0.15); color: {COLOR_ACCENT_PURPLE}; "
            f"border: 1px solid rgba(139, 92, 246, 0.4); border-radius: 4px; padding: 1px 6px; font-weight: 700; font-size: 10px;"
        )

        self.kind_lbl = QLabel("None selected")
        self.kind_lbl.setObjectName("dub_props_sublabel")
        self.kind_lbl.setStyleSheet(f"color: {COLOR_TEXT_SUB}; font-size: 11px;")

        h_lay.addWidget(self.kind_icon)
        h_lay.addWidget(self.kind_badge)
        h_lay.addWidget(self.kind_lbl, 1)
        lay.addWidget(self.header_card)

        # --- Text Specific Controls (Hidden for Images) ---
        self.text_group_widget = QWidget()
        txt_l = QVBoxLayout(self.text_group_widget)
        txt_l.setContentsMargins(0, 0, 0, 0)
        txt_l.setSpacing(6)

        self.edit_text = QLineEdit()
        self.edit_text.setPlaceholderText("Overlay text")
        self.edit_text.textChanged.connect(self._emit)
        txt_l.addWidget(self.edit_text)

        self.chk_live = QCheckBox("Live caption from script")
        self.chk_live.setObjectName("dub_switch")
        self.chk_live.toggled.connect(self._emit)
        txt_l.addWidget(self.chk_live)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(6)
        self.btn_color = QPushButton("Pick Color")
        self.btn_color.setObjectName("dub_props_ghost_btn")
        self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color.clicked.connect(self._pick_color)
        self.spin_size = ScrubSpinBox()
        self.spin_size.setRange(10, 144)
        self.spin_size.setPrefix("Size ")
        self.spin_size.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_size.valueChanged.connect(self._emit)
        color_row.addWidget(self.btn_color, 1)
        color_row.addWidget(self.spin_size, 1)
        txt_l.addLayout(color_row)
        lay.addWidget(self.text_group_widget)

        # --- Transform Controls (Position, Dimensions, Rotation, Opacity) ---
        self.transform_group_widget = QWidget()
        tr_l = QVBoxLayout(self.transform_group_widget)
        tr_l.setContentsMargins(0, 0, 0, 0)
        tr_l.setSpacing(6)

        # 1. Paired Position (X & Y)
        lbl_pos = QLabel("POSITION")
        lbl_pos.setObjectName("asr_field_label")
        tr_l.addWidget(lbl_pos)

        pos_row = QHBoxLayout()
        pos_row.setContentsMargins(0, 0, 0, 0)
        pos_row.setSpacing(6)
        self.spin_x = ScrubSpinBox()
        self.spin_x.setRange(0, 100)
        self.spin_x.setPrefix("X ")
        self.spin_x.setSuffix("%")
        self.spin_x.setMaximumWidth(16777215)
        self.spin_x.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_x.valueChanged.connect(self._emit)

        self.spin_y = ScrubSpinBox()
        self.spin_y.setRange(0, 100)
        self.spin_y.setPrefix("Y ")
        self.spin_y.setSuffix("%")
        self.spin_y.setMaximumWidth(16777215)
        self.spin_y.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_y.valueChanged.connect(self._emit)

        pos_row.addWidget(self.spin_x, 1)
        pos_row.addWidget(self.spin_y, 1)
        tr_l.addLayout(pos_row)

        # 2. Paired Size (Width & Height) + Aspect Lock
        lbl_size = QLabel("SIZE")
        lbl_size.setObjectName("asr_field_label")
        tr_l.addWidget(lbl_size)

        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(6)
        self.spin_w = ScrubSpinBox()
        self.spin_w.setRange(2, 100)
        self.spin_w.setPrefix("W ")
        self.spin_w.setSuffix("%")
        self.spin_w.setMaximumWidth(16777215)
        self.spin_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_w.valueChanged.connect(self._on_w_changed)

        self.spin_h = ScrubSpinBox()
        self.spin_h.setRange(2, 100)
        self.spin_h.setPrefix("H ")
        self.spin_h.setSuffix("%")
        self.spin_h.setMaximumWidth(16777215)
        self.spin_h.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_h.valueChanged.connect(self._on_h_changed)

        self.btn_lock_ratio = QToolButton()
        self.btn_lock_ratio.setObjectName("timeline_tool_btn")
        self.btn_lock_ratio.setCheckable(True)
        self.btn_lock_ratio.setChecked(True)
        self.btn_lock_ratio.setFixedSize(28, 28)
        self.btn_lock_ratio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lock_ratio.setToolTip("Lock aspect ratio")
        self._sync_lock_icon()
        self.btn_lock_ratio.toggled.connect(self._on_lock_toggled)

        size_row.addWidget(self.spin_w, 1)
        size_row.addWidget(self.spin_h, 1)
        size_row.addWidget(self.btn_lock_ratio)
        tr_l.addLayout(size_row)

        # 3. Paired Rotate & Opacity
        lbl_rot_op = QLabel("ROTATION & OPACITY")
        lbl_rot_op.setObjectName("asr_field_label")
        tr_l.addWidget(lbl_rot_op)

        rot_op_row = QHBoxLayout()
        rot_op_row.setContentsMargins(0, 0, 0, 0)
        rot_op_row.setSpacing(6)

        self.spin_rot = ScrubSpinBox()
        self.spin_rot.setRange(-180, 180)
        self.spin_rot.setPrefix("Rotate ")
        self.spin_rot.setSuffix("°")
        self.spin_rot.setMaximumWidth(16777215)
        self.spin_rot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_rot.valueChanged.connect(self._emit)

        self.spin_op = ScrubSpinBox()
        self.spin_op.setRange(5, 100)
        self.spin_op.setPrefix("Opacity ")
        self.spin_op.setSuffix("%")
        self.spin_op.setMaximumWidth(16777215)
        self.spin_op.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_op.valueChanged.connect(self._emit)

        rot_op_row.addWidget(self.spin_rot, 1)
        rot_op_row.addWidget(self.spin_op, 1)
        tr_l.addLayout(rot_op_row)

        # 4. Quick Actions (Center & Reset)
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 4, 0, 0)
        actions_row.setSpacing(6)

        self.btn_center = QPushButton("Center")
        self.btn_center.setObjectName("dub_props_ghost_btn")
        self.btn_center.setIcon(icon("align-center", color=COLOR_TEXT_SUB, size=12))
        self.btn_center.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_center.setToolTip("Center overlay on the canvas")
        self.btn_center.clicked.connect(self._center_overlay)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setObjectName("dub_props_ghost_btn")
        self.btn_reset.setIcon(icon("refresh", color=COLOR_TEXT_SUB, size=12))
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setToolTip("Reset position, rotation, and opacity")
        self.btn_reset.clicked.connect(self._reset_transform)

        actions_row.addWidget(self.btn_center, 1)
        actions_row.addWidget(self.btn_reset, 1)
        tr_l.addLayout(actions_row)

        lay.addWidget(self.transform_group_widget)

        # --- Danger Remove Button ---
        lay.addSpacing(4)
        self.btn_del = QPushButton("Remove Overlay")
        self.btn_del.setObjectName("dub_danger_btn")
        self.btn_del.setIcon(icon("trash", color="#f87171", size=13))
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.setToolTip("Delete this overlay from the timeline")
        self.btn_del.clicked.connect(self.delete_requested.emit)
        lay.addWidget(self.btn_del)

        self.setEnabled(False)

    def _sync_lock_icon(self):
        locked = self.btn_lock_ratio.isChecked()
        name = "lock" if locked else "unlock"
        col = COLOR_ACCENT_PURPLE if locked else COLOR_TEXT_MUTED
        self.btn_lock_ratio.setIcon(icon(name, color=col, size=14))

    def _on_lock_toggled(self, locked: bool):
        self._sync_lock_icon()
        if self._item:
            self._item.lock_aspect = locked
        if locked and self.spin_h.value() > 0:
            self._aspect_ratio = self.spin_w.value() / max(1, self.spin_h.value())
        self._emit()

    def _on_w_changed(self, new_w: int):
        if not self._block:
            if self.btn_lock_ratio.isChecked() and self._aspect_ratio > 0:
                self._block = True
                new_h = max(2, min(100, int(round(new_w / self._aspect_ratio))))
                self.spin_h.setValue(new_h)
                self._block = False
            elif self.spin_h.value() > 0:
                self._aspect_ratio = new_w / max(1, self.spin_h.value())
        self._emit()

    def _on_h_changed(self, new_h: int):
        if not self._block:
            if self.btn_lock_ratio.isChecked() and self._aspect_ratio > 0:
                self._block = True
                new_w = max(2, min(100, int(round(new_h * self._aspect_ratio))))
                self.spin_w.setValue(new_w)
                self._block = False
            elif new_h > 0:
                self._aspect_ratio = self.spin_w.value() / max(1, new_h)
        self._emit()

    def _center_overlay(self):
        self.spin_x.setValue(50)
        self.spin_y.setValue(50)
        self._emit()

    def _reset_transform(self):
        self.spin_rot.setValue(0)
        self.spin_op.setValue(100)
        self.spin_x.setValue(50)
        self.spin_y.setValue(50)
        self._emit()

    def current(self):
        return self._item

    def bind(self, item: OverlayItem | None):
        self._item = item
        self.setEnabled(item is not None)
        if not item:
            self.kind_lbl.setText("None selected")
            self.kind_badge.setText("OVERLAY")
            return

        self._block = True
        is_text = item.kind in TEXT_KINDS
        self.kind_badge.setText(item.kind.upper())

        if item.path:
            filename = os.path.basename(item.path)
            self.kind_lbl.setText(filename)
            self.kind_lbl.setToolTip(item.path)
        else:
            self.kind_lbl.setText(item.text if is_text else item.kind.title())
            self.kind_lbl.setToolTip("")

        # Icon switch
        icon_name = "type" if is_text else ("image" if item.kind in {"image", "logo"} else "shapes")
        self.kind_icon.setPixmap(icon(icon_name, color=COLOR_ACCENT_PURPLE, size=16).pixmap(16, 16))

        # Show / hide text fields vs image fields
        self.text_group_widget.setVisible(is_text)
        self.chk_live.setVisible(item.kind == "caption")

        self.edit_text.setText(item.text)
        self.chk_live.setChecked(bool(item.live))
        self.spin_size.setValue(int(item.font_size))
        self.spin_rot.setValue(int(item.rotation))
        self.spin_x.setValue(int(item.x * 100))
        self.spin_y.setValue(int(item.y * 100))
        self.spin_w.setValue(int(item.w * 100))
        self.spin_h.setValue(int(item.h * 100))
        self.spin_op.setValue(int(item.opacity))
        self.btn_color.setStyleSheet(f"color:{item.color};")

        self.btn_lock_ratio.setChecked(bool(getattr(item, "lock_aspect", True)))
        self._sync_lock_icon()

        # Update initial aspect ratio
        if item.h > 0:
            self._aspect_ratio = (item.w / item.h)
        else:
            self._aspect_ratio = 1.0

        self._block = False

    def apply_to(self, item: OverlayItem):
        item.text = self.edit_text.text()
        item.live = self.chk_live.isChecked()
        item.font_size = self.spin_size.value()
        item.rotation = float(self.spin_rot.value())
        item.x = self.spin_x.value() / 100.0
        item.y = self.spin_y.value() / 100.0
        item.w = self.spin_w.value() / 100.0
        item.h = self.spin_h.value() / 100.0
        item.lock_aspect = self.btn_lock_ratio.isChecked()
        item.opacity = self.spin_op.value()

    def sync_live(self, item: OverlayItem):
        if self._item is None or getattr(self._item, "id", "") != getattr(item, "id", ""):
            return
        self._block = True
        self.spin_x.setValue(int(item.x * 100))
        self.spin_y.setValue(int(item.y * 100))
        self.spin_w.setValue(int(item.w * 100))
        self.spin_h.setValue(int(item.h * 100))
        self.spin_rot.setValue(int(item.rotation))
        if hasattr(item, "lock_aspect"):
            self.btn_lock_ratio.setChecked(bool(item.lock_aspect))
            self._sync_lock_icon()
        if item.h > 0:
            self._aspect_ratio = item.w / item.h
        self._block = False

    def _pick_color(self):
        if not self._item:
            return
        color = QColorDialog.getColor(QColor(self._item.color), self, "Overlay color")
        if color.isValid():
            self._item.color = color.name()
            self.btn_color.setStyleSheet(f"color:{self._item.color};")
            self.changed.emit()

    def _emit(self, *_):
        if not self._block:
            self.changed.emit()

