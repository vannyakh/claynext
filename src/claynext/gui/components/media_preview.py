from claynext.adapters.ffmpeg_adapter import probe_media
import os
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSlider, QFrame,
    QStackedWidget, QSizePolicy, QSplitter, QMenu, QPushButton, QColorDialog
)
from PySide6.QtCore import Qt, QUrl, Signal, Slot, QSize, QEvent, QThreadPool, QPoint, QRect
from PySide6.QtGui import QKeySequence, QShortcut, QAction, QActionGroup, QPixmap, QColor, QPalette, QImage, QPainter
import numpy as np
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from claynext.constants.theme_constants import (
    COLOR_BG_CARD, COLOR_BG_SIDEBAR, COLOR_PRIMARY, COLOR_TEXT_SUB,
)
from claynext.models.adjust import clean_adjust, grade_rgb
from claynext.models.fx import TIMED_EFFECTS, apply_fx
from claynext.gui.icons import icon
from claynext.models.thumbnails import pixmap_for, VIDEO_EXTS
from claynext.adapters.media import ensure_playback_file, ready_playback_path
from claynext.models.canvas import (
    DEFAULT_CANVAS, PREVIEW_BLUR_DIV, clean_canvas, covers_canvas, ratio_value, video_box,
)
from claynext.gui.worker import Worker


_FULLSCREEN_BG = DEFAULT_CANVAS["color"]

# Preview wrapper zoom (wheel / hand pan). 100% = fit; below = mini; above = magnify.
ZOOM_MIN = 0.20
ZOOM_MAX = 1.80
ZOOM_FIT = 1.0
ZOOM_DEFAULT = 0.75  # Startup view zoom (75% of fit)
ZOOM_WHEEL_FACTOR = 1.10


def _fill_panel(widget, color: str) -> None:
    """Paint a playback surface with the panel color so letterbox matches the frame."""
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(color))
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


def grade_image(image: QImage, adjust: dict | None) -> QImage:
    """Colour-grade a QImage with the footage adjustments (live preview approximation)."""
    if not adjust or image.isNull():
        return image
    img = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h, line = img.width(), img.height(), img.bytesPerLine()
    rgb = np.frombuffer(img.constBits(), np.uint8, count=line * h).reshape(h, line)[:, : w * 3].reshape(h, w, 3)
    out = np.ascontiguousarray(grade_rgb(rgb, adjust))
    return QImage(out.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()


def fx_image(image: QImage, spans: list[dict], now_ms: int) -> QImage:
    """Timeline effects and filter looks on a QImage (live preview of fx_filters)."""
    if not spans or image.isNull():
        return image
    img = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h, line = img.width(), img.height(), img.bytesPerLine()
    rgb = np.frombuffer(img.constBits(), np.uint8, count=line * h).reshape(h, line)[:, : w * 3].reshape(h, w, 3)
    out = np.ascontiguousarray(apply_fx(rgb, spans, now_ms))
    return QImage(out.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()


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
        if not frame.isValid():
            return
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
                target.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self._cache = (key, fx_image(grade_image(image, self._adjust), self._fx, self._fx_ms))
        p = QPainter(self)
        p.drawImage(target.topLeft(), self._cache[1])
        p.end()


def blur_image(image: QImage, size: QSize, level: int) -> QPixmap:
    """Cover-crop `image` to `size` and soften it to the canvas blur level."""
    w, h = size.width(), size.height()
    if image.isNull() or w <= 0 or h <= 0:
        return QPixmap()
    smooth = Qt.TransformationMode.SmoothTransformation
    cover = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, smooth)
    cover = cover.copy((cover.width() - w) // 2, (cover.height() - h) // 2, w, h)
    div = PREVIEW_BLUR_DIV.get(level, 18)
    small = cover.scaled(max(2, w // div), max(2, h // div), Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    mid = small.scaled(max(2, w // 4), max(2, h // 4), Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    return QPixmap.fromImage(mid.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, smooth))


class MediaPlaybackWidget(QWidget):
    """Transport bar under the player stage. compact=True matches the preview player."""

    def __init__(self, parent=None, *, compact: bool = False):
        super().__init__(parent)
        self.setObjectName("media_playback")
        # Match dock / shelf panel headers (sidebar chrome, not card body).
        _fill_panel(self, COLOR_BG_SIDEBAR)
        self._preview: MediaPreviewWidget | None = None
        self._seeking = False
        self._compact = compact
        self._current_aspect_key = "fit"
        self._curr_pos = 0
        self._curr_dur = 0
        self._time_format_mode = "compact"
        self._init_ui()
        self.set_enabled(False)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        controls = QFrame()
        controls.setObjectName("media_controls")
        _fill_panel(controls, COLOR_BG_SIDEBAR)
        lay = QVBoxLayout(controls)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(4)

        # Top row: Full-width playback seek progress slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("media_seek")
        self.slider.setRange(0, 0)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.sliderPressed.connect(self._on_seek_start)
        self.slider.sliderReleased.connect(self._on_seek_end)
        self.slider.sliderMoved.connect(self._on_seek_moved)
        lay.addWidget(self.slider)

        # Bottom row: time (left) · play (center) · canvas tools (right)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.btn_stop = self._icon_btn("stop", "Stop")
        self.btn_stop.clicked.connect(self._on_stop)

        self.btn_play = self._icon_btn("play", "Play (Space)")
        self.btn_play.setObjectName("media_play_btn")
        self.btn_play.setFixedSize(28, 28)
        self.btn_play.clicked.connect(self._on_play)

        self.time_badge = QLabel()
        self.time_badge.setObjectName("media_time_badge")
        self.time_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_badge.setTextFormat(Qt.TextFormat.RichText)
        self.time_badge.setToolTip("Current playhead / Duration")

        # Kept for compatibility with any callers expecting pos_lbl / dur_lbl
        self.pos_lbl = QLabel("00:00:00")
        self.pos_lbl.setObjectName("media_time_now")
        self.pos_lbl.hide()
        self.slash_lbl = QLabel("/")
        self.slash_lbl.setObjectName("media_time_lbl")
        self.slash_lbl.hide()
        self.dur_lbl = QLabel("00:00:00")
        self.dur_lbl.setObjectName("media_time_lbl")
        self.dur_lbl.hide()

        left_box = QHBoxLayout()
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(6)
        left_box.addWidget(self.time_badge)
        left_box.addStretch(1)
        row.addLayout(left_box, 1)

        center_box = QHBoxLayout()
        center_box.setContentsMargins(0, 0, 0, 0)
        center_box.setSpacing(6)
        center_box.addStretch(1)
        center_box.addWidget(self.btn_stop)
        center_box.addWidget(self.btn_play)
        center_box.addStretch(1)
        row.addLayout(center_box, 0)

        right_box = QHBoxLayout()
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(4)
        right_box.addStretch(1)

        self.zoom_lbl = QLabel(f"{int(round(ZOOM_DEFAULT * 100))}%")
        self.zoom_lbl.setObjectName("media_zoom_lbl")
        self.zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_lbl.setMinimumWidth(36)
        self.zoom_lbl.setToolTip("Preview zoom 20%–180% · Default 75% · Wheel to zoom · Click to reset 100%")
        self.zoom_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_lbl.installEventFilter(self)

        self.btn_tool_move = self._tool_icon(
            "cursor", "Move tool (V) · Select & transform overlays"
        )
        self.btn_tool_hand = self._tool_icon(
            "grab", "Hand tool (H) · Pan canvas · Middle-drag · Wheel zooms"
        )
        self.btn_tool_move.setCheckable(True)
        self.btn_tool_hand.setCheckable(True)
        self.btn_tool_move.setChecked(True)
        self.btn_tool_move.clicked.connect(lambda: self._set_view_tool("move"))
        self.btn_tool_hand.clicked.connect(lambda: self._set_view_tool("hand"))
        self._paint_tool_icons("move")

        self.btn_mute = self._icon_btn("volume", "Mute audio (M)")
        self.btn_mute.setCheckable(True)
        self.btn_mute.toggled.connect(self._on_mute)

        self.btn_ratio = self._icon_btn("aspect", "Frame · Fit, ratio, and canvas background")
        self.btn_ratio.clicked.connect(self._show_aspect_menu)

        self.btn_fs = self._icon_btn("win-maximize", "Full screen player (F)")
        self.btn_fs.clicked.connect(self._on_fullscreen)

        self._init_playback_menus()

        right_box.addWidget(self.zoom_lbl)
        right_box.addWidget(self.btn_tool_move)
        right_box.addWidget(self.btn_tool_hand)
        right_box.addWidget(self.btn_mute)
        right_box.addWidget(self.btn_ratio)
        right_box.addWidget(self.btn_fs)
        row.addLayout(right_box, 1)

        if self._compact:
            self.btn_stop.hide()

        self.slider.hide()

        lay.addLayout(row)
        root.addWidget(controls)
        self._update_time_badge(0, 0)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_responsive_layout(self.width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(self.width())

    def _apply_responsive_layout(self, w: int):
        if w <= 0:
            return
        if w >= 440:
            self._time_format_mode = "full"
            self.zoom_lbl.show()
            self.btn_tool_move.show()
            self.btn_tool_hand.show()
            self.btn_mute.show()
            self.btn_ratio.show()
            self.btn_fs.show()
            if not self._compact:
                self.btn_stop.show()
        elif w >= 330:
            self._time_format_mode = "compact"
            self.zoom_lbl.show()
            self.btn_tool_move.show()
            self.btn_tool_hand.show()
            self.btn_mute.show()
            self.btn_ratio.show()
            self.btn_fs.show()
            if self._compact:
                self.btn_stop.hide()
        elif w >= 270:
            self._time_format_mode = "compact"
            self.zoom_lbl.show()
            self.btn_tool_move.show()
            self.btn_tool_hand.hide()
            self.btn_mute.show()
            self.btn_ratio.show()
            self.btn_fs.show()
            self.btn_stop.hide()
        else:
            self._time_format_mode = "minimal"
            self.zoom_lbl.hide()
            self.btn_tool_move.show()
            self.btn_tool_hand.hide()
            self.btn_mute.show()
            self.btn_ratio.show()
            self.btn_fs.show()
            self.btn_stop.hide()
        self._update_time_badge()

    def _format_time_code(self, ms: int, mode: str) -> str:
        ms = max(0, int(ms))
        s, milli = divmod(ms, 1000)
        m, sec = divmod(s, 60)
        h, m = divmod(m, 60)
        fr = milli // 40
        if mode == "full":
            return f"{h:02d}:{m:02d}:{sec:02d}:{fr:02d}" if h else f"{m:02d}:{sec:02d}:{fr:02d}"
        if mode == "compact" or mode == "minimal":
            return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"

    def _update_time_badge(self, pos: int | None = None, dur: int | None = None):
        if pos is not None:
            self._curr_pos = pos
        if dur is not None:
            self._curr_dur = dur
        curr = getattr(self, "_curr_pos", 0)
        total = getattr(self, "_curr_dur", 0)
        mode = getattr(self, "_time_format_mode", "compact")

        pos_str = self._format_time_code(curr, mode)
        dur_str = self._format_time_code(total, mode)

        if not hasattr(self, "time_badge"):
            return

        if mode == "minimal":
            self.time_badge.setText(
                f'<span style="color:#818cf8; font-weight:700;">{pos_str}</span>'
            )
        else:
            self.time_badge.setText(
                f'<span style="color:#818cf8; font-weight:700;">{pos_str}</span> '
                f'<span style="color:#475569;">/</span> '
                f'<span style="color:#94a3b8;">{dur_str}</span>'
            )
        if hasattr(self, "pos_lbl"):
            self.pos_lbl.setText(pos_str)
        if hasattr(self, "dur_lbl"):
            self.dur_lbl.setText(dur_str)

    def set_dock_host(self, host: QWidget, index: int = 1):
        self._dock_host = host
        self._dock_index = index

    def set_fullscreen_mode(self, is_fs: bool):
        if is_fs:
            self.slider.show()
        else:
            self.slider.hide()

    def _init_playback_menus(self):
        """One framing menu — fit / ratio / canvas background. Zoom is wheel + drag."""
        self._aspect_menu = QMenu(self)
        self._aspect_menu.setObjectName("aspect_ratio_menu")
        self._aspect_group = QActionGroup(self)
        self._aspect_group.setExclusive(True)
        self._aspect_actions = {}

        items = [
            ("fit", "Original (Fit)"),
            ("fill", "Fill (Stretch)"),
            ("cover", "Cover (Crop)"),
            (None, "separator"),
            ("16:9", "16:9 Widescreen"),
            ("9:16", "9:16 Vertical"),
            ("1:1", "1:1 Square"),
            ("4:3", "4:3"),
        ]

        for key, title in items:
            if key is None:
                self._aspect_menu.addSeparator()
                continue
            act = QAction(title, self)
            act.setCheckable(True)
            if key == "fit":
                act.setChecked(True)
            act.triggered.connect(lambda checked=False, k=key: self._on_aspect_selected(k))
            self._aspect_group.addAction(act)
            self._aspect_menu.addAction(act)
            self._aspect_actions[key] = act

        self._aspect_menu.addSeparator()
        self._bg_menu = self._aspect_menu.addMenu("Canvas background")
        self._bg_group = QActionGroup(self)
        self._bg_group.setExclusive(True)
        self._bg_actions = {}

        for bg_key, bg_label in (
            ("none", "Black"),
            ("blur", "Blurred video"),
            ("color", "Color…"),
        ):
            act = QAction(bg_label, self)
            act.setCheckable(True)
            if bg_key == "none":
                act.setChecked(True)
            act.triggered.connect(lambda checked=False, k=bg_key: self._on_frame_bg_selected(k))
            self._bg_group.addAction(act)
            self._bg_menu.addAction(act)
            self._bg_actions[bg_key] = act

        self._aspect_menu.addSeparator()
        act_reset = QAction("Reset zoom", self)
        act_reset.triggered.connect(lambda: self._on_aspect_selected("zoom_reset"))
        self._aspect_menu.addAction(act_reset)

    def _show_aspect_menu(self):
        if not self.btn_ratio.isEnabled():
            return
        pos = self.btn_ratio.mapToGlobal(QPoint(0, self.btn_ratio.height() + 4))
        self._aspect_menu.exec(pos)

    def _on_frame_bg_selected(self, key: str):
        if not self._preview:
            return
        if key == "color":
            current = QColor(self._preview.canvas_state()["color"])
            color = QColorDialog.getColor(current, self, "Canvas Background Color")
            if color.isValid():
                self._preview.set_frame_bg_mode("color", color.name())
            else:
                self.sync_canvas(self._current_aspect_key, self._preview.canvas_state()["bg"])
        else:
            self._preview.set_frame_bg_mode(key)

    def sync_canvas(self, aspect_key: str, bg: str):
        """Reflect the preview canvas in the menu checks without re-applying it."""
        self._current_aspect_key = aspect_key
        if aspect_key in self._aspect_actions:
            self._aspect_actions[aspect_key].setChecked(True)
            self.btn_ratio.setToolTip(f"Canvas ratio: {self._aspect_actions[aspect_key].text()}")
        if bg in self._bg_actions:
            self._bg_actions[bg].setChecked(True)

    def _on_aspect_selected(self, key: str):
        if key == "zoom_reset":
            if self._preview:
                self._preview.reset_zoom()
            return

        self._current_aspect_key = key
        if self._preview:
            if key in ("fill", "cover"):
                self._preview.set_aspect_ratio_mode(key)
            else:
                self._preview.edit_canvas(ratio="original" if key == "fit" else key)
        label = self._aspect_actions[key].text() if key in self._aspect_actions else key
        self.btn_ratio.setToolTip(f"Frame · {label}")

    def _icon_btn(self, name: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("media_ctrl_btn")
        btn.setIcon(icon(name, color="#e7ecf3", size=14))
        btn.setIconSize(QSize(14, 14))
        btn.setFixedSize(26, 26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setAutoRaise(True)
        return btn

    def _tool_icon(self, name: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("media_tool_btn")
        btn.setIcon(icon(name, color="#e7ecf3", size=14))
        btn.setIconSize(QSize(14, 14))
        btn.setFixedSize(26, 26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setAutoRaise(True)
        btn.setProperty("tool_icon", name)
        return btn

    def _paint_tool_icons(self, tool: str):
        """Accent the active tool icon; mute the other."""
        move_name = self.btn_tool_move.property("tool_icon") or "cursor"
        hand_name = self.btn_tool_hand.property("tool_icon") or "grab"
        self.btn_tool_move.setIcon(
            icon(move_name, color=COLOR_PRIMARY if tool == "move" else COLOR_TEXT_SUB, size=14)
        )
        self.btn_tool_hand.setIcon(
            icon(hand_name, color=COLOR_PRIMARY if tool == "hand" else COLOR_TEXT_SUB, size=14)
        )

    def _set_view_tool(self, tool: str):
        tool = "hand" if tool == "hand" else "move"
        self.btn_tool_move.setChecked(tool == "move")
        self.btn_tool_hand.setChecked(tool == "hand")
        self._paint_tool_icons(tool)
        if self._preview:
            self._preview.set_view_tool(tool)

    def sync_view_tool(self, tool: str):
        tool = "hand" if tool == "hand" else "move"
        self.btn_tool_move.blockSignals(True)
        self.btn_tool_hand.blockSignals(True)
        self.btn_tool_move.setChecked(tool == "move")
        self.btn_tool_hand.setChecked(tool == "hand")
        self.btn_tool_move.blockSignals(False)
        self.btn_tool_hand.blockSignals(False)
        self._paint_tool_icons(tool)

    def bind(self, preview: "MediaPreviewWidget"):
        self._preview = preview
        preview._playback_widget = self
        if not hasattr(self, "_dock_host") or self._dock_host is None:
            self._dock_host = self.parentWidget()
        preview.position_changed.connect(self._on_position)
        preview.duration_changed.connect(self._on_duration)
        preview.playing_changed.connect(self._set_play_icon)
        preview.media_changed.connect(self._on_media)
        preview.media_cleared.connect(self._on_cleared)
        preview.fullscreen_changed.connect(self._on_fs_changed)
        if hasattr(preview, "view_tool_changed"):
            preview.view_tool_changed.connect(self.sync_view_tool)
        if hasattr(preview, "zoom_changed"):
            preview.zoom_changed.connect(self._on_zoom_changed)
            self._on_zoom_changed(preview.zoom_factor())
        preview.set_aspect_ratio_mode(self._current_aspect_key)
        self._set_view_tool(getattr(preview, "view_tool", lambda: "move")())

    def _on_zoom_changed(self, factor: float):
        pct = max(1, int(round(float(factor) * 100)))
        self.zoom_lbl.setText(f"{pct}%")
        self.zoom_lbl.setProperty("zoomed", "true" if abs(factor - ZOOM_FIT) > 0.01 else "false")
        self.zoom_lbl.style().unpolish(self.zoom_lbl)
        self.zoom_lbl.style().polish(self.zoom_lbl)

    def _reset_preview_zoom(self):
        if self._preview is not None and hasattr(self._preview, "reset_zoom"):
            self._preview.reset_zoom()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "zoom_lbl", None) and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._reset_preview_zoom()
                return True
        return super().eventFilter(obj, event)

    def set_enabled(self, enabled: bool):
        widgets = [
            self.btn_play, self.btn_mute, self.btn_fs, self.slider,
            self.btn_stop, self.btn_ratio, self.btn_tool_move, self.btn_tool_hand,
            self.zoom_lbl,
        ]
        for w in widgets:
            w.setEnabled(enabled)

    def _on_ratio(self, keep: bool):
        self._keep_ratio = keep
        if self._preview:
            self._preview.set_keep_aspect(keep)
        self.btn_ratio.setToolTip("Fill frame" if keep else "Keep aspect ratio")

    def _on_media(self, path: str):
        self.set_enabled(bool(path))
        if not path:
            self._reset_timeline()

    def _on_cleared(self):
        self.set_enabled(False)
        self._reset_timeline()
        self._set_play_icon(False)
        if self.btn_mute.isChecked():
            self.btn_mute.setChecked(False)

    def _reset_timeline(self):
        self.slider.setRange(0, 0)
        self._update_time_badge(pos=0, dur=0)

    def _on_play(self):
        if self._preview:
            self._preview.toggle_play()

    def _on_stop(self):
        if self._preview:
            self._preview.stop()

    def _on_mute(self, muted: bool):
        if self._preview:
            self._preview.set_muted(muted)
        ico = "volume-off" if muted else "volume"
        color = "#f87171" if muted else "#e7ecf3"
        self.btn_mute.setIcon(icon(ico, color=color, size=14))
        self.btn_mute.setToolTip("Unmute audio (M)" if muted else "Mute audio (M)")

    def _on_fullscreen(self):
        if self._preview:
            self._preview.toggle_fullscreen()

    def _on_fs_changed(self, fullscreen: bool):
        ico = "win-restore" if fullscreen else "win-maximize"
        self.btn_fs.setIcon(icon(ico, color="#e7ecf3", size=14))
        self.btn_fs.setToolTip("Exit full screen (Esc / F)" if fullscreen else "Full screen (F)")

    def _set_play_icon(self, playing: bool):
        if playing:
            self.btn_play.setIcon(icon("pause", color="#ffffff", size=14))
            self.btn_play.setToolTip("Pause (Space)")
        else:
            self.btn_play.setIcon(icon("play", color="#ffffff", size=14))
            self.btn_play.setToolTip("Play (Space)")

    def _fmt_ms(self, ms: int) -> str:
        return self._format_time_code(ms, getattr(self, "_time_format_mode", "compact"))

    @Slot(int)
    def _on_position(self, pos: int):
        if not self._seeking:
            self.slider.blockSignals(True)
            self.slider.setValue(pos)
            self.slider.blockSignals(False)
        self._update_time_badge(pos=pos)

    @Slot(int)
    def _on_duration(self, dur: int):
        self.slider.setRange(0, max(0, dur))
        self._update_time_badge(dur=dur)

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        self._seeking = False
        if self._preview:
            self._preview.seek_ms(self.slider.value())

    def _on_seek_moved(self, value: int):
        self._update_time_badge(pos=value)


class MediaPreviewWidget(QWidget):
    """
    Pure player stage (poster / video). Transport lives in MediaPlaybackWidget.
    """
    media_changed = Signal(str)
    media_cleared = Signal()
    loading_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    playing_changed = Signal(bool)
    close_requested = Signal()
    fullscreen_changed = Signal(bool)
    aspect_changed = Signal(str)
    canvas_edited = Signal(dict)
    view_tool_changed = Signal(str)
    zoom_changed = Signal(float)

    AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}

    ASPECT_PRESETS = {
        "fit": (None, Qt.AspectRatioMode.KeepAspectRatio),
        "fill": (None, Qt.AspectRatioMode.IgnoreAspectRatio),
        "cover": (None, Qt.AspectRatioMode.KeepAspectRatioByExpanding),
        "16:9": (16.0 / 9.0, Qt.AspectRatioMode.IgnoreAspectRatio),
        "9:16": (9.0 / 16.0, Qt.AspectRatioMode.IgnoreAspectRatio),
        "1:1": (1.0, Qt.AspectRatioMode.IgnoreAspectRatio),
        "4:3": (4.0 / 3.0, Qt.AspectRatioMode.IgnoreAspectRatio),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media_preview")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._path = ""
        self._play_path = ""
        self._is_video = False
        self._fullscreen = False
        self._fs_window = None
        self._fs_target: tuple[QWidget, QWidget, int] | None = None
        self._title = ""
        self._load_gen = 0
        self._source_ready = False
        self._pending_play = False
        self._pending_seek = -1
        self._compat_worker = None
        self._aspect_key = "fit"
        self._custom_ratio = None
        self._video_natural_ratio = None

        # View zoom & pan — magnifies the wrapper view only; project canvas (fit) is unchanged.
        self._view_tool = "move"
        self._zoom_factor = ZOOM_DEFAULT
        self._pan_x = 0
        self._pan_y = 0
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._drag_start_pan = (0, 0)
        self._fit_rect = QRect()

        self.init_ui()
        self._setup_player()

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

    def init_ui(self):
        # Clip magnified frame to the wrapper so zoom is a view, not a layout blow-out.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.canvas_frame = QWidget(self)
        self.canvas_frame.setObjectName("media_canvas")
        _fill_panel(self.canvas_frame, COLOR_BG_CARD)

        self.bg_label = QLabel(self.canvas_frame)
        self.bg_label.setObjectName("media_bg_label")
        self.bg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bg_label.setScaledContents(True)
        self.bg_label.hide()

        self.stage = QStackedWidget(self.canvas_frame)
        self.stage.setObjectName("media_stage")

        self.placeholder = QLabel("Select media to play")
        self.placeholder.setObjectName("media_placeholder")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.poster = QLabel()
        self.poster.setObjectName("media_poster")
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setScaledContents(False)

        self.video = _VideoSurface()
        self.video.setObjectName("media_video")
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)

        self.stage.addWidget(self.placeholder)
        self.stage.addWidget(self.poster)
        self.stage.addWidget(self.video)
        for surface in (self, self.stage, self.placeholder, self.poster, self.video):
            _fill_panel(surface, COLOR_BG_CARD)

        self.stage.installEventFilter(self)
        self.video.installEventFilter(self)
        self.poster.installEventFilter(self)
        self._canvas = clean_canvas(None)
        self._canvas_active = False
        self._canvas_covered = True
        self._adjust: dict = {}
        self._blur_src = QImage()
        self._blur_clock = 0.0

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
        fill = _FULLSCREEN_BG if self._fullscreen else COLOR_BG_CARD
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
        _fill_panel(self._fs_window, _FULLSCREEN_BG)
        _fill_panel(self, _FULLSCREEN_BG)
        fs_layout = QVBoxLayout(self._fs_window)
        fs_layout.setContentsMargins(0, 0, 0, 0)
        fs_layout.setSpacing(0)

        target = self._fs_target[0] if self._fs_target else self
        target.setStyleSheet(
            f"#media_preview, #preview_stage_wrap {{ background-color: {_FULLSCREEN_BG}; border-radius: 0; }}"
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

    def set_dock_host(self, host: QWidget, index: int = 0):
        self._dock_host = host
        self._dock_index = index

    def set_fullscreen_target(self, target: QWidget, host: QWidget, index: int = 0):
        """Take `target` (e.g. stage + overlays) fullscreen instead of the bare player, docking back into host."""
        self._fs_target = (target, host, index)

    def _setup_player(self):
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video.videoSink())
        self._source_gain = 1.0
        self._voice_gain = 1.0
        self._bed_gain = 0.0
        self._master_mute = False
        self._bed_path = ""
        self._voice_path = ""
        self.bed_out = QAudioOutput(self)
        self.voice_out = QAudioOutput(self)
        self.bed_player = QMediaPlayer(self)
        self.voice_player = QMediaPlayer(self)
        self.bed_player.setAudioOutput(self.bed_out)
        self.voice_player.setAudioOutput(self.voice_out)

        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)
        self.video.frame_image.connect(self._on_video_frame)
        self.stage.setCurrentIndex(0)

    @staticmethod
    def _probe_video_size(path: str) -> tuple[int, int]:
        """Return (width, height) from probe_media; never raises."""
        try:
            info = probe_media(path)
        except Exception:
            return 0, 0
        if isinstance(info, dict):
            return int(info.get("width") or 0), int(info.get("height") or 0)
        stream = getattr(info, "video_stream", None)
        if stream is None:
            return 0, 0
        return int(getattr(stream, "width", 0) or 0), int(getattr(stream, "height", 0) or 0)

    def load(self, path: str) -> bool:
        if not path or not os.path.isfile(path):
            self.clear()
            return False

        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        self.player.setSource(QUrl())

        self._load_gen += 1
        gen = self._load_gen
        self._path = path
        self._play_path = ""
        self._source_ready = False
        self._pending_play = False
        self._pending_seek = -1
        self._title = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        self._is_video = ext in VIDEO_EXTS

        self.stage.show()
        self._update_stage_bounds()

        if self._is_video:
            w, h = self._probe_video_size(path)
            if w > 0 and h > 0:
                self._video_natural_ratio = float(w) / float(h)
                self._update_stage_bounds()
            self._show_poster(path)
        else:
            self.placeholder.setText(self._title)
            self.stage.setCurrentWidget(self.placeholder)

        self.media_changed.emit(path)

        abs_path = os.path.abspath(path)
        cached = ready_playback_path(abs_path)
        if cached:
            self.loading_changed.emit(False)
            self._apply_play_source(gen, cached)
            return True

        self.loading_changed.emit(True)
        worker = Worker(ensure_playback_file, abs_path)
        worker.signals.result.connect(lambda play_path, g=gen: self._apply_play_source(g, play_path))
        worker.signals.error.connect(lambda err, _tb, g=gen: self._on_compat_fail(g, err))
        self._compat_worker = worker
        QThreadPool.globalInstance().start(worker)
        return True

    def _on_compat_fail(self, gen: int, err):
        if gen != self._load_gen:
            return
        self._source_ready = False
        self.loading_changed.emit(False)
        self.placeholder.setText(f"Playback convert failed · {err}")
        self.stage.setCurrentWidget(self.placeholder)

    def _apply_play_source(self, gen: int, play_path: str):
        if gen != self._load_gen or not self._path:
            return
        if not play_path or not os.path.isfile(play_path):
            self._on_compat_fail(gen, "missing playback file")
            return
        self._play_path = play_path
        self.player.setSource(QUrl.fromLocalFile(os.path.abspath(play_path)))
        self._source_ready = True
        self.loading_changed.emit(False)
        self._apply_buses()
        if self._pending_seek >= 0:
            self.seek_ms(self._pending_seek)
        if self._pending_play:
            self._pending_play = False
            self.toggle_play()

    def clear(self):
        if self._fullscreen:
            self.exit_fullscreen()
        self.stop()
        self._load_gen += 1
        self._path = ""
        self._play_path = ""
        self._title = ""
        self._is_video = False
        self.loading_changed.emit(False)
        self._source_ready = False
        self._pending_play = False
        self._video_natural_ratio = None
        self._custom_ratio = self.ASPECT_PRESETS.get(self._aspect_key, (None, None))[0]
        self._blur_src = QImage()
        self.player.setSource(QUrl())
        self.placeholder.setText("Select media to play")
        self.poster.clear()
        self.stage.setCurrentWidget(self.placeholder)
        self.stage.hide()
        self.playing_changed.emit(False)
        self.duration_changed.emit(0)
        self.position_changed.emit(0)
        self.media_cleared.emit()

    def toggle_play(self):
        if not self._path:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        if not self._source_ready:
            self._pending_play = True
            return
        if self._is_video:
            self.stage.setCurrentWidget(self.video)
        self.player.play()

    def stop(self):
        self._pending_play = False
        self.player.stop()
        if self._path and self._is_video:
            self._show_poster(self._path)

    def stop_playback(self):
        """Halt audio/video when leaving the tool window."""
        self._pending_play = False
        if self._fullscreen:
            self.exit_fullscreen()
        self.player.stop()
        if self._path and self._is_video:
            self._show_poster(self._path)

    def seek_ms(self, ms: int):
        pos = max(0, int(ms))
        if self._path and not self._source_ready:
            self._pending_seek = pos
            return
        self._pending_seek = -1
        self.player.setPosition(pos)
        self._seek_stems(pos)

    def set_muted(self, muted: bool):
        self._master_mute = bool(muted)
        self._apply_buses()

    def set_source_gain(self, gain: float):
        self._source_gain = max(0.0, min(1.5, float(gain)))
        self._apply_buses()

    def set_voice_gain(self, gain: float):
        self._voice_gain = max(0.0, min(1.5, float(gain)))
        self._apply_buses()

    def set_bed_gain(self, gain: float):
        self._bed_gain = max(0.0, min(1.5, float(gain)))
        self._apply_buses()

    def set_stems(self, bed: str, voice: str):
        self._bed_path = bed if bed and os.path.isfile(bed) else ""
        self._voice_path = voice if voice and os.path.isfile(voice) else ""
        self._load_stem(self.bed_player, self._bed_path)
        self._load_stem(self.voice_player, self._voice_path)
        self._apply_buses()
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._sync_stems(True)

    def _load_stem(self, player: QMediaPlayer, path: str):
        player.stop()
        if path:
            player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
            player.setPosition(self.player.position())
        else:
            player.setSource(QUrl())

    def _apply_buses(self):
        if not hasattr(self, "audio"):
            return
        source = 0.0 if self._master_mute else self._source_gain
        voice = 0.0 if self._master_mute else self._voice_gain
        bed = 0.0 if self._master_mute or not self._bed_path else self._bed_gain
        self.audio.setMuted(source <= 0.001)
        self.audio.setVolume(min(1.0, source))
        self.bed_out.setVolume(min(1.0, bed))
        self.bed_out.setMuted(bed <= 0.001)
        self.voice_out.setVolume(voice)
        self.voice_out.setMuted(voice <= 0.001 or not self._voice_path)

    def _seek_stems(self, pos: int):
        for player, path in ((self.bed_player, self._bed_path), (self.voice_player, self._voice_path)):
            if path:
                player.setPosition(pos)

    def _sync_stems(self, playing: bool):
        pos = self.player.position()
        for player, path in ((self.bed_player, self._bed_path), (self.voice_player, self._voice_path)):
            if not path:
                if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    player.pause()
                continue
            if abs(player.position() - pos) > 180:
                player.setPosition(pos)
            if playing and player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                player.play()
            elif not playing and player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                player.pause()

    @Slot(int)
    def _on_position(self, pos: int):
        self.position_changed.emit(pos)
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._sync_stems(True)

    @Slot(int)
    def _on_duration(self, dur: int):
        self.duration_changed.emit(dur)

    @Slot(QMediaPlayer.PlaybackState)
    def _on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playing_changed.emit(playing)
        self._sync_stems(playing)
        if state == QMediaPlayer.PlaybackState.StoppedState and self._path and self._is_video:
            self._show_poster(self._path)

    def _on_error(self, error, message=""):
        # Auto-recover using proxy processor if playback stream errors out
        if self._path and not getattr(self, "_proxy_recovering", False):
            self._proxy_recovering = True
            # pyrefly: ignore [missing-import]
            from claynext.models.media_service import ensure_proxy_render
            gen = self._load_gen
            worker = Worker(ensure_proxy_render, self._path)
            worker.signals.result.connect(lambda proxy_path, g=gen: self._on_proxy_recovered(g, proxy_path))
            worker.signals.error.connect(lambda _err, _tb: self._reset_proxy_recovering())
            QThreadPool.globalInstance().start(worker)
            return

        if self._path and self._is_video and self.poster.pixmap() and not self.poster.pixmap().isNull():
            self.stage.setCurrentWidget(self.poster)
        else:
            self.placeholder.setText(f"Preview error · {message or error}")
            self.stage.setCurrentWidget(self.placeholder)

    def _reset_proxy_recovering(self):
        self._proxy_recovering = False

    def _on_proxy_recovered(self, gen: int, proxy_path: str):
        self._proxy_recovering = False
        if gen == self._load_gen and proxy_path and os.path.isfile(proxy_path):
            self._apply_play_source(gen, proxy_path)

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

