"""Transport bar under the player stage."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QSlider,
    QFrame,
    QMenu,
    QColorDialog,
)
from PySide6.QtCore import (
    Qt,
    Slot,
    QSize,
    QEvent,
    QPoint,
)
from PySide6.QtGui import QAction, QActionGroup, QColor

from claynext.constants.theme_constants import COLOR_BG_SIDEBAR, COLOR_PRIMARY, COLOR_TEXT_SUB
from claynext.gui.icons import icon

from claynext.gui.components.media_preview.const import ZOOM_DEFAULT, ZOOM_FIT
from claynext.gui.components.media_preview.image import _fill_panel

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
        self._origin = 0
        self._length = 0
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

    def set_window(self, origin_ms: int, length_ms: int):
        """Show and seek a slice of the file. Length 0 follows the whole file."""
        self._origin = max(0, int(origin_ms))
        self._length = max(0, int(length_ms))
        if self._length:
            self.slider.setRange(0, self._length)
            shown = max(0, min(self._length, self._curr_pos - self._origin))
            self.slider.blockSignals(True)
            self.slider.setValue(shown)
            self.slider.blockSignals(False)
            self._update_time_badge(pos=shown, dur=self._length)

    def _shown_pos(self, file_ms: int) -> int:
        shown = int(file_ms) - self._origin
        if self._length:
            return max(0, min(self._length, shown))
        return max(0, shown)

    @Slot(int)
    def _on_position(self, pos: int):
        shown = self._shown_pos(pos)
        if not self._seeking:
            self.slider.blockSignals(True)
            self.slider.setValue(shown)
            self.slider.blockSignals(False)
        self._update_time_badge(pos=shown)

    @Slot(int)
    def _on_duration(self, dur: int):
        if self._length:
            self.slider.setRange(0, self._length)
            self._update_time_badge(dur=self._length)
            return
        self.slider.setRange(0, max(0, dur))
        self._update_time_badge(dur=dur)

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        self._seeking = False
        if self._preview:
            self._preview.seek_ms(self._origin + self.slider.value())

    def _on_seek_moved(self, value: int):
        self._update_time_badge(pos=value)
