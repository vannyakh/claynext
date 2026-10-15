"""CapCut-style project details inspector + Modify dialog."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QRadioButton, QButtonGroup, QCheckBox, QFrame, QTabWidget,
    QFileDialog, QScrollArea,
)
from PySide6.QtCore import Qt, Signal

from claynext.models.dub_project import PROJECT_DIR

ASPECT_CHOICES = ["Original", "16:9", "9:16", "1:1", "4:3", "4:5"]
RESOLUTION_CHOICES = ["Adapted", "2160p", "1080p", "720p"]
FPS_CHOICES = ["Original", "24.00 fps", "25.00 fps", "30.00 fps", "60.00 fps"]
COLOR_SPACES = ["Rec. 709 SDR", "Rec. 2020 HLG", "Rec. 2020 PQ"]


def default_project_settings(*, name: str = "", media: str = "") -> dict:
    return {
        "name": name or "Untitled",
        "save_to": str(PROJECT_DIR),
        "import_mode": "original",
        "color_space": "Rec. 709 SDR",
        "arrange_layers": True,
        "proxy": False,
        "hw_decode": True,
        "timeline_name": "Timeline 01",
        "aspect": "Original",
        "resolution": "Adapted",
        "fps": "Original",
        "path": "",
        "media": media or "",
    }


def _kv(key: str) -> tuple[QWidget, QLabel]:
    row = QWidget()
    row.setObjectName("prop_row")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 3, 0, 3)
    lay.setSpacing(8)
    k = QLabel(key)
    k.setObjectName("prop_key")
    v = QLabel("—")
    v.setObjectName("prop_val")
    v.setWordWrap(True)
    v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lay.addWidget(k, 0, Qt.AlignmentFlag.AlignTop)
    lay.addWidget(v, 1)
    return row, v


def _field(label: str, widget: QWidget) -> QWidget:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lbl = QLabel(label)
    lbl.setObjectName("asr_field_label")
    lay.addWidget(lbl)
    lay.addWidget(widget)
    return wrap


class ProjectInfoPage(QWidget):
    """Read-only Details inspector; Modify opens project settings."""

    modify_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("project_info_page")
        self._vals: dict[str, QLabel] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        # Title lives in the sticky properties header.
        self.header_title = QLabel("Project")
        self.header_title.hide()

        for key, label in (
            ("name", "Name"),
            ("path", "Path"),
            ("imported", "Imported media"),
            ("layers", "Arrange layers"),
            ("proxy", "Proxy"),
        ):
            row, val = _kv(label)
            self._vals[key] = val
            lay.addWidget(row)

        line = QFrame()
        line.setObjectName("prop_divider")
        line.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line)

        for key, label in (
            ("timeline", "Timeline name"),
            ("aspect", "Aspect ratio"),
            ("resolution", "Resolution"),
            ("fps", "Frame rate"),
        ):
            row, val = _kv(label)
            self._vals[key] = val
            lay.addWidget(row)

        lay.addStretch(1)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.btn_modify = QPushButton("Modify")
        self.btn_modify.setObjectName("prop_modify_btn")
        self.btn_modify.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_modify.clicked.connect(self.modify_requested.emit)
        foot.addWidget(self.btn_modify)
        lay.addLayout(foot)

    def show_empty(self):
        self.bind({}, media={})

    def bind(self, project: dict, media: dict | None = None, **_unused):
        project = project or {}
        media = media or {}
        name = str(project.get("name") or media.get("name") or "Untitled")
        path = str(project.get("path") or project.get("save_to") or media.get("path") or "—")
        imported = "Stay in original location" if project.get("import_mode", "original") == "original" else "Copied to project"
        self._vals["name"].setText(name)
        self._vals["path"].setText(path)
        self._vals["imported"].setText(imported)
        self._vals["layers"].setText("Turned on" if project.get("arrange_layers", True) else "Turned off")
        self._vals["proxy"].setText("Turned on" if project.get("proxy") else "Turned off")
        self._vals["timeline"].setText(str(project.get("timeline_name") or "Timeline 01"))
        aspect = str(project.get("aspect") or "Original")
        if aspect == "Original" and media.get("aspect"):
            self._vals["aspect"].setText("Original")
        else:
            self._vals["aspect"].setText(aspect)
        self._vals["resolution"].setText(str(project.get("resolution") or "Adapted"))
        fps_set = str(project.get("fps") or "Original")
        if fps_set == "Original" and media.get("fps"):
            self._vals["fps"].setText(f"{float(media['fps']):.2f}fps")
        else:
            self._vals["fps"].setText(fps_set.replace(" ", ""))


class ProjectSettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project settings")
        self.setModal(True)
        self.setMinimumSize(420, 520)
        self.resize(460, 560)
        self.setObjectName("project_settings_dialog")
        self._data = dict(settings or default_project_settings())
        self._init_ui()
        self._load(self._data)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        title = QLabel("Project settings")
        title.setObjectName("transcript_panel_title")
        root.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("project_settings_tabs")
        self.tabs.addTab(self._details_tab(), "Details")
        self.tabs.addTab(self._performance_tab(), "Performance")
        root.addWidget(self.tabs, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_save, 1)
        btns.addWidget(self.btn_cancel, 1)
        root.addLayout(btns)

    def _details_tab(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 8, 4, 8)
        lay.setSpacing(10)

        sec = QLabel("Details")
        sec.setObjectName("asr_field_label")
        lay.addWidget(sec)

        self.edit_name = QLineEdit()
        self.edit_name.setObjectName("transcript_search")
        lay.addWidget(_field("Name", self.edit_name))

        save_row = QWidget()
        s_l = QVBoxLayout(save_row)
        s_l.setContentsMargins(0, 0, 0, 0)
        s_l.setSpacing(4)
        s_l.addWidget(QLabel("Save to"))
        path_row = QHBoxLayout()
        self.lbl_save = QLabel(str(PROJECT_DIR))
        self.lbl_save.setObjectName("prop_val")
        self.lbl_save.setWordWrap(True)
        btn_browse = QPushButton("…")
        btn_browse.setFixedWidth(32)
        btn_browse.setObjectName("asr_export_btn")
        btn_browse.clicked.connect(self._browse_save)
        path_row.addWidget(self.lbl_save, 1)
        path_row.addWidget(btn_browse, 0)
        s_l.addLayout(path_row)
        lay.addWidget(save_row)

        imp = QLabel("Imported media")
        imp.setObjectName("asr_field_label")
        lay.addWidget(imp)
        self.radio_copy = QRadioButton("Copy media to project")
        self.radio_keep = QRadioButton("Stay in original location")
        self.radio_keep.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.radio_copy)
        group.addButton(self.radio_keep)
        lay.addWidget(self.radio_copy)
        lay.addWidget(self.radio_keep)

        self.combo_color = QComboBox()
        self.combo_color.setObjectName("asr_option_combo")
        self.combo_color.addItems(COLOR_SPACES)
        lay.addWidget(_field("Color space", self.combo_color))

        self.chk_layers = QCheckBox("Arrange layers")
        self.chk_layers.setChecked(True)
        self.chk_layers.toggled.connect(self._on_layers)
        lay.addWidget(self.chk_layers)
        self.lbl_layers_note = QLabel("Cannot be turned off after turned on")
        self.lbl_layers_note.setObjectName("prop_warn")
        self.lbl_layers_note.setVisible(False)
        lay.addWidget(self.lbl_layers_note)

        line = QFrame()
        line.setObjectName("prop_divider")
        line.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line)

        tl = QLabel("Timeline settings")
        tl.setObjectName("asr_field_label")
        lay.addWidget(tl)
        self.lbl_apply = QLabel("Timeline 01")
        self.lbl_apply.setObjectName("prop_val")
        lay.addWidget(_field("Apply to", self.lbl_apply))

        self.combo_aspect = QComboBox()
        self.combo_aspect.setObjectName("asr_option_combo")
        self.combo_aspect.addItems(ASPECT_CHOICES)
        lay.addWidget(_field("Aspect ratio", self.combo_aspect))

        self.combo_res = QComboBox()
        self.combo_res.setObjectName("asr_option_combo")
        self.combo_res.addItems(RESOLUTION_CHOICES)
        lay.addWidget(_field("Resolution", self.combo_res))

        self.combo_fps = QComboBox()
        self.combo_fps.setObjectName("asr_option_combo")
        self.combo_fps.addItems(FPS_CHOICES)
        lay.addWidget(_field("Frame rate", self.combo_fps))
        lay.addStretch(1)
        scroll.setWidget(body)
        wrap = QVBoxLayout(page)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(scroll)
        return page

    def _performance_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        hint = QLabel("Playback performance for this project")
        hint.setObjectName("transcript_count")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.chk_proxy = QCheckBox("Use proxy media")
        self.chk_hw = QCheckBox("Hardware decode")
        self.chk_hw.setChecked(True)
        lay.addWidget(self.chk_proxy)
        lay.addWidget(self.chk_hw)
        note = QLabel("Proxy keeps the original file and plays a lighter copy.")
        note.setObjectName("transcript_count")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        return page

    def _on_layers(self, on: bool):
        self.lbl_layers_note.setVisible(bool(on))

    def _browse_save(self):
        path = QFileDialog.getExistingDirectory(self, "Save project to", self.lbl_save.text())
        if path:
            self.lbl_save.setText(path)

    def _load(self, data: dict):
        self.edit_name.setText(str(data.get("name") or "Untitled"))
        self.lbl_save.setText(str(data.get("save_to") or PROJECT_DIR))
        if data.get("import_mode") == "copy":
            self.radio_copy.setChecked(True)
        else:
            self.radio_keep.setChecked(True)
        idx = self.combo_color.findText(str(data.get("color_space") or ""))
        if idx >= 0:
            self.combo_color.setCurrentIndex(idx)
        layers = bool(data.get("arrange_layers", True))
        self.chk_layers.blockSignals(True)
        self.chk_layers.setChecked(layers)
        self.chk_layers.setEnabled(not layers)
        self.chk_layers.blockSignals(False)
        self.lbl_layers_note.setVisible(layers)
        self.lbl_apply.setText(str(data.get("timeline_name") or "Timeline 01"))
        for combo, key, fallback in (
            (self.combo_aspect, "aspect", "Original"),
            (self.combo_res, "resolution", "Adapted"),
            (self.combo_fps, "fps", "Original"),
        ):
            i = combo.findText(str(data.get(key) or fallback))
            if i >= 0:
                combo.setCurrentIndex(i)
        self.chk_proxy.setChecked(bool(data.get("proxy")))
        self.chk_hw.setChecked(bool(data.get("hw_decode", True)))

    def result_settings(self) -> dict:
        out = dict(self._data)
        out.update({
            "name": self.edit_name.text().strip() or "Untitled",
            "save_to": self.lbl_save.text().strip(),
            "import_mode": "copy" if self.radio_copy.isChecked() else "original",
            "color_space": self.combo_color.currentText(),
            "arrange_layers": self.chk_layers.isChecked(),
            "timeline_name": self.lbl_apply.text(),
            "aspect": self.combo_aspect.currentText(),
            "resolution": self.combo_res.currentText(),
            "fps": self.combo_fps.currentText(),
            "proxy": self.chk_proxy.isChecked(),
            "hw_decode": self.chk_hw.isChecked(),
        })
        return out

