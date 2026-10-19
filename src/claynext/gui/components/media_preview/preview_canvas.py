"""Canvas, aspect, fullscreen, and poster painting."""
from __future__ import annotations

import os
import time

from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import (
    QKeySequence,
    QShortcut,
    QPixmap,
    QImage,
)

from claynext.constants.theme_constants import COLOR_BG_CARD
from claynext.models.adjust import clean_adjust
from claynext.models.canvas import DEFAULT_CANVAS, clean_canvas, ratio_value
from claynext.models.thumbnails import pixmap_for

from claynext.gui.components.media_preview.const import FULLSCREEN_BG
from claynext.gui.components.media_preview.image import _fill_panel, blur_image, grade_image

class PreviewCanvas:
    def canvas_state(self) -> dict:
        return dict(self._canvas)

    def video_ratio(self) -> float | None:
        return self._video_natural_ratio if self._is_video else None

    def canvas_covered(self) -> bool:
        return self._canvas_covered

    def current_frame_image(self) -> QImage | None:
        """The active video frame as QImage (or poster thumbnail) for live blur / overlays."""
        if hasattr(self, "video") and hasattr(self.video, "_frame") and not self.video._frame.isNull():
            return self.video._frame
        if hasattr(self, "poster") and self.poster.pixmap() and not self.poster.pixmap().isNull():
            return self.poster.pixmap().toImage()
        return None

    def set_canvas(self, canvas: dict | None, *, active: bool = True):
        """Apply a project canvas (ratio, video transform, background). None restores the plain player."""
        self._canvas = clean_canvas(canvas)
        self._canvas_active = bool(active and canvas is not None)
        ratio_key = self._canvas["ratio"]
        self._aspect_key = "fit" if ratio_key == "original" else ratio_key
        self._custom_ratio = ratio_value(ratio_key, None)
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        if self._canvas["bg"] == "blur" and self._blur_src.isNull():
            self._seed_blur_source()
        self._update_stage_bounds()
        pb = getattr(self, "_playback_widget", None)
        if pb is not None:
            pb.sync_canvas(self._aspect_key, self._canvas["bg"])

    def edit_canvas(self, **fields):
        """Canvas change made from the player chrome; applied and announced via canvas_edited."""
        state = dict(self._canvas)
        state.update(fields)
        self.set_canvas(state, active=self._canvas_active)
        self.canvas_edited.emit(self.canvas_state())

    def set_frame_bg_mode(self, mode: str, extra: str = ""):
        fields = {"bg": {"black": "none"}.get(mode, mode)}
        if mode == "color" and extra:
            fields["color"] = extra
        self.edit_canvas(**fields)

    def _seed_blur_source(self):
        pix = pixmap_for(self._path, QSize(320, 180)) if self._path and self._is_video else None
        if pix is not None and not pix.isNull():
            self._set_blur_source(pix.toImage())

    def _set_blur_source(self, image: QImage):
        if image.isNull():
            return
        self._blur_src = image.scaled(
            320, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
        )
        self._update_frame_bg()

    def _on_video_frame(self, image: QImage):
        if self._canvas["bg"] != "blur" or self._canvas_covered:
            return
        now = time.monotonic()
        if now - self._blur_clock < 0.25:
            return
        self._blur_clock = now
        self._set_blur_source(image)

    def set_video_adjust(self, adjust: dict | None):
        """Live colour grade on the player frames and poster."""
        value = clean_adjust(adjust)
        if value == self._adjust:
            return
        self._adjust = value
        self.video.set_adjust(value)
        if self._path and self._is_video and self.stage.currentWidget() is self.poster:
            self._show_poster(self._path)
        self._update_frame_bg()

    def set_video_effects(self, spans: list[dict], now_ms: int):
        self.video.set_effects(spans, now_ms)

    def _update_frame_bg(self):
        frame = self.canvas_frame
        w, h = frame.width(), frame.height()
        if w <= 0 or h <= 0:
            return
        bg = self._canvas["bg"]
        fill = FULLSCREEN_BG if self._fullscreen else COLOR_BG_CARD
        if self._canvas_active or bg != "none":
            fill = self._canvas["color"] if bg == "color" else DEFAULT_CANVAS["color"]
        _fill_panel(frame, fill)
        if bg != "blur" or self._canvas_covered or self._blur_src.isNull():
            self.bg_label.hide()
            return
        self.bg_label.setGeometry(0, 0, w, h)
        source = grade_image(self._blur_src, self._adjust)
        self.bg_label.setPixmap(blur_image(source, QSize(w, h), self._canvas["blur"]))
        self.bg_label.show()
        self.bg_label.lower()

    def set_aspect_ratio_mode(self, key: str):
        self._aspect_key = key
        preset = self.ASPECT_PRESETS.get(key)
        if not preset:
            return
        custom_ratio, mode = preset
        self._custom_ratio = custom_ratio
        if mode is not None:
            self.video.setAspectRatioMode(mode)
        if key not in ("fill", "cover"):
            self._canvas["ratio"] = "original" if key == "fit" else key
        self._update_stage_bounds()
        if self._path and self._is_video and self.stage.currentWidget() is self.poster:
            self._show_poster(self._path)
        self.aspect_changed.emit(key)

    def set_keep_aspect(self, keep: bool):
        self.set_aspect_ratio_mode("fit" if keep else "fill")

    def toggle_fullscreen(self):
        if self._fullscreen:
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    def enter_fullscreen(self):
        if self._fullscreen:
            return
        self._fullscreen = True

        self._fs_window = QWidget(None, Qt.WindowType.Window)
        self._fs_window.setObjectName("media_fs_window")
        self._fs_window.setWindowTitle(self._title or "Player")
        _fill_panel(self._fs_window, FULLSCREEN_BG)
        _fill_panel(self, FULLSCREEN_BG)
        fs_layout = QVBoxLayout(self._fs_window)
        fs_layout.setContentsMargins(0, 0, 0, 0)
        fs_layout.setSpacing(0)

        target = self._fs_target[0] if self._fs_target else self
        target.setStyleSheet(
            f"#media_preview, #preview_stage_wrap {{ background-color: {FULLSCREEN_BG}; border-radius: 0; }}"
        )
        target.setParent(self._fs_window)
        fs_layout.addWidget(target, 1)
        target.show()

        pb = getattr(self, "_playback_widget", None)
        if pb is not None:
            pb.setParent(self._fs_window)
            fs_layout.addWidget(pb, 0)
            pb.set_fullscreen_mode(True)
            pb.show()

        self._fs_window.installEventFilter(self)
        esc = QShortcut(QKeySequence("Esc"), self._fs_window)
        esc.activated.connect(self.exit_fullscreen)
        self._fs_esc = esc

        self._fs_window.showFullScreen()
        self._update_stage_bounds()
        self.fullscreen_changed.emit(True)

    def exit_fullscreen(self):
        if not self._fullscreen or not self._fs_window:
            return
        self._fullscreen = False

        self._fs_window.hide()
        _fill_panel(self, COLOR_BG_CARD)

        if self._fs_target:
            target, host, index = self._fs_target
        else:
            target = self
            host = getattr(self, "_dock_host", None)
            index = getattr(self, "_dock_index", 0)
        target.setStyleSheet("")
        if isinstance(host, QSplitter):
            host.insertWidget(index, target)
        elif host is not None:
            target.setParent(host)
            lay = host.layout()
            if lay is not None:
                lay.insertWidget(index, target, 1)
        target.show()

        pb = getattr(self, "_playback_widget", None)
        if pb is not None:
            pb_host = getattr(pb, "_dock_host", None)
            pb_index = getattr(pb, "_dock_index", 1)
            if isinstance(pb_host, QSplitter):
                pb_host.insertWidget(pb_index, pb)
                pb.show()
            elif pb_host is not None:
                pb.setParent(pb_host)
                lay = pb_host.layout()
                if lay is not None:
                    lay.insertWidget(pb_index, pb, 0)
                pb.show()
            pb.set_fullscreen_mode(False)

        self._fs_window.deleteLater()
        self._fs_window = None
        self._update_stage_bounds()
        self.fullscreen_changed.emit(False)

    def _show_poster(self, path: str):
        pix = pixmap_for(path, QSize(480, 270))
        if pix.isNull():
            self.poster.clear()
            self.poster.setText(os.path.basename(path))
            self.stage.setCurrentWidget(self.poster)
            return

        if pix.width() > 0 and pix.height() > 0:
            new_ratio = float(pix.width()) / float(pix.height())
            if (
                self._video_natural_ratio is None
                or abs(self._video_natural_ratio - new_ratio) > 0.001
            ):
                self._video_natural_ratio = new_ratio
                self._update_stage_bounds()

        self._paint_poster(pix)
        self.stage.setCurrentWidget(self.poster)
        if self._canvas["bg"] == "blur":
            self._set_blur_source(pix.toImage())

    def _paint_poster(self, pix: QPixmap | None = None):
        """Scale the poster into the current stage without changing stage bounds."""
        if pix is None or pix.isNull():
            if not self._path:
                return
            pix = pixmap_for(self._path, QSize(480, 270))
            if pix.isNull():
                return
        target_size = self.stage.size() if self.stage.width() > 40 else QSize(480, 270)
        # Stage is already the video rect — fill it (same as live video under canvas).
        mode = (
            Qt.AspectRatioMode.IgnoreAspectRatio
            if self._canvas_active
            else Qt.AspectRatioMode.KeepAspectRatio
        )
        scaled = pix.scaled(target_size, mode, Qt.TransformationMode.SmoothTransformation)
        if self._adjust:
            scaled = QPixmap.fromImage(grade_image(scaled.toImage(), self._adjust))
        self.poster.setPixmap(scaled)
