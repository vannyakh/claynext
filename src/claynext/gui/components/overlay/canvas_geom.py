"""Item boxes, handles, and the selection toolbar."""
from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF
from PySide6.QtGui import QPixmap, QTransform

from claynext.gui.components.overlay.const import (
    HANDLE_KINDS, HANDLE_R, MEDIA_KINDS, ROTATE_GAP, TOOL_GAP, TOOL_NAMES, TOOL_SIZE,
)
from claynext.gui.components.overlay.item import OverlayItem
from claynext.gui.components.shape_render import shape_px
from claynext.gui.components.text_render import caption_width, fit_caption, item_box, wrap_text
from claynext.models.text_style import anim_frame

class CanvasGeom:
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

    def _pixmap(self, path: str) -> QPixmap | None:
        """Load a logo or image once and reuse it while the overlay stays on screen."""
        if not path or not os.path.isfile(path):
            return None
        pix = self._pix.get(path)
        if pix is None:
            pix = QPixmap(path)
            self._pix[path] = pix
        return None if pix.isNull() else pix

    def _pixel_aspect(self, item: OverlayItem) -> float | None:
        if item.kind not in MEDIA_KINDS:
            return None
        pix = self._pixmap(item.path)
        if pix is None or pix.height() <= 0:
            return None
        return pix.width() / float(pix.height())

    def _logo_box(self, item: OverlayItem) -> QRectF:
        """Local frame around the picture. Locked logos keep the image aspect, so the frame hugs it."""
        rw, rh = self._frame_wh()
        bw = max(8.0, float(item.w) * rw)
        bh = max(8.0, float(item.h) * rh)
        aspect = self._pixel_aspect(item)
        if aspect and getattr(item, "lock_aspect", True):
            box_aspect = bw / max(1.0, bh)
            if box_aspect > aspect:
                bw = bh * aspect
            else:
                bh = bw / aspect
        return QRectF(-bw / 2.0, -bh / 2.0, bw, bh)

    def _box_for(self, item: OverlayItem, style: dict, text: str = "") -> QRectF:
        _fw, fh = self._frame_wh()
        if item.kind in {"shape", "mask"}:
            w, h = shape_px(style, item.w, item.h, fh)
            return QRectF(-w / 2, -h / 2, w, h)
        if item.kind in MEDIA_KINDS:
            return self._logo_box(item)
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
        reach = HANDLE_R + 5
        knob = QPointF(0, box.bottom() + ROTATE_GAP)
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
        if item.kind in {"shape", "mask"} | MEDIA_KINDS:
            if abs(local.y() - box.top()) <= reach and abs(local.x()) <= reach + 8:
                return "handle_top"
            if abs(local.y() - box.bottom()) <= reach and abs(local.x()) <= reach + 8:
                return "handle_bottom"
            if abs(local.x() - box.left()) <= reach and abs(local.y()) <= reach + 8:
                return "handle_left"
            if abs(local.x() - box.right()) <= reach and abs(local.y()) <= reach + 8:
                return "handle_right"
        return ""

    def _toolbar_rects(self, item: OverlayItem) -> dict[str, QRectF]:
        """Upright delete / eye / more buttons sitting above the selection frame."""
        center, box, _style, _text = self._text_geom(item)
        mapped = QTransform().translate(center.x(), center.y()).rotate(item.rotation).mapRect(box)
        total = len(TOOL_NAMES) * TOOL_SIZE + (len(TOOL_NAMES) - 1) * TOOL_GAP
        x = mapped.center().x() - total / 2.0
        y = mapped.top() - 10.0 - TOOL_SIZE
        frame = self.content_rect()
        if y < frame.top() + 4:
            y = mapped.bottom() + ROTATE_GAP + HANDLE_R + 14
        return {
            name: QRectF(x + i * (TOOL_SIZE + TOOL_GAP), y, TOOL_SIZE, TOOL_SIZE)
            for i, name in enumerate(TOOL_NAMES)
        }

    def _tool_at(self, item: OverlayItem | None, pos: QPointF) -> str:
        if item is None or item.id != self.selected_id:
            return ""
        for name, rect in self._toolbar_rects(item).items():
            if rect.adjusted(-3, -3, 3, 3).contains(pos):
                return name
        return ""

    def _rect_for(self, item: OverlayItem) -> QRect:
        rw, rh = self._frame_wh()
        w = max(36, int(item.w * rw))
        h = max(24, int(item.h * rh))
        center = self._from_content(QPointF(item.x * rw, item.y * rh))
        cx, cy = int(center.x()), int(center.y())
        return QRect(cx - w // 2, cy - h // 2, w, h)

    def _item_at(self, pos: QPoint) -> OverlayItem | None:
        for item in reversed(self.items):
            if item.hidden and item.id != self.selected_id:
                continue
            if item.kind in HANDLE_KINDS:
                center, box, _style, _text = self._text_geom(item)
                if box.adjusted(-4, -4, 4, 4).contains(self._local(QPointF(pos), center, item.rotation)):
                    return item
            elif self._rect_for(item).adjusted(-4, -4, 4, 4).contains(pos):
                return item
        return None
