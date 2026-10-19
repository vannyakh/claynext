"""Project canvas controls on the properties page."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QButtonGroup,
    QSizePolicy,
    QToolButton,
    QColorDialog,
    QSlider,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QPixmap,
)

from claynext.constants.theme_constants import COLOR_TEXT_SUB
from claynext.gui.components.field_controls import SelectField
from claynext.gui.components.media_preview import blur_image
from claynext.gui.components.scrub_spin import ScrubSpinBox
from claynext.gui.icons import icon
from claynext.models.adjust import FILTER_PRESETS, filter_sample_rgb, grade_filter_preview
from claynext.models.canvas import (
    BLUR_LEVELS,
    CANVAS_BACKGROUNDS,
    CANVAS_COLORS,
    CANVAS_RATIOS,
    DEFAULT_CANVAS,
    POSITION_RANGE,
    SCALE_RANGE,
    clean_canvas,
)

class PropsCanvas:
    def _build_canvas_section(self):
        self._canvas_color = DEFAULT_CANVAS["color"]
        # Aspect ratio is project-level (project settings); keep value for canvas emit only.
        self._canvas_ratio = DEFAULT_CANVAS["ratio"]
        self._ratio_keys = [key for key, _label, _value in CANVAS_RATIOS]
        self.sec_canvas, cv = self._section("Canvas", bare=True)
        cv.setSpacing(6)

        tr_head = QHBoxLayout()
        tr_head.setContentsMargins(0, 0, 0, 0)
        lbl_tr = self._field_label("TRANSFORM")
        self.btn_reset_canvas = QPushButton("Reset")
        self.btn_reset_canvas.setObjectName("dub_props_ghost_btn")
        self.btn_reset_canvas.setIcon(icon("refresh", color=COLOR_TEXT_SUB, size=10))
        self.btn_reset_canvas.setIconSize(QSize(10, 10))
        self.btn_reset_canvas.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_canvas.setToolTip("Centre the video and reset scale to 100%")
        self.btn_reset_canvas.clicked.connect(self._reset_canvas_transform)
        tr_head.addWidget(lbl_tr, 1)
        tr_head.addWidget(self.btn_reset_canvas)
        cv.addLayout(tr_head)

        scale_row = QHBoxLayout()
        scale_row.setContentsMargins(0, 0, 0, 0)
        scale_row.setSpacing(6)
        self.lbl_scale = QLabel("Scale")
        self.lbl_scale.setObjectName("asr_field_label")
        self.slider_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_scale.setRange(SCALE_RANGE[0], SCALE_RANGE[1])
        self.slider_scale.setValue(100)
        self.slider_scale.valueChanged.connect(self._on_scale_slider)
        self.spin_scale = ScrubSpinBox()
        self.spin_scale.setRange(*SCALE_RANGE)
        self.spin_scale.setSuffix("%")
        self.spin_scale.setFixedWidth(64)
        self.spin_scale.valueChanged.connect(self._on_canvas_spin)
        self.btn_scale_100 = QPushButton("100%")
        self.btn_scale_100.setObjectName("dub_props_ghost_btn")
        self.btn_scale_100.setFixedWidth(40)
        self.btn_scale_100.setToolTip("Reset scale to 100%")
        self.btn_scale_100.clicked.connect(lambda: self.spin_scale.setValue(100))
        scale_row.addWidget(self.lbl_scale)
        scale_row.addWidget(self.slider_scale, 1)
        scale_row.addWidget(self.spin_scale)
        scale_row.addWidget(self.btn_scale_100)
        cv.addLayout(scale_row)

        pos_row = QHBoxLayout()
        pos_row.setContentsMargins(0, 4, 0, 0)
        pos_row.setSpacing(6)
        cell_px, self.lbl_pos_x, self.spin_pos_x = self._paired_spin_cell("Position X", *POSITION_RANGE, prefix="X ", suffix="%")
        cell_py, self.lbl_pos_y, self.spin_pos_y = self._paired_spin_cell("Position Y", *POSITION_RANGE, prefix="Y ", suffix="%")
        self.spin_pos_x.valueChanged.connect(self._on_canvas_spin)
        self.spin_pos_y.valueChanged.connect(self._on_canvas_spin)
        pos_row.addWidget(cell_px, 1)
        pos_row.addWidget(cell_py, 1)
        cv.addLayout(pos_row)

        cv.addWidget(self._field_label("BACKGROUND"))
        self._bg_keys = [key for key, _label in CANVAS_BACKGROUNDS]
        self.bg_select = SelectField(size="sm", width=None)
        self.bg_select.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for key, label in CANVAS_BACKGROUNDS:
            self.bg_select.addItem(label, key)
        self.bg_select.setToolTip("Canvas background fill")
        self.bg_select.value_changed.connect(self._emit_canvas)
        cv.addWidget(self.bg_select)

        self.blur_row = QWidget()
        blur_l = QHBoxLayout(self.blur_row)
        blur_l.setContentsMargins(0, 0, 0, 0)
        blur_l.setSpacing(6)
        self.blur_group = QButtonGroup(self)
        self.blur_group.setExclusive(True)
        for level in BLUR_LEVELS:
            btn = self._swatch_btn(f"Blur strength {level}", QSize(56, 34))
            self.blur_group.addButton(btn, level)
            blur_l.addWidget(btn)
        blur_l.addStretch(1)
        self.blur_group.idClicked.connect(self._emit_canvas)
        cv.addWidget(self.blur_row)

        self.color_row = QWidget()
        color_l = QGridLayout(self.color_row)
        color_l.setContentsMargins(0, 0, 0, 0)
        color_l.setSpacing(6)
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        for i, color in enumerate(CANVAS_COLORS):
            btn = self._swatch_btn(color, QSize(26, 26))
            btn.setIcon(self._color_icon(color, 18))
            btn.setIconSize(QSize(18, 18))
            self.color_group.addButton(btn, i)
            color_l.addWidget(btn, 0, i)
        self.btn_color_custom = self._swatch_btn("Custom colour…", QSize(26, 26))
        self.btn_color_custom.setCheckable(False)
        self.btn_color_custom.setText("+")
        self.btn_color_custom.clicked.connect(self._pick_canvas_color)
        color_l.addWidget(self.btn_color_custom, 0, len(CANVAS_COLORS))
        color_l.setColumnStretch(len(CANVAS_COLORS) + 1, 1)
        self.color_group.idClicked.connect(self._on_canvas_swatch)
        cv.addWidget(self.color_row)
        self.lbl_canvas_hint = self._hint("")
        cv.addWidget(self.lbl_canvas_hint)

    def set_blur_source(self, image: QImage):
        """Blur + filter thumbnails rendered from a frame of the footage."""
        self._filter_source = None if image.isNull() else image
        self._refresh_filter_thumbs()
        for level in BLUR_LEVELS:
            btn = self.blur_group.button(level)
            big = blur_image(image, QSize(320, 192), level) if not image.isNull() else QPixmap()
            if big.isNull():
                btn.setIcon(QIcon())
                btn.setText(str(level))
                continue
            btn.setText("")
            btn.setIcon(QIcon(big.scaled(52, 30, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)))
            btn.setIconSize(QSize(52, 30))

    def _filter_grid(self) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("dub_props_filter_grid")
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(5)
        cols = 3
        for i, key in enumerate(self._preset_keys):
            label = FILTER_PRESETS[key][0]
            btn = QToolButton()
            btn.setObjectName("dub_props_filter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setText(label)
            btn.setToolTip(f"{label} look")
            btn.setIconSize(QSize(72, 42))
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.preset_group.addButton(btn, i)
            grid.addWidget(btn, i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        return wrap

    def _refresh_filter_thumbs(self):
        """Bake graded samples onto each preset tile (footage frame or synthetic)."""
        rgb = self._filter_rgb()
        for i, key in enumerate(self._preset_keys):
            btn = self.preset_group.button(i)
            if btn is None:
                continue
            pix = self._rgb_thumb(grade_filter_preview(rgb, key), 72, 42)
            btn.setIcon(QIcon(pix))
            btn.setIconSize(QSize(72, 42))

    def _filter_rgb(self):
        src = self._filter_source
        if src is not None and not src.isNull():
            scaled = src.scaled(72, 42, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
            x = max(0, (scaled.width() - 72) // 2)
            y = max(0, (scaled.height() - 42) // 2)
            crop = scaled.copy(x, y, 72, 42).convertToFormat(QImage.Format.Format_RGB888)
            w, h = crop.width(), crop.height()
            bpl = crop.bytesPerLine()
            buf = bytes(crop.constBits())
            # QImage may pad rows — reshape via bytes-per-line.
            import numpy as np
            arr = np.frombuffer(buf, dtype=np.uint8)
            if bpl == w * 3:
                return arr.reshape(h, w, 3).copy()
            rows = [arr[r * bpl:r * bpl + w * 3] for r in range(h)]
            return np.asarray(rows, dtype=np.uint8).reshape(h, w, 3).copy()
        return filter_sample_rgb(42, 72).copy()

    @staticmethod
    def _rgb_thumb(rgb, w: int, h: int) -> QPixmap:
        import numpy as np
        data = np.ascontiguousarray(rgb, dtype=np.uint8)
        image = QImage(data.data, data.shape[1], data.shape[0], data.shape[1] * 3, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(image.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    def canvas_state(self) -> dict:
        ratio = self._canvas_ratio if self._canvas_ratio in self._ratio_keys else DEFAULT_CANVAS["ratio"]
        bg = self.bg_select.current_value() or self._bg_keys[0]
        return clean_canvas({
            "ratio": ratio,
            "scale": self.spin_scale.value(),
            "x": self.spin_pos_x.value(),
            "y": self.spin_pos_y.value(),
            "bg": bg,
            "blur": self.blur_group.checkedId() if self.blur_group.checkedId() > 0 else 2,
            "color": self._canvas_color,
        })

    def set_canvas_state(self, canvas: dict | None):
        c = clean_canvas(canvas)
        was = self._block
        self._block = True
        self._canvas_ratio = c["ratio"]
        self.bg_select.blockSignals(True)
        self.bg_select.set_value(c["bg"])
        self.bg_select.blockSignals(False)
        self.blur_group.button(c["blur"]).setChecked(True)
        self._canvas_color = c["color"]
        self._check_color_swatch()
        self.show_transform(c)
        self._block = was
        self._sync_canvas_rows()

    def show_transform(self, transform: dict):
        """Mirror a drag on the preview handles without re-emitting."""
        for spin, key in ((self.spin_scale, "scale"), (self.spin_pos_x, "x"), (self.spin_pos_y, "y")):
            if key in transform:
                spin.blockSignals(True)
                spin.setValue(int(transform[key]))
                spin.blockSignals(False)
        if hasattr(self, "slider_scale") and "scale" in transform:
            self.slider_scale.blockSignals(True)
            self.slider_scale.setValue(int(transform["scale"]))
            self.slider_scale.blockSignals(False)
        self._relabel_canvas()

    def show_canvas_hint(self, covered: bool):
        bg = self.bg_select.current_value() or "none"
        self.lbl_canvas_hint.setVisible(covered and bg != "none")
        self.lbl_canvas_hint.setText("The video fills the canvas · scale it down to see the background.")

    def _relabel_canvas(self):
        self.lbl_scale.setText("Scale")
        self.lbl_pos_x.setText("Position X")
        self.lbl_pos_y.setText("Position Y")

    def _sync_canvas_rows(self):
        bg = self.bg_select.current_value() or "none"
        self.blur_row.setVisible(bg == "blur")
        self.color_row.setVisible(bg == "color")

    def _check_color_swatch(self):
        self.color_group.setExclusive(False)
        for i, btn in enumerate(self.color_group.buttons()):
            btn.setChecked(CANVAS_COLORS[i] == self._canvas_color)
        self.color_group.setExclusive(True)
        custom = self._canvas_color not in CANVAS_COLORS
        self.btn_color_custom.setIcon(self._color_icon(self._canvas_color, 18) if custom else QIcon())
        self.btn_color_custom.setText("" if custom else "+")

    def _on_canvas_spin(self, *_):
        if hasattr(self, "slider_scale"):
            self.slider_scale.blockSignals(True)
            self.slider_scale.setValue(self.spin_scale.value())
            self.slider_scale.blockSignals(False)
        self._emit_canvas()

    def _on_scale_slider(self, value: int):
        self.spin_scale.setValue(value)

    def _on_canvas_swatch(self, index: int):
        self._canvas_color = CANVAS_COLORS[index]
        self._check_color_swatch()
        self._emit_canvas()

    def _pick_canvas_color(self):
        color = QColorDialog.getColor(QColor(self._canvas_color), self, "Canvas background colour")
        if color.isValid():
            self._canvas_color = color.name().lower()
            self._check_color_swatch()
            self._emit_canvas()

    def _reset_canvas_transform(self):
        self.show_transform({"scale": 100, "x": 0, "y": 0})
        self._emit_canvas()

    def _emit_canvas(self, *_):
        self._sync_canvas_rows()
        if not self._block:
            self.canvas_changed.emit(self.canvas_state())
