"""Export settings window for the dubbing timeline."""
from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt, QPoint, QRectF, QSize, QThreadPool
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QCheckBox, QFileDialog, QFrame, QWidget, QToolButton,
    QGraphicsDropShadowEffect,
)

from claynext.constants.theme_constants import COLOR_BORDER, COLOR_TEXT_MUTED
from claynext.gui.icons import icon
from claynext.gui.worker import Worker

EXPORT_KINDS = (
    ("movie", "Dubbed movie (timeline mix)", "mp4"),
    ("mix_wav", "Full mix audio", "wav"),
    ("voice_wav", "Voice-over track only", "wav"),
    ("source", "Source movie", "mp4"),
    ("srt", "Subtitles (SRT)", "srt"),
    ("vtt", "Subtitles (WebVTT)", "vtt"),
    ("json", "Script (JSON)", "json"),
)
_EXT = {kind: ext for kind, _label, ext in EXPORT_KINDS}
_MOVIE = {"movie", "source"}
_SCRIPT = {"srt", "vtt", "json"}
_CARD_MAX = QSize(132, 176)
_CARD_RADIUS = 8
_COPY_SUFFIX = re.compile(r"^(.+)_(\d+)$")


def unused_export_path(path: str) -> str:
    """A path that does not replace a file already sitting in the export folder."""
    candidate = os.path.abspath(path)
    if not os.path.exists(candidate):
        return candidate
    folder, filename = os.path.split(candidate)
    stem, ext = os.path.splitext(filename)
    base, number = stem, 2
    match = _COPY_SUFFIX.fullmatch(stem)
    if match and int(match.group(2)) >= 2:
        base, number = match.group(1), int(match.group(2))
    while number < 10000:
        nxt = os.path.join(folder, f"{base}_{number}{ext}")
        if not os.path.exists(nxt):
            return nxt
        number += 1
    return os.path.join(folder, f"{base}_{number}{ext}")


def rounded_still(
    pix: QPixmap, max_size: QSize, radius: int, pixel_ratio: float, *, border: bool = False,
) -> QPixmap:
    """Scale a still to its own aspect and clip it with a rounded border."""
    ratio = pixel_ratio if pixel_ratio > 0 else 1.0
    target = QSize(int(max_size.width() * ratio), int(max_size.height() * ratio))
    scaled = pix.scaled(
        target,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    image = QPixmap(scaled.size())
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    logical = QRectF(0, 0, scaled.width() / ratio, scaled.height() / ratio)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    clip = QPainterPath()
    clip.addRoundedRect(logical.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(logical.toRect(), scaled)
    painter.setClipping(False)
    if border:
        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(logical.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    painter.end()
    return image


class ExportTitleBar(QWidget):
    """Drag handle and close control for a frameless export window."""

    def __init__(self, window: QDialog, title: str):
        super().__init__(window)
        self._window = window
        self._origin: QPoint | None = None
        self.setObjectName("export_title_bar")
        self.setFixedHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 10, 0)
        lay.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("export_title")
        close = QToolButton()
        close.setObjectName("export_close")
        close.setIcon(icon("win-close", color=COLOR_TEXT_MUTED, size=12))
        close.setFixedSize(28, 28)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("Close")
        close.clicked.connect(window.reject)
        lay.addWidget(label)
        lay.addStretch(1)
        lay.addWidget(close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._origin = None
        super().mouseReleaseEvent(event)


def frameless_shell(dialog: QDialog) -> QVBoxLayout:
    """Replace the system title bar with a rounded studio frame."""
    dialog.setWindowFlags(
        Qt.WindowType.Dialog
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.NoDropShadowWindowHint
    )
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(18, 16, 18, 22)
    shell = QFrame()
    shell.setObjectName("export_shell")
    shadow = QGraphicsDropShadowEffect(shell)
    shadow.setBlurRadius(28)
    shadow.setOffset(0, 8)
    shadow.setColor(QColor(0, 0, 0, 170))
    shell.setGraphicsEffect(shadow)
    outer.addWidget(shell)
    body = QVBoxLayout(shell)
    body.setContentsMargins(0, 0, 0, 16)
    body.setSpacing(0)
    return body


def place_export_dialog(dialog: QDialog) -> None:
    """Center the custom frame on its parent window."""
    dialog.adjustSize()
    parent = dialog.parentWidget()
    if parent is not None and parent.isVisible():
        center = parent.mapToGlobal(parent.rect().center())
    else:
        screen = dialog.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        center = screen.availableGeometry().center()
    geo = dialog.frameGeometry()
    geo.moveCenter(center)
    dialog.move(geo.topLeft())


class ExportDialog(QDialog):
    """Pick what to export and where it goes, with a small preview of the movie."""

    def __init__(
        self, parent=None, *, folder: str = "", stem: str = "export", summary: str = "",
        saved: dict | None = None, script_only: bool = False,
        source: str = "", preview: QPixmap | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export script" if script_only else "Export")
        self.setObjectName("exportDialog")
        self.setModal(True)
        self._placed = False
        self._auto_name = True
        self._stem = stem or "export"
        self._script_only = bool(script_only)
        self._source = source or ""
        saved = saved or {}
        _ = summary
        if not folder:
            from claynext.utils.paths import OUTPUTS_DIR
            folder = str(OUTPUTS_DIR)

        body = frameless_shell(self)
        body.addWidget(ExportTitleBar(self, "Export script" if script_only else "Export"))

        content = QHBoxLayout()
        content.setContentsMargins(18, 10, 18, 14)
        content.setSpacing(18)

        box = QFrame()
        box.setObjectName("dub_config_section")
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.combo_kind = QComboBox()
        kinds = [row for row in EXPORT_KINDS if row[0] in _SCRIPT] if script_only else list(EXPORT_KINDS)
        for kind, label, _ext in kinds:
            self.combo_kind.addItem(label, kind)
        default_kind = saved.get("kind", "srt" if script_only else "movie")
        if script_only and default_kind not in _SCRIPT:
            default_kind = "srt"
        self._select(self.combo_kind, default_kind)
        self.combo_kind.currentIndexChanged.connect(self._sync)
        grid.addWidget(self._label("Format"), 0, 0)
        grid.addWidget(self.combo_kind, 0, 1, 1, 2)

        self.combo_version = QComboBox()
        self.combo_version.addItem("Current version", "current")
        self.combo_version.addItem("Back version (last accepted / source)", "back")
        self._select(self.combo_version, saved.get("version", "current"))
        self.lbl_version = self._label("Script")
        grid.addWidget(self.lbl_version, 1, 0)
        grid.addWidget(self.combo_version, 1, 1, 1, 2)

        self.edit_name = QLineEdit()
        self.edit_name.setObjectName("dub_setting_field")
        grid.addWidget(self._label("File name"), 2, 0)
        grid.addWidget(self.edit_name, 2, 1, 1, 2)

        self.edit_folder = QLineEdit(saved.get("folder") or folder)
        self.edit_folder.setObjectName("dub_setting_field")
        browse = QPushButton("Browse…")
        browse.setObjectName("api_keys_btn")
        browse.clicked.connect(self._browse)
        grid.addWidget(self._label("Folder"), 3, 0)
        grid.addWidget(self.edit_folder, 3, 1)
        grid.addWidget(browse, 3, 2)

        self.combo_video = QComboBox()
        self.combo_video.addItem("Keep original picture (fast)", "copy")
        self.combo_video.addItem("Re-encode H.264 high quality", "h264")
        self._select(self.combo_video, saved.get("video", "copy"))
        self.lbl_video = self._label("Video")
        grid.addWidget(self.lbl_video, 4, 0)
        grid.addWidget(self.combo_video, 4, 1, 1, 2)

        self.combo_audio = QComboBox()
        for rate in ("128k", "192k", "256k", "320k"):
            self.combo_audio.addItem(f"AAC {rate.replace('k', '')} kbps", rate)
        self._select(self.combo_audio, saved.get("audio", "256k"))
        self.lbl_audio = self._label("Audio")
        grid.addWidget(self.lbl_audio, 5, 0)
        grid.addWidget(self.combo_audio, 5, 1, 1, 2)

        self.chk_overlays = QCheckBox("Burn on-screen text and captions")
        self.chk_overlays.setChecked(saved.get("overlays", True) is not False)
        grid.addWidget(self.chk_overlays, 6, 1, 1, 2)
        grid.setColumnStretch(1, 1)
        content.addWidget(box, 1)

        self.preview_card = QFrame()
        self.preview_card.setObjectName("export_preview_card")
        self.preview_card.setFixedWidth(156)
        card = QVBoxLayout(self.preview_card)
        card.setContentsMargins(10, 10, 10, 10)
        card.setSpacing(0)
        self.thumb = QLabel("Preview")
        self.thumb.setObjectName("export_thumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setMinimumSize(120, 80)
        card.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.preview_card, 0, Qt.AlignmentFlag.AlignVCenter)
        body.addLayout(content)

        actions = QHBoxLayout()
        actions.setContentsMargins(18, 0, 18, 0)
        actions.setSpacing(8)
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("api_keys_btn")
        cancel.clicked.connect(self.reject)
        self.btn_export = QPushButton("Export")
        self.btn_export.setObjectName("api_keys_btn_primary")
        self.btn_export.setDefault(True)
        self.btn_export.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(self.btn_export)
        body.addLayout(actions)

        self.edit_name.textEdited.connect(self._on_name_edited)
        self.edit_name.textChanged.connect(self._sync_target)
        self.edit_folder.textChanged.connect(self._on_folder_changed)
        self._sync()
        if self._script_only:
            self.preview_card.hide()
            self.setMinimumWidth(460)
        else:
            self.setMinimumWidth(640)
            if preview is not None and not preview.isNull():
                self._apply_pix(preview)
            else:
                self._load_thumb(self._source)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._placed:
            self._placed = True
            place_export_dialog(self)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("asr_field_label")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return label

    @staticmethod
    def _select(combo: QComboBox, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _kind(self) -> str:
        return self.combo_kind.currentData() or "movie"

    def _default_name(self) -> str:
        kind = self._kind()
        suffix = {
            "movie": "_dub", "mix_wav": "_mix", "voice_wav": "_voice", "source": "_source",
        }.get(kind, "_" + str(self.combo_version.currentData() or "current"))
        name = f"{self._stem}{suffix}.{_EXT[kind]}"
        folder = self.edit_folder.text().strip()
        if not folder:
            return name
        return os.path.basename(unused_export_path(os.path.join(folder, name)))

    def _on_name_edited(self):
        self._auto_name = False

    def _on_folder_changed(self):
        if self._auto_name:
            self.edit_name.setText(self._default_name())
        self._sync_target()

    def _sync(self):
        kind = self._kind()
        self.lbl_version.setVisible(kind in _SCRIPT)
        self.combo_version.setVisible(kind in _SCRIPT)
        movie = kind in _MOVIE
        for widget in (self.lbl_video, self.combo_video):
            widget.setVisible(movie)
        for widget in (self.lbl_audio, self.combo_audio):
            widget.setVisible(kind in {"movie"})
        self.chk_overlays.setVisible(kind == "movie")
        self._auto_name = True
        self.edit_name.setText(self._default_name())
        self._sync_target()

    def accept(self):
        path = self.target_path()
        if path:
            free = unused_export_path(path)
            if os.path.basename(free) != os.path.basename(path):
                self.edit_name.setText(os.path.basename(free))
        super().accept()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Export folder", self.edit_folder.text())
        if folder:
            self.edit_folder.setText(folder)

    def _sync_target(self):
        self.btn_export.setEnabled(bool(self.target_path()))

    def _load_thumb(self, source: str) -> None:
        if not source or not os.path.isfile(source):
            self.thumb.setText("No preview")
            return
        from claynext.models.thumbnails import thumb_path_for

        for width in (480, 160):
            cached = thumb_path_for(source, width)
            if cached.is_file():
                self._apply_pix(QPixmap(str(cached)))
                if width >= 480:
                    return
        worker = Worker(self._extract, source)
        self._thumb_worker = worker
        worker.signals.result.connect(self._on_thumb)
        worker.signals.finished.connect(self._clear_thumb_worker)
        QThreadPool.globalInstance().start(worker)

    def _clear_thumb_worker(self) -> None:
        self._thumb_worker = None

    @staticmethod
    def _extract(source: str, progress_callback=None) -> str | None:
        from claynext.models.thumbnails import ensure_thumbnail

        return ensure_thumbnail(source, 480)

    def _on_thumb(self, path) -> None:
        if not path:
            return
        self._apply_pix(QPixmap(str(path)))

    def _apply_pix(self, pix: QPixmap) -> None:
        if pix.isNull():
            self.thumb.setText("No preview")
            return
        rounded = rounded_still(pix, _CARD_MAX, _CARD_RADIUS, self.devicePixelRatioF())
        self.thumb.setPixmap(rounded)
        self.thumb.setText("")
        ratio = rounded.devicePixelRatio() or 1.0
        self.thumb.setFixedSize(int(rounded.width() / ratio), int(rounded.height() / ratio))

    def target_path(self) -> str:
        folder = self.edit_folder.text().strip()
        name = self.edit_name.text().strip()
        if not folder or not name:
            return ""
        ext = "." + _EXT[self._kind()]
        if not name.lower().endswith(ext):
            name += ext
        return os.path.join(folder, name)

    def options(self) -> dict:
        return {
            "kind": self._kind(),
            "version": self.combo_version.currentData() or "current",
            "path": self.target_path(),
            "folder": self.edit_folder.text().strip(),
            "video": self.combo_video.currentData() or "copy",
            "audio": self.combo_audio.currentData() or "256k",
            "overlays": self.chk_overlays.isChecked(),
        }
