"""Clean New Project dialog — templates, essentials, live canvas preview."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
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
    QVBoxLayout,
    QWidget,
)

from claynext.constants.project_constants import (
    NEW_PROJECT_FIELD_H,
    TEMPLATES,
    canvas_dimensions,
    template_by_id,
)
from claynext.gui.dialogs.new_project_widgets import (
    CanvasPreviewWidget,
    TemplateCard,
    labeled_field,
)
from claynext.gui.dialogs.project_settings_dialog import (
    ASPECT_CHOICES,
    FPS_CHOICES,
    RESOLUTION_CHOICES,
    default_project_settings,
)
from claynext.gui.icons import icon
from claynext.models.dub_project import PROJECT_DIR, _slug


class NewProjectDialog(QDialog):
    """Clean two-column New Project: templates + essentials + preview."""

    def __init__(self, parent=None, *, defaults: dict | None = None):
        super().__init__(parent)
        self.setObjectName("new_project_dialog")
        self.setWindowTitle("New Project")
        self.setModal(True)
        self.setMinimumSize(720, 460)
        self.resize(760, 500)

        self._data = dict(defaults or default_project_settings(name="Untitled"))
        self._template_id = "hd_landscape"
        self._template_buttons: dict[str, TemplateCard] = {}

        self._build_ui()
        self._load(self._data)
        self._select_template("hd_landscape", apply_values=True)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        title = QLabel("New Project")
        title.setObjectName("new_project_title")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._left_column(), 1)
        body.addWidget(self._right_column(), 0)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        tip = QLabel("Canvas options can also be changed inside Studio.")
        tip.setObjectName("new_project_hint")
        footer.addWidget(tip)
        footer.addStretch(1)

        cancel = QPushButton("Cancel")
        cancel.setObjectName("btn_secondary")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setFixedHeight(NEW_PROJECT_FIELD_H)
        cancel.setMinimumWidth(84)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)

        self.btn_create = QPushButton("Create Project")
        self.btn_create.setObjectName("btn_primary")
        self.btn_create.setIcon(icon("plus", color="#ffffff", size=13))
        self.btn_create.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create.setFixedHeight(NEW_PROJECT_FIELD_H)
        self.btn_create.setMinimumWidth(120)
        self.btn_create.setDefault(True)
        self.btn_create.clicked.connect(self.accept)
        footer.addWidget(self.btn_create)
        root.addLayout(footer)

    def _left_column(self) -> QWidget:
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Templates — flat chips, no group card
        lay.addWidget(self._kicker("PROJECT TEMPLATES"))
        chips = QGridLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setHorizontalSpacing(5)
        chips.setVerticalSpacing(5)
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
        lay.addSpacing(2)
        lay.addWidget(self._kicker("PROJECT DETAILS"))
        self.edit_name = QLineEdit()
        self.edit_name.setObjectName("home_search")
        self.edit_name.setFixedHeight(NEW_PROJECT_FIELD_H)
        self.edit_name.setPlaceholderText("Project name")
        self.edit_name.textChanged.connect(self._refresh_summary)
        lay.addWidget(labeled_field("Project Name", self.edit_name))

        loc_lbl = QLabel("Save Location")
        loc_lbl.setObjectName("new_project_field_lbl")
        lay.addWidget(loc_lbl)
        loc_row = QHBoxLayout()
        loc_row.setSpacing(6)
        self.edit_location = QLineEdit()
        self.edit_location.setObjectName("home_search")
        self.edit_location.setFixedHeight(NEW_PROJECT_FIELD_H)
        self.edit_location.setReadOnly(True)
        self.edit_location.textChanged.connect(self._refresh_summary)
        loc_row.addWidget(self.edit_location, 1)
        browse = QPushButton("Browse…")
        browse.setObjectName("btn_secondary")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setFixedHeight(NEW_PROJECT_FIELD_H)
        browse.clicked.connect(self._browse_location)
        loc_row.addWidget(browse)
        default = QPushButton("Default")
        default.setObjectName("btn_secondary")
        default.setCursor(Qt.CursorShape.PointingHandCursor)
        default.setFixedHeight(NEW_PROJECT_FIELD_H)
        default.clicked.connect(lambda: self.edit_location.setText(str(PROJECT_DIR)))
        loc_row.addWidget(default)
        lay.addLayout(loc_row)

        # Canvas
        lay.addSpacing(2)
        lay.addWidget(self._kicker("CANVAS & TIMELINE"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.combo_aspect = QComboBox()
        self.combo_aspect.setObjectName("asr_option_combo")
        self.combo_aspect.setFixedHeight(NEW_PROJECT_FIELD_H)
        self.combo_aspect.addItems(ASPECT_CHOICES)
        self.combo_aspect.currentTextChanged.connect(self._refresh_summary)
        self.combo_res = QComboBox()
        self.combo_res.setObjectName("asr_option_combo")
        self.combo_res.setFixedHeight(NEW_PROJECT_FIELD_H)
        self.combo_res.addItems(RESOLUTION_CHOICES)
        self.combo_res.currentTextChanged.connect(self._refresh_summary)
        self.combo_fps = QComboBox()
        self.combo_fps.setObjectName("asr_option_combo")
        self.combo_fps.setFixedHeight(NEW_PROJECT_FIELD_H)
        self.combo_fps.addItems(FPS_CHOICES)
        self.combo_fps.currentTextChanged.connect(self._refresh_summary)
        row.addWidget(labeled_field("Aspect Ratio", self.combo_aspect), 1)
        row.addWidget(labeled_field("Resolution", self.combo_res), 1)
        row.addWidget(labeled_field("Frame Rate", self.combo_fps), 1)
        lay.addLayout(row)
        lay.addStretch(1)
        return col

    def _right_column(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(220)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._kicker("CANVAS PREVIEW"))
        lay.addSpacing(6)

        self.canvas = CanvasPreviewWidget(self)
        lay.addWidget(self.canvas)

        # Label sits below the paint area — never overlaps the divider
        self.lbl_canvas_size = QLabel("1920 × 1080")
        self.lbl_canvas_size.setObjectName("new_project_hint")
        self.lbl_canvas_size.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(4)
        lay.addWidget(self.lbl_canvas_size)

        lay.addSpacing(10)
        line = QFrame()
        line.setObjectName("prop_divider")
        line.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line)
        lay.addSpacing(8)

        lay.addWidget(self._kicker("SPECIFICATION SUMMARY"))
        lay.addSpacing(6)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
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

        lay.addSpacing(10)
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
        for tid, btn in self._template_buttons.items():
            btn.setChecked(tid == template_id)
        if not apply_values:
            return
        tmpl = template_by_id(template_id)
        self._set_combo(self.combo_aspect, tmpl.aspect)
        self._set_combo(self.combo_res, tmpl.resolution)
        self._set_combo(self.combo_fps, tmpl.fps)
        self._refresh_summary()

    def _refresh_summary(self):
        aspect = self.combo_aspect.currentText()
        res = self.combo_res.currentText()
        fps = self.combo_fps.currentText()
        self.canvas.update_canvas(aspect)

        pw, ph = canvas_dimensions(aspect, res)
        size_txt = f"{aspect} · {pw}×{ph}" if aspect not in {"Original", "Adapted"} else f"{aspect} · {pw}×{ph}"
        self.lbl_canvas_size.setText(size_txt)

        preset = template_by_id(self._template_id).title
        self.val_preset.setText(preset)
        self.val_canvas.setText(f"{pw} × {ph}")
        self.val_fps.setText(fps)

        name = self.edit_name.text().strip() or "Untitled"
        folder = Path(self.edit_location.text().strip() or str(PROJECT_DIR))
        dest = folder / f"{_slug(name)}.claynext.json"

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

    def result_settings(self) -> dict:
        out = dict(self._data)
        out.update({
            "name": self.edit_name.text().strip() or "Untitled",
            "save_to": self.edit_location.text().strip() or str(PROJECT_DIR),
            "timeline_name": "Timeline 01",
            "media": "",
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

