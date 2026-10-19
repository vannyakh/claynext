"""Command card under the media library."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QSizePolicy,
    QPushButton,
    QFrame,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon

from claynext.constants.theme_constants import COLOR_PRIMARY
from claynext.gui.icons import icon
from claynext.models.thumbnails import VIDEO_EXTS

class _MediaDetailFooter(QFrame):
    """
    Docked interactive command card below the media library list/grid:
    Shows thumbnail preview with quick play, file meta, resolution, duration,
    and action buttons: '+ Add to Timeline', 'Reveal in Folder', and 'Remove'.
    """
    preview_requested = Signal(str)
    localize_requested = Signal()
    reveal_requested = Signal()
    remove_requested = Signal()
    browse_requested = Signal()
    clear_selection_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media_lib_detail_card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(52)

        self._active_path = ""
        self._selected_paths: list[str] = []

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        # Left: Interactive Thumbnail / Poster
        self.thumb_box = QLabel()
        self.thumb_box.setObjectName("media_lib_footer_thumb")
        self.thumb_box.setFixedSize(48, 36)
        self.thumb_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb_box.setToolTip("Click to preview in player")
        self.thumb_box.mousePressEvent = lambda ev: self._on_thumb_click(ev)
        lay.addWidget(self.thumb_box)

        # Center: Info & Meta
        mid = QVBoxLayout()
        mid.setSpacing(2)
        mid.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("media_lib_footer_title")
        title_row.addWidget(self.lbl_title)
        title_row.addStretch(1)
        mid.addLayout(title_row)

        self.meta_row = QHBoxLayout()
        self.meta_row.setSpacing(8)
        self.chip_dur, self.ico_dur, self.lbl_dur = self._meta_chip()
        self.chip_size, self.ico_size, self.lbl_size = self._meta_chip()
        self.chip_res, self.ico_res, self.lbl_res = self._meta_chip()
        self.meta_row.addWidget(self.chip_dur)
        self.meta_row.addWidget(self.chip_size)
        self.meta_row.addWidget(self.chip_res)
        self.meta_row.addStretch(1)
        mid.addLayout(self.meta_row)

        lay.addLayout(mid, 1)

        # Right: Dub + utility actions
        self.btn_localize = QPushButton("Localize")
        self.btn_localize.setObjectName("media_lib_btn_localize")
        self.btn_localize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_localize.setFixedHeight(22)
        self.btn_localize.setIcon(icon("activity", color="#c4b5fd", size=11))
        self.btn_localize.setIconSize(QSize(11, 11))
        self.btn_localize.setToolTip("Start localization for selected movies")
        self.btn_localize.clicked.connect(self.localize_requested.emit)
        lay.addWidget(self.btn_localize)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setObjectName("media_lib_footer_progress")
        self.lbl_progress.setVisible(False)
        self.lbl_progress.setMinimumWidth(72)
        lay.addWidget(self.lbl_progress)

        self._localize_busy = False

        self.btn_reveal = QToolButton()
        self.btn_reveal.setObjectName("media_lib_footer_btn")
        self.btn_reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reveal.setFixedSize(22, 22)
        self.btn_reveal.setIcon(icon("folder", color="#94a3b8", size=12))
        self.btn_reveal.setIconSize(QSize(12, 12))
        self.btn_reveal.setToolTip("Show file in Finder / Explorer")
        self.btn_reveal.clicked.connect(self.reveal_requested.emit)
        lay.addWidget(self.btn_reveal)

        self.btn_remove = QToolButton()
        self.btn_remove.setObjectName("media_lib_footer_btn")
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setFixedSize(22, 22)
        self.btn_remove.setIcon(icon("trash", color="#94a3b8", size=12))
        self.btn_remove.setIconSize(QSize(12, 12))
        self.btn_remove.setToolTip("Remove selected from library")
        self.btn_remove.clicked.connect(self.remove_requested.emit)
        lay.addWidget(self.btn_remove)

    def _meta_chip(self) -> tuple[QWidget, QLabel, QLabel]:
        chip = QWidget()
        chip.setObjectName("media_lib_footer_meta_chip")
        row = QHBoxLayout(chip)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        ico = QLabel()
        ico.setObjectName("media_lib_footer_meta_ico")
        ico.setFixedSize(10, 10)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt = QLabel("")
        txt.setObjectName("media_lib_footer_meta")
        row.addWidget(ico, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(txt, 0, Qt.AlignmentFlag.AlignVCenter)
        return chip, ico, txt

    def _set_meta(
        self,
        chip: QWidget,
        ico_lbl: QLabel,
        txt_lbl: QLabel,
        *,
        icon_name: str | None,
        text: str,
        visible: bool = True,
    ):
        if not visible or not text:
            chip.hide()
            return
        if icon_name:
            ico_lbl.setPixmap(icon(icon_name, color="#6b7785", size=10).pixmap(10, 10))
            ico_lbl.show()
        else:
            ico_lbl.clear()
            ico_lbl.hide()
        txt_lbl.setText(text)
        chip.show()

    def _on_thumb_click(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._active_path:
            self.preview_requested.emit(self._active_path)

    def set_localize_progress(self, busy: bool, pct: int = 0, message: str = ""):
        """Show job progress in the media footer (replaces script-panel loader)."""
        self._localize_busy = bool(busy)
        if not busy:
            self._localize_pct = None
            self._localize_tip = None
            self.lbl_progress.clear()
            self.lbl_progress.setVisible(False)
            self.btn_localize.setEnabled(True)
            return
        self.show()
        pct = max(0, min(100, int(pct)))
        tip = str(message or "Localization in progress")
        label = "Working…" if pct <= 0 else f"{pct}%"
        short = tip if len(tip) <= 42 else tip[:39] + "…"
        if (
            getattr(self, "_localize_pct", None) == pct
            and getattr(self, "_localize_tip", None) == tip
        ):
            return
        self._localize_pct = pct
        self._localize_tip = tip
        self.btn_localize.setEnabled(False)
        if self.btn_localize.text() != label:
            self.btn_localize.setText(label)
        self.btn_localize.setToolTip(tip)
        if self.lbl_progress.text() != short:
            self.lbl_progress.setText(short)
        self.lbl_progress.setToolTip(tip)
        self.lbl_progress.setVisible(True)

    def update_state(
        self,
        selected_paths: list[str],
        total_paths: list[str],
        meta_cache: dict[str, dict],
        thumb_cache: dict[str, QIcon],
        dur_cache: dict[str, float],
        fallback_icon_fn,
        format_dur_fn,
        size_label_fn,
    ):
        self._selected_paths = list(selected_paths)
        n_selected = len(selected_paths)

        # Empty selection → hide command card (keep visible while a job runs).
        if n_selected == 0 and not self._localize_busy:
            self._active_path = ""
            self.hide()
            return

        self.show()
        if n_selected == 0 and self._localize_busy:
            self.lbl_title.setText("Localizing…")
            self.chip_dur.hide()
            self.chip_size.hide()
            self.chip_res.hide()
            self.btn_reveal.hide()
            self.btn_remove.hide()
            return

        if n_selected == 1:
            path = selected_paths[0]
            self._active_path = path
            name = os.path.basename(path)

            ico = thumb_cache.get(path) or fallback_icon_fn(path)
            self.thumb_box.clear()
            if isinstance(ico, QIcon) and not ico.isNull():
                self.thumb_box.setPixmap(ico.pixmap(48, 36))
            else:
                self.thumb_box.setPixmap(icon("play", color="#94a3b8", size=14).pixmap(14, 14))
            self.thumb_box.setCursor(Qt.CursorShape.PointingHandCursor)
            self.thumb_box.setToolTip("Click to preview in player")

            self.lbl_title.setText(name)
            self.lbl_title.setToolTip(path)

            dur_sec = dur_cache.get(path, 0.0)
            dur_txt = format_dur_fn(dur_sec) if dur_sec > 0 else "—"
            self._set_meta(self.chip_dur, self.ico_dur, self.lbl_dur, icon_name="clock", text=dur_txt)

            sz_txt = size_label_fn(path)
            self._set_meta(self.chip_size, self.ico_size, self.lbl_size, icon_name="hard-drive", text=sz_txt)

            meta = meta_cache.get(path, {})
            w = meta.get("width")
            h = meta.get("height")
            fps = meta.get("fps")
            if w and h:
                fps_txt = f" · {fps:.0f} fps" if fps else ""
                self._set_meta(
                    self.chip_res, self.ico_res, self.lbl_res,
                    icon_name="video", text=f"{w}×{h}{fps_txt}",
                )
            else:
                self.chip_res.hide()

            is_video = os.path.splitext(path)[1].lower() in VIDEO_EXTS
            if not self._localize_busy:
                self.btn_localize.setText("Localize")
                self.btn_localize.setEnabled(is_video)
                self.btn_localize.setToolTip(
                    "Start localization for this movie" if is_video else "Select a video to localize"
                )
                self.lbl_progress.setVisible(False)

            self.btn_reveal.show()
            self.btn_remove.show()

        else:
            self._active_path = selected_paths[-1]
            total_bytes = 0
            video_count = 0
            for p in selected_paths:
                try:
                    total_bytes += os.path.getsize(p)
                except OSError:
                    pass
                if os.path.splitext(p)[1].lower() in VIDEO_EXTS:
                    video_count += 1
            sz_txt = size_label_fn(total_bytes) if callable(size_label_fn) else "—"

            ico = icon("check_on", color=COLOR_PRIMARY, size=24)
            self.thumb_box.setPixmap(ico.pixmap(32, 32))
            self.thumb_box.setCursor(Qt.CursorShape.ArrowCursor)
            self.thumb_box.setToolTip("")

            self.lbl_title.setText(f"{n_selected} items selected")
            self._set_meta(
                self.chip_dur, self.ico_dur, self.lbl_dur,
                icon_name="list", text=f"{n_selected} clips",
            )
            self._set_meta(
                self.chip_size, self.ico_size, self.lbl_size,
                icon_name="hard-drive", text=f"Total {sz_txt}",
            )
            self.chip_res.hide()

            if not self._localize_busy:
                self.btn_localize.setText(
                    f"Localize · {video_count}" if video_count > 1 else "Localize"
                )
                self.btn_localize.setEnabled(video_count > 0)
                self.btn_localize.setToolTip(
                    f"Start localization for {video_count} movie(s)"
                    if video_count
                    else "Select a video to localize"
                )
                self.lbl_progress.setVisible(False)

            self.btn_reveal.show()
            self.btn_remove.show()
