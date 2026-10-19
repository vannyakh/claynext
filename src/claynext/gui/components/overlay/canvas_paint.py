"""Draw the video frame, overlays, selection chrome, and toolbar."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from claynext.constants.theme_constants import (
    COLOR_ACCENT_CYAN, COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_DARK, COLOR_BORDER, COLOR_TEXT_MAIN,
)
from claynext.gui.components.overlay.const import HANDLE_R, MEDIA_KINDS, ROTATE_GAP, TEXT_KINDS
from claynext.gui.components.overlay.item import OverlayItem
from claynext.gui.components.render.shape import paint_shape
from claynext.gui.components.render.text import paint_text
from claynext.gui.icons import icon

class CanvasPaint:
    def _paint_snap_guides(self, p: QPainter):
        snap_x, snap_y = self._snap
        if not snap_x and not snap_y:
            return
        frame = self.content_rect()
        p.setPen(QPen(QColor(COLOR_ACCENT_CYAN), 1, Qt.PenStyle.DashLine))
        if snap_x:
            mid_x = frame.center().x()
            p.drawLine(QPointF(mid_x, frame.top()), QPointF(mid_x, frame.bottom()))
        if snap_y:
            mid_y = frame.center().y()
            p.drawLine(QPointF(frame.left(), mid_y), QPointF(frame.right(), mid_y))

    def _paint_video_frame(self, p: QPainter):
        rect = self._video_rect()
        if rect is None or not self._video_edit:
            return
        if self._video_drag == "move":
            self._paint_snap_guides(p)
        p.setPen(QPen(QColor(COLOR_TEXT_MAIN), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect)
        p.setPen(QPen(QColor(COLOR_BG_DARK), 1))
        p.setBrush(QColor(COLOR_TEXT_MAIN))
        for corner in (rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()):
            p.drawEllipse(corner, HANDLE_R, HANDLE_R)

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
        selected = None
        for item in self.items:
            if item.hidden and item.id != self.selected_id:
                continue
            if item.kind in TEXT_KINDS:
                center, box, style, shown = self._text_geom(item)
                if shown.strip() and not item.hidden:
                    p.save()
                    self._apply_flip(p, item, center)
                    paint_text(p, style, shown, center, fh, item.rotation, self._frame_for(item, style))
                    p.restore()
                if item.id == self.selected_id:
                    self._paint_text_chrome(p, item, center, box)
                    selected = item
                continue
            if item.kind in {"shape", "mask"}:
                center, box, style, _text = self._text_geom(item)
                if not item.hidden:
                    p.save()
                    self._apply_flip(p, item, center)
                    paint_style = dict(style)
                    paint_style["path"] = item.path
                    paint_shape(
                        p,
                        paint_style,
                        item.shape,
                        (box.width(), box.height()),
                        center,
                        fh,
                        item.rotation,
                        self._frame_for(item, style),
                        bg_image=curr_frame_img,
                        canvas_rect=canvas_rect_f,
                    )
                    p.restore()
                if item.id == self.selected_id:
                    self._paint_text_chrome(p, item, center, box)
                    selected = item
                continue
            if item.kind in MEDIA_KINDS:
                center, box, _style, _shown = self._text_geom(item)
                if not item.hidden:
                    p.save()
                    p.translate(center)
                    p.rotate(item.rotation)
                    if item.flip_h or item.flip_v:
                        p.scale(-1.0 if item.flip_h else 1.0, -1.0 if item.flip_v else 1.0)
                    p.setOpacity(max(0.08, item.opacity / 100.0))
                    self._paint_media(p, item, box)
                    p.restore()
                if item.id == self.selected_id:
                    self._paint_text_chrome(p, item, center, box)
                    selected = item
                continue
            if item.hidden:
                continue
            rect = self._rect_for(item)
            p.save()
            p.translate(rect.center())
            p.rotate(item.rotation)
            p.translate(-rect.center())
            p.setOpacity(max(0.08, item.opacity / 100.0))
            self._paint_item(p, item, rect)
            p.restore()
        if selected is not None:
            p.setClipping(False)
            self._paint_toolbar(p, selected)
        if getattr(self, "_capture_zone_active", False):
            self._paint_capture_zone(p)
        p.end()

    def _apply_flip(self, p: QPainter, item: OverlayItem, center: QPointF):
        if item.flip_h or item.flip_v:
            p.translate(center)
            p.scale(-1.0 if item.flip_h else 1.0, -1.0 if item.flip_v else 1.0)
            p.translate(-center)

    def _paint_toolbar(self, p: QPainter, item: OverlayItem):
        for name, rect in self._toolbar_rects(item).items():
            hot = name == self._tool_hot
            p.setPen(QPen(QColor(COLOR_ACCENT_CYAN if hot else COLOR_BORDER), 1))
            p.setBrush(QColor(COLOR_BG_CARD_HOVER if hot else COLOR_BG_CARD))
            p.drawRoundedRect(rect, 6, 6)
            if name == "delete":
                glyph, color = "trash", "#f87171"
            elif name == "eye":
                glyph, color = ("eye-off" if item.hidden else "eye"), COLOR_TEXT_MAIN
            else:
                glyph, color = "more", COLOR_TEXT_MAIN
            pix = icon(glyph, color=color, size=14).pixmap(QSize(14, 14))
            p.drawPixmap(
                QPointF(rect.center().x() - pix.width() / pix.devicePixelRatio() / 2.0,
                        rect.center().y() - pix.height() / pix.devicePixelRatio() / 2.0),
                pix,
            )

    def _paint_text_chrome(self, p: QPainter, item: OverlayItem, center: QPointF, box: QRectF):
        if self._drag_mode == "move":
            self._paint_snap_guides(p)
        p.save()
        p.translate(center)
        p.rotate(item.rotation)
        if item.kind in MEDIA_KINDS:
            p.setPen(QPen(QColor(COLOR_ACCENT_CYAN), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box, 8, 8)
        else:
            p.setPen(QPen(QColor(COLOR_TEXT_MAIN), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(box)
        p.setPen(QPen(QColor(COLOR_BG_DARK), 1))
        p.setBrush(QColor(COLOR_TEXT_MAIN))
        for corner in (box.topLeft(), box.topRight(), box.bottomRight(), box.bottomLeft()):
            p.drawEllipse(corner, HANDLE_R, HANDLE_R)
        if item.kind in {"shape", "mask"} | MEDIA_KINDS:
            for mid_x, mid_y, pw, ph in (
                (0, box.top(), 10, 4),
                (0, box.bottom(), 10, 4),
                (box.left(), 0, 4, 10),
                (box.right(), 0, 4, 10),
            ):
                p.drawRoundedRect(QRectF(mid_x - pw / 2, mid_y - ph / 2, pw, ph), 1.5, 1.5)
        knob = QPointF(0, box.bottom() + ROTATE_GAP)
        p.setPen(QPen(QColor(COLOR_TEXT_MAIN), 1.2))
        p.drawLine(QPointF(0, box.bottom()), knob - QPointF(0, HANDLE_R + 1))
        p.setBrush(QColor(COLOR_BG_DARK))
        p.drawEllipse(knob, HANDLE_R + 2, HANDLE_R + 2)
        p.drawArc(QRectF(knob.x() - 3.5, knob.y() - 3.5, 7, 7), 30 * 16, 280 * 16)
        p.restore()
        if self._drag_mode == "rotate":
            p.setPen(QColor(COLOR_TEXT_MAIN))
            p.drawText(QRectF(center.x() - 30, center.y() + box.bottom() + ROTATE_GAP + 10, 60, 16),
                       Qt.AlignmentFlag.AlignCenter, f"{item.rotation:.0f}°")

    def _paint_media(self, p: QPainter, item: OverlayItem, box: QRectF):
        """Draw a logo or image so it fills its resize frame."""
        pix = self._pixmap(item.path)
        if pix is not None:
            mode = (
                Qt.AspectRatioMode.KeepAspectRatio
                if getattr(item, "lock_aspect", True)
                else Qt.AspectRatioMode.IgnoreAspectRatio
            )
            scaled = pix.scaled(
                max(1, int(box.width())),
                max(1, int(box.height())),
                mode,
                Qt.TransformationMode.SmoothTransformation,
            )
            target = QRectF(
                box.center().x() - scaled.width() / 2.0,
                box.center().y() - scaled.height() / 2.0,
                scaled.width(),
                scaled.height(),
            )
            p.drawPixmap(target, scaled, QRectF(scaled.rect()))
            return
        self._paint_item(p, item, box.toRect())

    def _paint_item(self, p: QPainter, item: OverlayItem, rect: QRect):
        color = QColor(item.color)
        if item.kind in {"logo", "image"}:
            pix = self._pixmap(item.path)
            if pix is not None:
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

    def _capture_zone_rect(self) -> QRectF | None:
        """Return the current capture zone in canvas pixels."""
        frame = self.content_rect()
        if frame.isEmpty():
            return None
        zone = getattr(self, "_capture_zone", None) or {"x": 0.05, "y": 0.72, "w": 0.90, "h": 0.20}
        fw = float(frame.width())
        fh = float(frame.height())
        zx = frame.left() + float(zone.get("x", 0.05)) * fw
        zy = frame.top() + float(zone.get("y", 0.72)) * fh
        zw = float(zone.get("w", 0.90)) * fw
        zh = float(zone.get("h", 0.20)) * fh
        return QRectF(zx, zy, zw, zh)

    def _paint_capture_zone(self, p: QPainter):
        """Paint the video subtitle capture zone overlay with interactive key point handles."""
        z_rect = self._capture_zone_rect()
        if z_rect is None:
            return
        frame = self.content_rect()
        fw = float(frame.width())
        zone = getattr(self, "_capture_zone", {}) or {}

        p.save()
        p.setClipping(False)

        # 1. Darken the non-selected area outside the capture zone (letterbox mask)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        zx, zy, zw, zh = z_rect.x(), z_rect.y(), z_rect.width(), z_rect.height()
        # Top
        p.drawRect(QRectF(frame.left(), frame.top(), fw, max(0.0, zy - frame.top())))
        # Bottom
        p.drawRect(QRectF(frame.left(), zy + zh, fw, max(0.0, frame.bottom() - (zy + zh))))
        # Left
        p.drawRect(QRectF(frame.left(), zy, max(0.0, zx - frame.left()), zh))
        # Right
        p.drawRect(QRectF(zx + zw, zy, max(0.0, frame.right() - (zx + zw)), zh))

        # 2. Draw capture box boundary
        pen = QPen(QColor("#38bdf8"), 1.8, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(56, 189, 248, 22))  # subtle tint inside zone
        p.drawRect(z_rect)

        # 3. Cinema viewfinder brackets at corners
        bracket_len = min(16.0, zw / 4.0, zh / 4.0)
        p.setPen(QPen(QColor("#00f0ff"), 3.0, Qt.PenStyle.SolidLine))
        # Top-Left
        p.drawLine(QPointF(zx, zy), QPointF(zx + bracket_len, zy))
        p.drawLine(QPointF(zx, zy), QPointF(zx, zy + bracket_len))
        # Top-Right
        p.drawLine(QPointF(zx + zw, zy), QPointF(zx + zw - bracket_len, zy))
        p.drawLine(QPointF(zx + zw, zy), QPointF(zx + zw, zy + bracket_len))
        # Bottom-Left
        p.drawLine(QPointF(zx, zy + zh), QPointF(zx + bracket_len, zy + zh))
        p.drawLine(QPointF(zx, zy + zh), QPointF(zx, zy + zh - bracket_len))
        # Bottom-Right
        p.drawLine(QPointF(zx + zw, zy + zh), QPointF(zx + zw - bracket_len, zy + zh))
        p.drawLine(QPointF(zx + zw, zy + zh), QPointF(zx + zw, zy + zh - bracket_len))

        # 4. Key Point Tracker Handles (4 corners, 4 edges, 1 center)
        handle_r = 5.0
        p.setPen(QPen(QColor("#080c12"), 1.5))
        p.setBrush(QColor("#38bdf8"))
        for pt in (z_rect.topLeft(), z_rect.topRight(), z_rect.bottomLeft(), z_rect.bottomRight()):
            p.drawEllipse(pt, handle_r, handle_r)

        # Edge midpoints
        p.setBrush(QColor("#a855f7"))
        mid_top = QPointF(zx + zw / 2.0, zy)
        mid_bot = QPointF(zx + zw / 2.0, zy + zh)
        mid_left = QPointF(zx, zy + zh / 2.0)
        mid_right = QPointF(zx + zw, zy + zh / 2.0)
        for pt in (mid_top, mid_bot, mid_left, mid_right):
            p.drawRoundedRect(QRectF(pt.x() - 4.5, pt.y() - 4.5, 9, 9), 2, 2)

        # Center target anchor
        center = z_rect.center()
        p.setPen(QPen(QColor("#38bdf8"), 1.5))
        p.setBrush(QColor(56, 189, 248, 60))
        p.drawEllipse(center, 9, 9)
        p.drawLine(QPointF(center.x() - 6, center.y()), QPointF(center.x() + 6, center.y()))
        p.drawLine(QPointF(center.x(), center.y() - 6), QPointF(center.x(), center.y() + 6))

        # 5. Floating Badge & Coordinate HUD
        badge_text = f"🎯 Subtitle Tracker · Y: {int(zone.get('y', 0.72)*100)}% - {int((zone.get('y', 0.72) + zone.get('h', 0.20))*100)}% | W: {int(zone.get('w', 0.90)*100)}%"
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        badge_y = zy - 24 if zy >= frame.top() + 28 else zy + zh + 6
        badge_rect = QRectF(zx, badge_y, min(zw, 320.0), 20)
        p.setPen(QPen(QColor("#233348"), 1))
        p.setBrush(QColor(14, 20, 30, 220))
        p.drawRoundedRect(badge_rect, 4, 4)
        p.setPen(QColor("#e7ecf3"))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        p.restore()
