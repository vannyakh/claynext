"""Pointer, wheel, and keyboard handling for the overlay canvas."""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QToolTip

from claynext.gui.components.overlay.const import HANDLE_KINDS, MEDIA_KINDS, ROTATE_SNAP, SNAP_PCT
from claynext.models.canvas import clean_canvas
from claynext.gui.components.overlay.item import OverlayItem
from claynext.models.text_style import SCALE_RANGE

class CanvasInput:
    def leaveEvent(self, event):
        if self._tool_hot:
            self._tool_hot = ""
            QToolTip.hideText()
            self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        preview = self._preview
        if delta != 0 and preview is not None:
            if hasattr(preview, "apply_wheel_zoom"):
                preview.apply_wheel_zoom(event.globalPosition().toPoint(), delta)
            elif hasattr(preview, "zoom_by"):
                from claynext.gui.components.media_preview import ZOOM_WHEEL_FACTOR

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
        if event.button() == Qt.MouseButton.RightButton:
            self._open_item_menu(event)
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
        tool = self._tool_at(picked, pos)
        if tool and picked is not None:
            self._run_tool(picked, tool, event.globalPosition().toPoint())
            event.accept()
            return
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
            media_box = self._logo_box(picked) if picked.kind in MEDIA_KINDS else None
            pix_aspect = self._pixel_aspect(picked) if picked.kind in MEDIA_KINDS else None
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
                "box_w": media_box.width() if media_box is not None else 0.0,
                "box_h": media_box.height() if media_box is not None else 0.0,
                "pix_aspect": pix_aspect or aspect,
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
            snap_x, snap_y = abs(x) < SNAP_PCT, abs(y) < SNAP_PCT
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
        tool = self._tool_at(picked, event.position())
        if tool != self._tool_hot:
            self._tool_hot = tool
            if tool == "delete":
                tip = "Delete"
            elif tool == "eye":
                tip = "Show" if picked is not None and picked.hidden else "Hide"
            elif tool == "more":
                tip = "Flip and more"
            else:
                tip = ""
            if tip:
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
            else:
                QToolTip.hideText()
            self.update()
        if tool:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
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
            snap_x = item.kind in HANDLE_KINDS and abs(x - 0.5) * 100 < SNAP_PCT
            snap_y = item.kind in HANDLE_KINDS and abs(y - 0.5) * 100 < SNAP_PCT
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
                if abs(angle - target) <= ROTATE_SNAP:
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

        if item.kind in {"shape", "mask"}:
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

        elif item.kind in MEDIA_KINDS:
            self._resize_media(item, local_pos, vec, start)

        else:
            dist = max(1.0, (vec.x() ** 2 + vec.y() ** 2) ** 0.5)
            item.scale = int(max(SCALE_RANGE[0], min(SCALE_RANGE[1], round(start["start_scale"] * dist / start_dist))))
            self.item_edited.emit(item)

    def _resize_media(self, item: OverlayItem, local_pos: QPointF, vec: QPointF, start: dict):
        """Resize a logo or image from its frame. Locked aspect keeps the picture's shape."""
        rw, rh = self._frame_wh()
        lock = bool(start.get("lock", True))
        aspect = float(start.get("pix_aspect") or start.get("aspect") or 1.0)
        box_w = max(8.0, float(start.get("box_w") or 36))
        box_h = max(8.0, float(start.get("box_h") or 24))
        start_dist = max(1.0, float(start.get("start_dist") or 1.0))

        def apply(pw: float, ph: float):
            item.w = round(min(2.0, max(0.02, pw / max(1.0, rw))), 3)
            item.h = round(min(2.0, max(0.02, ph / max(1.0, rh))), 3)

        mode = self._drag_mode
        if mode in ("handle_tl", "handle_tr", "handle_br", "handle_bl"):
            if lock:
                dist = max(1.0, (vec.x() ** 2 + vec.y() ** 2) ** 0.5)
                ratio = dist / start_dist
                apply(box_w * ratio, box_h * ratio)
            else:
                apply(max(8.0, 2.0 * abs(local_pos.x())), max(8.0, 2.0 * abs(local_pos.y())))
        elif mode in ("handle_left", "handle_right"):
            pw = max(8.0, 2.0 * abs(local_pos.x()))
            ph = pw / aspect if lock and aspect > 0 else box_h
            apply(pw, ph)
        elif mode in ("handle_top", "handle_bottom"):
            ph = max(8.0, 2.0 * abs(local_pos.y()))
            pw = ph * aspect if lock and aspect > 0 else box_w
            apply(pw, ph)
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
            self._request_delete()
            return
        super().keyPressEvent(event)
