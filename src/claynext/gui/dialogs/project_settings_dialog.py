"""Project details inspector + Modify dialog (Settings-style cards)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QRadioButton, QButtonGroup, QCheckBox, QFrame, QTabWidget,
    QFileDialog, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from claynext.models.dub_project import PROJECT_DIR
from claynext.gui.icons import icon

ASPECT_CHOICES = ["Original", "16:9", "9:16", "1:1", "4:3", "4:5"]
RESOLUTION_CHOICES = ["Adapted", "2160p", "1080p", "720p"]
FPS_CHOICES = ["Original", "24.00 fps", "25.00 fps", "30.00 fps", "60.00 fps"]
COLOR_SPACES = ["Rec. 709 SDR", "Rec. 2020 HLG", "Rec. 2020 PQ"]

_FIELD_H = 28


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
    """Project settings — card sections, clean tabs, 28px fields."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project settings")
        self.setModal(True)
        self.setMinimumSize(480, 540)
        self.resize(520, 580)
        self.setObjectName("project_settings_dialog")
        self._data = dict(settings or default_project_settings())
        self._init_ui()
        self._load(self._data)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("settingsTabs")
        self.tabs.addTab(self._details_tab(), icon("folder", size=13), "Details")
        self.tabs.addTab(self._performance_tab(), icon("activity", size=13), "Performance")
        root.addWidget(self.tabs, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setFixedHeight(_FIELD_H)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setFixedHeight(_FIELD_H)
        self.btn_save.setMinimumWidth(88)
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.accept)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_save)
        root.addLayout(btns)

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("settings_field_label")
        return lbl

    @staticmethod
    def _scroll_page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(12)
        scroll.setWidget(host)
        outer.addWidget(scroll)
        return page, lay

    @staticmethod
    def _card(title: str, hint: str = "") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("project_settings_card")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        hdr = QLabel(title)
        hdr.setObjectName("settings_section_title")
        lay.addWidget(hdr)
        if hint:
            note = QLabel(hint)
            note.setObjectName("settings_section_hint")
            note.setWordWrap(True)
            lay.addWidget(note)
        return card, lay

    def _labeled(self, label: str, widget: QWidget) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._field_label(label))
        lay.addWidget(widget)
        return wrap

    # ── tabs ─────────────────────────────────────────────────────────

    def _details_tab(self) -> QWidget:
        page, lay = self._scroll_page()

        # Project
        card, cl = self._card("Project", "Name and where this project is saved.")
        self.edit_name = QLineEdit()
        self.edit_name.setFixedHeight(_FIELD_H)
        self.edit_name.setPlaceholderText("Project name")
        cl.addWidget(self._labeled("Name", self.edit_name))

        path_row = QWidget()
        pr = QHBoxLayout(path_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(6)
        self.edit_save = QLineEdit()
        self.edit_save.setFixedHeight(_FIELD_H)
        self.edit_save.setPlaceholderText(str(PROJECT_DIR))
        btn_browse = QPushButton("…")
        btn_browse.setObjectName("project_settings_browse")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setFixedSize(_FIELD_H, _FIELD_H)
        btn_browse.setToolTip("Browse folder")
        btn_browse.clicked.connect(self._browse_save)
        pr.addWidget(self.edit_save, 1)
        pr.addWidget(btn_browse, 0)
        cl.addWidget(self._labeled("Save to", path_row))
        lay.addWidget(card)

        # Media
        card, cl = self._card("Media", "How imported files are stored and colored.")
        self.radio_copy = QRadioButton("Copy media to project")
        self.radio_keep = QRadioButton("Stay in original location")
        self.radio_keep.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.radio_copy)
        group.addButton(self.radio_keep)
        cl.addWidget(self._field_label("Imported media"))
        cl.addWidget(self.radio_copy)
        cl.addWidget(self.radio_keep)

        self.combo_color = QComboBox()
        self.combo_color.setFixedHeight(_FIELD_H)
        self.combo_color.addItems(COLOR_SPACES)
        cl.addWidget(self._labeled("Color space", self.combo_color))

        self.chk_layers = QCheckBox("Arrange layers")
        self.chk_layers.setChecked(True)
        self.chk_layers.toggled.connect(self._on_layers)
        cl.addWidget(self.chk_layers)
        self.lbl_layers_note = QLabel("Cannot be turned off after turned on.")
        self.lbl_layers_note.setObjectName("project_settings_warn")
        self.lbl_layers_note.setWordWrap(True)
        self.lbl_layers_note.setVisible(False)
        cl.addWidget(self.lbl_layers_note)
        lay.addWidget(card)

        # Timeline
        card, cl = self._card("Timeline", "Canvas format for the active timeline.")
        self.lbl_apply = QLineEdit()
        self.lbl_apply.setFixedHeight(_FIELD_H)
        self.lbl_apply.setReadOnly(True)
        self.lbl_apply.setObjectName("project_settings_readonly")
        cl.addWidget(self._labeled("Apply to", self.lbl_apply))

        self.combo_aspect = QComboBox()
        self.combo_aspect.setFixedHeight(_FIELD_H)
        self.combo_aspect.addItems(ASPECT_CHOICES)
        cl.addWidget(self._labeled("Aspect ratio", self.combo_aspect))

        self.combo_res = QComboBox()
        self.combo_res.setFixedHeight(_FIELD_H)
        self.combo_res.addItems(RESOLUTION_CHOICES)
        cl.addWidget(self._labeled("Resolution", self.combo_res))

        self.combo_fps = QComboBox()
        self.combo_fps.setFixedHeight(_FIELD_H)
        self.combo_fps.addItems(FPS_CHOICES)
        cl.addWidget(self._labeled("Frame rate", self.combo_fps))
        lay.addWidget(card)

        lay.addStretch(1)
        return page

    def _performance_tab(self) -> QWidget:
        page, lay = self._scroll_page()
        card, cl = self._card(
            "Playback",
            "Proxy keeps the original file and plays a lighter copy.",
        )
        self.chk_proxy = QCheckBox("Use proxy media")
        self.chk_hw = QCheckBox("Hardware decode")
        self.chk_hw.setChecked(True)
        cl.addWidget(self.chk_proxy)
        cl.addWidget(self.chk_hw)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _on_layers(self, on: bool):
        self.lbl_layers_note.setVisible(bool(on))

    def _browse_save(self):
        path = QFileDialog.getExistingDirectory(
            self, "Save project to", self.edit_save.text() or str(PROJECT_DIR)
        )
        if path:
            self.edit_save.setText(path)

    def _load(self, data: dict):
        self.edit_name.setText(str(data.get("name") or "Untitled"))
        self.edit_save.setText(str(data.get("save_to") or PROJECT_DIR))
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
            "save_to": self.edit_save.text().strip() or str(PROJECT_DIR),
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
