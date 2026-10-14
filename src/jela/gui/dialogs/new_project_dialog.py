"""Clean New Project dialog — templates, essentials, live canvas preview."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QThreadPool
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from jela.constants.theme_constants import (
    COLOR_BG_DARK,
    COLOR_BORDER,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SUB,
    primary_color,
)
from jela.core.dub_project import PROJECT_DIR, _slug
from jela.core.ffmpeg_tools import probe_media
from jela.core.icons import icon
from jela.core.worker import Worker
from jela.gui.dialogs.project_settings_dialog import (
    ASPECT_CHOICES,
    FPS_CHOICES,
    RESOLUTION_CHOICES,
    default_project_settings,
)


@dataclass(frozen=True)
class ProjectTemplate:
    id: str
    title: str
    size_label: str
    icon: str
    aspect: str
    resolution: str
    fps: str

    @property
    def label(self) -> str:
        """Single-line chip text: name · size (no aspect ratio)."""
        return f"{self.title} · {self.size_label}"


TEMPLATES: tuple[ProjectTemplate, ...] = (
    ProjectTemplate("hd_landscape", "YouTube", "1080p · 30fps", "video", "16:9", "1080p", "30.00 fps"),
    ProjectTemplate("vertical_shorts", "TikTok Reels", "1080p · 30fps", "aspect", "9:16", "1080p", "30.00 fps"),
    ProjectTemplate("cinema_4k", "Cinema 4K", "2160p · 24fps", "sparkles", "16:9", "2160p", "24.00 fps"),
    ProjectTemplate("square_post", "Instagram", "1080p · 30fps", "grid", "1:1", "1080p", "30.00 fps"),
    ProjectTemplate("portrait_feed", "Portrait", "1080p · 30fps", "image", "4:5", "1080p", "30.00 fps"),
    ProjectTemplate("blank", "Custom", "Original · Adapted", "plus", "Original", "Adapted", "Original"),
)


def _canvas_dimensions(aspect: str, resolution: str) -> tuple[int, int]:
    base_h = {"2160p": 2160, "1080p": 1080, "720p": 720, "Adapted": 1080}.get(resolution, 1080)
    if aspect == "16:9":
        return int(round(base_h * 16 / 9)), base_h
    if aspect == "9:16":
        return base_h, int(round(base_h * 16 / 9))
    if aspect == "1:1":
        return base_h, base_h
    if aspect == "4:3":
        return int(round(base_h * 4 / 3)), base_h
    if aspect == "4:5":
        return base_h, int(round(base_h * 5 / 4))
    return 1920, 1080


def _field(label: str, widget: QWidget) -> QWidget:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lbl = QLabel(label)
    lbl.setObjectName("new_project_field_lbl")
    lay.addWidget(lbl)
    lay.addWidget(widget)
    return wrap


class TemplateCard(QToolButton):
    """Flat chip: icon + long size text (no nested card chrome)."""

    def __init__(self, template: ProjectTemplate, parent=None):
        super().__init__(parent)
        self.template = template
        self.setObjectName("new_project_template")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIcon(icon(template.icon, color=COLOR_TEXT_SUB, size=16))
        self.setIconSize(QSize(16, 16))
        self.setText(template.label)
        self.setToolTip(template.label)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(34)


class CanvasPreviewWidget(QWidget):
    """Aspect-ratio frame only — labels live outside so nothing overlaps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aspect = "16:9"
        self.setMinimumHeight(120)
        self.setMaximumHeight(132)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def update_canvas(self, aspect: str):
        self._aspect = aspect
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(COLOR_BG_DARK))
        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.drawRoundedRect(rect, 8, 8)

        grid = QPen(QColor(255, 255, 255, 10), 1, Qt.PenStyle.DotLine)
        painter.setPen(grid)
        for x in range(rect.left() + 16, rect.right(), 16):
            painter.drawLine(x, rect.top() + 6, x, rect.bottom() - 6)
        for y in range(rect.top() + 16, rect.bottom(), 16):
            painter.drawLine(rect.left() + 6, y, rect.right() - 6, y)

        ratio = {
            "16:9": 16 / 9,
            "9:16": 9 / 16,
            "1:1": 1.0,
            "4:3": 4 / 3,
            "4:5": 4 / 5,
        }.get(self._aspect, 16 / 9)

        avail_w = max(10.0, float(rect.width()) - 40)
        avail_h = max(10.0, float(rect.height()) - 28)
        if avail_w / avail_h > ratio:
            h = avail_h
            w = h * ratio
        else:
            w = avail_w
            h = w / ratio

        cx = rect.center().x()
        cy = rect.center().y()
        frame = QRectF(cx - w / 2, cy - h / 2, w, h)

        accent = QColor(primary_color())
        grad = QLinearGradient(frame.topLeft(), frame.bottomRight())
        grad.setColorAt(0.0, QColor(24, 34, 52, 220))
        grad.setColorAt(1.0, QColor(12, 18, 28, 240))
        painter.setBrush(grad)
        painter.setPen(QPen(accent, 1.5))
        painter.drawRoundedRect(frame, 3, 3)

        painter.setPen(QPen(accent, 1))
        painter.drawLine(QPointF(cx - 4, cy), QPointF(cx + 4, cy))
        painter.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 4))


class StarterMediaStrip(QFrame):
    media_changed = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("new_project_drop_zone")
        self.setAcceptDrops(True)
        self._path = ""
        self._info: dict = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(0)

        self.empty = QWidget()
        row = QHBoxLayout(self.empty)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        ic = QLabel()
        ic.setPixmap(icon("video", color=COLOR_TEXT_SUB, size=20).pixmap(20, 20))
        row.addWidget(ic)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel("Add Initial Footage / Audio (Optional)")
        title.setObjectName("new_project_field_lbl")
        sub = QLabel("Drag & drop or browse · MP4, MKV, MOV, WAV, MP3")
        sub.setObjectName("new_project_hint")
        text.addWidget(title)
        text.addWidget(sub)
        row.addLayout(text, 1)

        browse = QPushButton("Browse…")
        browse.setObjectName("btn_secondary")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setFixedHeight(28)
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        root.addWidget(self.empty)

        self.loaded = QWidget()
        loaded_row = QHBoxLayout(self.loaded)
        loaded_row.setContentsMargins(0, 0, 0, 0)
        loaded_row.setSpacing(10)
        ic2 = QLabel()
        ic2.setPixmap(icon("video", color=primary_color(), size=20).pixmap(20, 20))
        loaded_row.addWidget(ic2)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("new_project_field_lbl")
        self.lbl_meta = QLabel()
        self.lbl_meta.setObjectName("new_project_hint")
        col.addWidget(self.lbl_name)
        col.addWidget(self.lbl_meta)
        loaded_row.addLayout(col, 1)
        clear = QPushButton()
        clear.setObjectName("btn_secondary")
        clear.setIcon(icon("trash", color=COLOR_TEXT_MUTED, size=14))
        clear.setFixedSize(28, 28)
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self.clear_media)
        loaded_row.addWidget(clear)
        root.addWidget(self.loaded)
        self.loaded.hide()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            ext = Path(event.mimeData().urls()[0].toLocalFile()).suffix.lower()
            if ext in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wav", ".mp3", ".flac", ".m4a"}:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isfile(path):
                self.load_media(path)
                event.acceptProposedAction()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Footage or Audio",
            str(Path.home()),
            "Media (*.mp4 *.mkv *.mov *.avi *.webm *.wav *.mp3 *.flac *.m4a);;All (*.*)",
        )
        if path:
            self.load_media(path)

    def load_media(self, path: str):
        if not path or not os.path.isfile(path):
            return
        self._path = path
        worker = Worker(probe_media, path)
        worker.signals.result.connect(self._on_probed)
        QThreadPool.globalInstance().start(worker)

    def _on_probed(self, info: dict):
        self._info = dict(info or {})
        self.lbl_name.setText(os.path.basename(self._path))
        parts = []
        if self._info.get("width") and self._info.get("height"):
            parts.append(f"{self._info['width']}×{self._info['height']}")
        if self._info.get("fps"):
            parts.append(f"{float(self._info['fps']):.2f} fps")
        self.lbl_meta.setText(" · ".join(parts) if parts else "Media attached")
        self.empty.hide()
        self.loaded.show()
        self.media_changed.emit(self._path, self._info)

    def clear_media(self):
        self._path = ""
        self._info = {}
        self.loaded.hide()
        self.empty.show()
        self.media_changed.emit("", {})

    def current_path(self) -> str:
        return self._path

    def current_info(self) -> dict:
        return self._info


class NewProjectDialog(QDialog):
    """Clean two-column New Project: templates + essentials + preview."""

    def __init__(self, parent=None, *, defaults: dict | None = None):
        super().__init__(parent)
        self.setObjectName("new_project_dialog")
        self.setWindowTitle("New Project")
        self.setModal(True)
        self.setMinimumSize(900, 560)
        self.resize(940, 600)

        self._data = dict(defaults or default_project_settings(name="Untitled"))
        self._template_id = "hd_landscape"
        self._template_buttons: dict[str, TemplateCard] = {}

        self._build_ui()
        self._load(self._data)
        self._select_template("hd_landscape", apply_values=True)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        title = QLabel("New Project")
        title.setObjectName("new_project_title")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._left_column(), 1)
        body.addWidget(self._right_column(), 0)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        tip = QLabel("Canvas options can also be changed inside Studio.")
        tip.setObjectName("new_project_hint")
        footer.addWidget(tip)
        footer.addStretch(1)

        cancel = QPushButton("Cancel")
        cancel.setObjectName("btn_secondary")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setFixedHeight(34)
        cancel.setMinimumWidth(96)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)

        self.btn_create = QPushButton("Create Project")
        self.btn_create.setObjectName("btn_primary")
        self.btn_create.setIcon(icon("plus", color="#ffffff", size=15))
        self.btn_create.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create.setFixedHeight(34)
        self.btn_create.setMinimumWidth(140)
        self.btn_create.setDefault(True)
        self.btn_create.clicked.connect(self.accept)
        footer.addWidget(self.btn_create)
        root.addLayout(footer)

    def _left_column(self) -> QWidget:
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # Templates — flat chips, no group card
        lay.addWidget(self._kicker("PROJECT TEMPLATES"))
        chips = QGridLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setHorizontalSpacing(6)
        chips.setVerticalSpacing(6)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for i, tmpl in enumerate(TEMPLATES):
            chip = TemplateCard(tmpl)
            chip.clicked.connect(lambda _=False, t=tmpl: self._select_template(t.id))
            group.addButton(chip)
            self._template_buttons[tmpl.id] = chip
            chips.addWidget(chip, i // 3, i % 3)
        lay.addLayout(chips)

        # Details — flat, no section card
        lay.addSpacing(4)
        lay.addWidget(self._kicker("PROJECT DETAILS"))
        self.edit_name = QLineEdit()
        self.edit_name.setObjectName("home_search")
        self.edit_name.setPlaceholderText("Project name")
        self.edit_name.textChanged.connect(self._refresh_summary)
        lay.addWidget(_field("Project Name", self.edit_name))

        loc_lbl = QLabel("Save Location")
        loc_lbl.setObjectName("new_project_field_lbl")
        lay.addWidget(loc_lbl)
        loc_row = QHBoxLayout()
        loc_row.setSpacing(8)
        self.edit_location = QLineEdit()
        self.edit_location.setObjectName("home_search")
        self.edit_location.setReadOnly(True)
        self.edit_location.textChanged.connect(self._refresh_summary)
        loc_row.addWidget(self.edit_location, 1)
        browse = QPushButton("Browse…")
        browse.setObjectName("btn_secondary")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setFixedHeight(30)
        browse.clicked.connect(self._browse_location)
        loc_row.addWidget(browse)
        default = QPushButton("Default")
        default.setObjectName("btn_secondary")
        default.setCursor(Qt.CursorShape.PointingHandCursor)
        default.setFixedHeight(30)
        default.clicked.connect(lambda: self.edit_location.setText(str(PROJECT_DIR)))
        loc_row.addWidget(default)
        lay.addLayout(loc_row)

        # Starter footage
        lay.addSpacing(4)
        lay.addWidget(self._kicker("STARTER FOOTAGE (OPTIONAL)"))
        self.media_strip = StarterMediaStrip(self)
        self.media_strip.media_changed.connect(self._on_media_changed)
        lay.addWidget(self.media_strip)

        # Canvas
        lay.addSpacing(4)
        lay.addWidget(self._kicker("CANVAS & TIMELINE"))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.combo_aspect = QComboBox()
        self.combo_aspect.setObjectName("asr_option_combo")
        self.combo_aspect.addItems(ASPECT_CHOICES)
        self.combo_aspect.currentTextChanged.connect(self._refresh_summary)
        self.combo_res = QComboBox()
        self.combo_res.setObjectName("asr_option_combo")
        self.combo_res.addItems(RESOLUTION_CHOICES)
        self.combo_res.currentTextChanged.connect(self._refresh_summary)
        self.combo_fps = QComboBox()
        self.combo_fps.setObjectName("asr_option_combo")
        self.combo_fps.addItems(FPS_CHOICES)
        self.combo_fps.currentTextChanged.connect(self._refresh_summary)
        row.addWidget(_field("Aspect Ratio", self.combo_aspect), 1)
        row.addWidget(_field("Resolution", self.combo_res), 1)
        row.addWidget(_field("Frame Rate", self.combo_fps), 1)
        lay.addLayout(row)
        lay.addStretch(1)
        return col

    def _right_column(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(260)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._kicker("CANVAS PREVIEW"))
        lay.addSpacing(8)

        self.canvas = CanvasPreviewWidget(self)
        lay.addWidget(self.canvas)

        # Label sits below the paint area — never overlaps the divider
        self.lbl_canvas_size = QLabel("1920 × 1080")
        self.lbl_canvas_size.setObjectName("new_project_hint")
        self.lbl_canvas_size.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(6)
        lay.addWidget(self.lbl_canvas_size)

        lay.addSpacing(14)
        line = QFrame()
        line.setObjectName("prop_divider")
        line.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line)
        lay.addSpacing(12)

        lay.addWidget(self._kicker("SPECIFICATION SUMMARY"))
        lay.addSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        self.val_preset = QLabel("—")
        self.val_canvas = QLabel("—")
        self.val_fps = QLabel("—")
        self.val_storage = QLabel("Original Referenced")

        for i, (key, val) in enumerate((
            ("Preset", self.val_preset),
            ("Canvas", self.val_canvas),
            ("Frame Rate", self.val_fps),
            ("Storage", self.val_storage),
        )):
            k = QLabel(key)
            k.setObjectName("new_project_field_lbl")
            val.setObjectName("new_project_summary_val")
            val.setWordWrap(True)
            grid.addWidget(k, i, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(val, i, 1)
        lay.addLayout(grid)

        lay.addSpacing(14)
        line2 = QFrame()
        line2.setObjectName("prop_divider")
        line2.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line2)
        lay.addSpacing(12)

        lay.addWidget(self._kicker("TARGET PROJECT FILE"))
        lay.addSpacing(6)
        self.lbl_dest = QLabel()
        self.lbl_dest.setObjectName("new_project_path_preview")
        self.lbl_dest.setWordWrap(True)
        lay.addWidget(self.lbl_dest)

        lay.addSpacing(12)
        self.lbl_status = QLabel("✓ Ready to create")
        self.lbl_status.setObjectName("new_project_pill_ready")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_status)
        lay.addStretch(1)
        return panel

    @staticmethod
    def _kicker(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("new_project_kicker")
        return lbl

    def _browse_location(self):
        path = QFileDialog.getExistingDirectory(
            self, "Save Project To", self.edit_location.text() or str(PROJECT_DIR)
        )
        if path:
            self.edit_location.setText(path)

    def _select_template(self, template_id: str, *, apply_values: bool = True):
        self._template_id = template_id
        accent = primary_color()
        for tid, btn in self._template_buttons.items():
            active = tid == template_id
            btn.setChecked(active)
            btn.setIcon(icon(btn.template.icon, color=accent if active else COLOR_TEXT_SUB, size=16))
        if not apply_values:
            return
        tmpl = next((t for t in TEMPLATES if t.id == template_id), TEMPLATES[0])
        self._set_combo(self.combo_aspect, tmpl.aspect)
        self._set_combo(self.combo_res, tmpl.resolution)
        self._set_combo(self.combo_fps, tmpl.fps)
        self._refresh_summary()

    def _on_media_changed(self, path: str, info: dict):
        if not path or not info:
            self._refresh_summary()
            return
        name = self.edit_name.text().strip()
        if not name or name.lower() in {"untitled", "untitled project"}:
            stem = Path(path).stem.replace("_", " ").strip().title()
            if stem:
                self.edit_name.setText(stem)

        aspect = str(info.get("aspect") or "")
        if aspect in ASPECT_CHOICES:
            self._set_combo(self.combo_aspect, aspect)
        h = int(info.get("height") or 0)
        w = int(info.get("width") or 0)
        dim = max(w, h)
        if dim >= 3800 or h >= 2000:
            self._set_combo(self.combo_res, "2160p")
        elif dim >= 1900 or h >= 1000:
            self._set_combo(self.combo_res, "1080p")
        elif dim >= 1200 or h >= 700:
            self._set_combo(self.combo_res, "720p")
        fps_val = float(info.get("fps") or 0)
        if fps_val > 0:
            for opt in FPS_CHOICES:
                try:
                    if abs(float(opt.replace("fps", "").strip()) - fps_val) < 0.1:
                        self._set_combo(self.combo_fps, opt)
                        break
                except ValueError:
                    continue
        self._refresh_summary()

    def _refresh_summary(self):
        aspect = self.combo_aspect.currentText()
        res = self.combo_res.currentText()
        fps = self.combo_fps.currentText()
        self.canvas.update_canvas(aspect)

        pw, ph = _canvas_dimensions(aspect, res)
        size_txt = f"{aspect} · {pw}×{ph}" if aspect not in {"Original", "Adapted"} else f"{aspect} · {pw}×{ph}"
        self.lbl_canvas_size.setText(size_txt)

        preset = next((t.title for t in TEMPLATES if t.id == self._template_id), "Custom")
        self.val_preset.setText(preset)
        self.val_canvas.setText(f"{pw} × {ph}")
        self.val_fps.setText(fps)

        name = self.edit_name.text().strip() or "Untitled"
        folder = Path(self.edit_location.text().strip() or str(PROJECT_DIR))
        dest = folder / f"{_slug(name)}.jela.json"
        self.lbl_dest.setText(str(dest))

        if not self.edit_name.text().strip():
            self.lbl_status.setObjectName("new_project_pill_error")
            self.lbl_status.setText("Project name required")
            self.btn_create.setEnabled(False)
        elif dest.is_file():
            self.lbl_status.setObjectName("new_project_pill_warn")
            self.lbl_status.setText("File exists — timestamp will be added")
            self.btn_create.setEnabled(True)
        else:
            self.lbl_status.setObjectName("new_project_pill_ready")
            self.lbl_status.setText("✓ Ready to create")
            self.btn_create.setEnabled(True)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str):
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _load(self, data: dict):
        self.edit_name.setText(str(data.get("name") or "Untitled"))
        self.edit_name.selectAll()
        self.edit_location.setText(str(data.get("save_to") or PROJECT_DIR))
        self._set_combo(self.combo_aspect, str(data.get("aspect") or "16:9"))
        self._set_combo(self.combo_res, str(data.get("resolution") or "1080p"))
        self._set_combo(self.combo_fps, str(data.get("fps") or "30.00 fps"))
        media = str(data.get("media") or "").strip()
        if media and os.path.isfile(media):
            self.media_strip.load_media(media)

    def result_settings(self) -> dict:
        out = dict(self._data)
        out.update({
            "name": self.edit_name.text().strip() or "Untitled",
            "save_to": self.edit_location.text().strip() or str(PROJECT_DIR),
            "timeline_name": "Timeline 01",
            "media": self.media_strip.current_path(),
            "import_mode": "original",
            "color_space": "Rec. 709 SDR",
            "aspect": self.combo_aspect.currentText(),
            "resolution": self.combo_res.currentText(),
            "fps": self.combo_fps.currentText(),
            "arrange_layers": True,
            "proxy": False,
            "hw_decode": True,
            "template": self._template_id,
            "open_after_create": True,
        })
        return out

    def open_after_create(self) -> bool:
        return True
