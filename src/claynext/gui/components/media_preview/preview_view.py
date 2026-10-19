"""Zoom, pan, and pointer handling for the preview stage."""
from __future__ import annotations

from PySide6.QtCore import (
    Qt,
    QEvent,
    QPoint,
    QRect,
)
from PySide6.QtMultimedia import QMediaPlayer

from claynext.models.canvas import covers_canvas, video_box

from claynext.gui.components.media_preview.const import (
    ZOOM_DEFAULT,
    ZOOM_FIT,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_WHEEL_FACTOR,
)

class PreviewView:
    def view_tool(self) -> str:
        return self._view_tool

    def zoom_factor(self) -> float:
        return float(self._zoom_factor)

    def is_zoomed(self) -> bool:
        """True when the wrapper is not at fit (100%) — zoomed in or out."""
        return abs(self._zoom_factor - ZOOM_FIT) > 0.01

    def can_pan(self) -> bool:
        return abs(self._zoom_factor - ZOOM_FIT) > 0.01

    def set_view_tool(self, tool: str, *, emit: bool = True):
        tool = "hand" if tool == "hand" else "move"
        if tool == self._view_tool:
            self._sync_view_cursor()
            return
        self._view_tool = tool
        if self._dragging and tool != "hand":
            self._dragging = False
        self._sync_view_cursor()
        if emit:
            self.view_tool_changed.emit(tool)

    def _hand_active(self) -> bool:
        return self._view_tool == "hand"

    def _sync_view_cursor(self):
        if self._dragging:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._hand_active():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

    def begin_hand_pan(self, pos: QPoint):
        """Start a hand-pan from the overlay (global tool routing)."""
        if not self.can_pan():
            return False
        self._dragging = True
        self._drag_start_pos = QPoint(pos)
        self._drag_start_pan = (self._pan_x, self._pan_y)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        return True

    def update_hand_pan(self, pos: QPoint):
        if not self._dragging:
            return
        delta = pos - self._drag_start_pos
        self._pan_x = self._drag_start_pan[0] + delta.x()
        self._pan_y = self._drag_start_pan[1] + delta.y()
        self._apply_zoom_pan(emit=False)

    def end_hand_pan(self):
        if not self._dragging:
            return
        self._dragging = False
        self._apply_zoom_pan(emit=True)
        self._sync_view_cursor()

    def apply_wheel_zoom(self, global_pos: QPoint, angle_delta_y: int):
        """Zoom toward a global cursor point (from overlay / stage host)."""
        if angle_delta_y == 0:
            return
        factor = ZOOM_WHEEL_FACTOR if angle_delta_y > 0 else (1.0 / ZOOM_WHEEL_FACTOR)
        local = self.mapFromGlobal(global_pos)
        self.zoom_by(factor, local)

    def stage_geometry(self) -> QRect:
        """Visible project-canvas rect in wrapper coordinates (follows view zoom/pan)."""
        return self.canvas_frame.geometry()

    def fit_geometry(self) -> QRect:
        """100% fit rect for the project canvas — independent of view zoom."""
        r = self._fit_rect
        return QRect(r) if r.width() > 0 and r.height() > 0 else self.canvas_frame.geometry()

    def video_geometry(self) -> QRect:
        """Video rect relative to the canvas frame."""
        return self.stage.geometry()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_fs_window", None) and event.type() == QEvent.Type.Close:
            self.exit_fullscreen()
            return True

        if event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta != 0:
                factor = ZOOM_WHEEL_FACTOR if delta > 0 else (1.0 / ZOOM_WHEEL_FACTOR)
                pos = self.mapFromGlobal(event.globalPosition().toPoint())
                self.zoom_by(factor, pos)
                return True

        return super().eventFilter(obj, event)

    def reset_zoom(self):
        changed = abs(self._zoom_factor - ZOOM_FIT) > 0.001 or self._pan_x or self._pan_y
        self._zoom_factor = ZOOM_FIT
        self._pan_x = 0
        self._pan_y = 0
        self.unsetCursor()
        self._update_stage_bounds()
        if changed:
            self.zoom_changed.emit(self._zoom_factor)

    def zoom_by(self, factor: float, center_pt: QPoint | None = None):
        old_zoom = self._zoom_factor
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, old_zoom * float(factor)))
        # Snap near fit / default so 100% and 75% are easy to hit with the wheel.
        if abs(new_zoom - ZOOM_FIT) < 0.02:
            new_zoom = ZOOM_FIT
        elif abs(new_zoom - ZOOM_DEFAULT) < 0.02:
            new_zoom = ZOOM_DEFAULT
        if abs(new_zoom - old_zoom) < 0.001:
            return

        self._zoom_factor = new_zoom
        if abs(new_zoom - ZOOM_FIT) < 0.001:
            self._pan_x = 0
            self._pan_y = 0
        elif center_pt is not None:
            w, h = self.width(), self.height()
            cx, cy = w / 2.0, h / 2.0
            mx, my = center_pt.x() - cx, center_pt.y() - cy
            scale_ratio = (new_zoom / max(0.001, old_zoom)) - 1.0
            self._pan_x -= int(mx * scale_ratio)
            self._pan_y -= int(my * scale_ratio)

        self._update_stage_bounds()
        self.zoom_changed.emit(self._zoom_factor)

    def _update_stage_bounds(self):
        self._apply_zoom_pan(emit=True)

    def _compute_fit_rect(self) -> QRect:
        """Project-canvas rect at 100% fit inside the wrapper (no view zoom)."""
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return QRect()

        if self._aspect_key in ("fill", "cover"):
            ratio = None
        else:
            ratio = self._custom_ratio or self._video_natural_ratio

        if ratio is None or ratio <= 0:
            return QRect(0, 0, w, h)
        if w / h > ratio:
            base_h = h
            base_w = int(h * ratio)
            return QRect((w - base_w) // 2, 0, max(1, base_w), max(1, base_h))
        base_w = w
        base_h = int(w / ratio)
        return QRect(0, (h - base_h) // 2, max(1, base_w), max(1, base_h))

    def _apply_zoom_pan(self, *, emit: bool = True):
        """Place the frame for view zoom/pan. Does not change project canvas values.

        ``emit=False`` skips heavy bg work mid-drag.
        """
        fit = self._compute_fit_rect()
        if fit.width() <= 0 or fit.height() <= 0:
            return
        self._fit_rect = QRect(fit)

        w, h = self.width(), self.height()
        base_x, base_y = fit.x(), fit.y()
        base_w, base_h = fit.width(), fit.height()

        zoom = max(ZOOM_MIN, min(ZOOM_MAX, float(self._zoom_factor)))
        self._zoom_factor = zoom
        zoomed_w = max(1, int(round(base_w * zoom)))
        zoomed_h = max(1, int(round(base_h * zoom)))

        prev_geom = self.canvas_frame.geometry()

        if abs(zoom - ZOOM_FIT) < 0.001:
            self._pan_x = 0
            self._pan_y = 0
            self.canvas_frame.setGeometry(base_x, base_y, base_w, base_h)
        else:
            # Zoomed in: pan within the magnified frame.
            # Zoomed out: keep the mini frame inside the preview wrapper.
            if zoom > ZOOM_FIT:
                max_pan_x = max(0, (zoomed_w - base_w) // 2)
                max_pan_y = max(0, (zoomed_h - base_h) // 2)
            else:
                max_pan_x = max(0, (w - zoomed_w) // 2)
                max_pan_y = max(0, (h - zoomed_h) // 2)
            self._pan_x = max(-max_pan_x, min(max_pan_x, self._pan_x))
            self._pan_y = max(-max_pan_y, min(max_pan_y, self._pan_y))

            stage_cx = base_x + base_w // 2 + self._pan_x
            stage_cy = base_y + base_h // 2 + self._pan_y
            stage_x = stage_cx - zoomed_w // 2
            stage_y = stage_cy - zoomed_h // 2
            self.canvas_frame.setGeometry(stage_x, stage_y, zoomed_w, zoomed_h)

        self._layout_video()
        # Rescale poster when the view size changes so it stays locked to the frame.
        new_geom = self.canvas_frame.geometry()
        if (
            self._path
            and self._is_video
            and self.stage.currentWidget() is self.poster
            and new_geom.size() != prev_geom.size()
        ):
            self._paint_poster()
        # Sync overlay content_rect to the visible frame (view zoom only).
        self.aspect_changed.emit(self._aspect_key)
        if emit:
            self._update_frame_bg()

    def _layout_video(self):
        cw, ch = self.canvas_frame.width(), self.canvas_frame.height()
        ratio = self._video_natural_ratio
        if self._aspect_key in ("fill", "cover") or not self._is_video or not ratio:
            self.stage.setGeometry(0, 0, max(1, cw), max(1, ch))
            self._canvas_covered = True
            return
        # video_box already sizes the rect to the source aspect + canvas transform —
        # fill that rect exactly so a second letterbox cannot drift under view zoom.
        x, y, w, h = video_box(cw, ch, ratio, self._canvas)
        self.stage.setGeometry(int(round(x)), int(round(y)), max(1, int(round(w))), max(1, int(round(h))))
        self._canvas_covered = covers_canvas(cw, ch, ratio, self._canvas)
        if self._canvas_active:
            self.video.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta != 0:
            factor = ZOOM_WHEEL_FACTOR if delta > 0 else (1.0 / ZOOM_WHEEL_FACTOR)
            self.zoom_by(factor, event.position().toPoint())
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        # Hand tool or middle-mouse pans when zoomed in or out.
        want_pan = event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._hand_active()
        )
        if want_pan and self.can_pan():
            self.begin_hand_pan(event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_dragging", False):
            self.update_hand_pan(event.position().toPoint())
            event.accept()
            return
        self._sync_view_cursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, "_dragging", False):
            self.end_hand_pan()
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_zoomed():
                self.reset_zoom()
                event.accept()
                return
            elif self._path:
                self.toggle_fullscreen()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_stage_bounds()
        if (
            self._path
            and self._is_video
            and self.stage.currentWidget() is self.poster
            and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        ):
            self._show_poster(self._path)
