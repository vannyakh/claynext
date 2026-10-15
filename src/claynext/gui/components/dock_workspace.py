from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QMainWindow, QDockWidget, QFrame, QLabel, QToolButton,
    QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPalette

from claynext.constants.theme_constants import COLOR_BG_SIDEBAR
from claynext.gui.icons import icon

_QWIDGETSIZE_MAX = 16777215
# Compact dock titles — intentionally shorter than shelf panel headers (40px).
DOCK_HEADER_H = 36
_EXTRA_H = 28


class DockHeader(QFrame):
    """Dock title bar with close / float buttons, the title, and extra controls."""

    def __init__(self, dock: QDockWidget, extra: QWidget | None = None):
        super().__init__(dock)
        self.setObjectName("dock_header")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(COLOR_BG_SIDEBAR))
        pal.setColor(QPalette.ColorRole.Base, QColor(COLOR_BG_SIDEBAR))
        self.setPalette(pal)
        self.setFixedHeight(DOCK_HEADER_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._dock = dock
        lay = QHBoxLayout(self)
        # Vertical inset keeps the title / buttons clear of the dock chrome edge.
        lay.setContentsMargins(10, 4, 12, 4)
        lay.setSpacing(6)
        features = dock.features()
        if features & QDockWidget.DockWidgetFeature.DockWidgetClosable:
            lay.addWidget(self._button("win-close", "Close panel", dock.close), 0, Qt.AlignmentFlag.AlignVCenter)
        if features & QDockWidget.DockWidgetFeature.DockWidgetFloatable:
            self.btn_float = self._button("win-restore", "Pop out / dock panel", self._toggle_float)
            lay.addWidget(self.btn_float, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = QLabel(dock.windowTitle())
        self.title.setObjectName("dock_title_label")
        self.title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        dock.windowTitleChanged.connect(self.title.setText)
        lay.addSpacing(2)
        lay.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        if extra is not None:
            self._fit_extra(extra)
            # Player mode tabs: center in the remaining header space.
            if extra.objectName() == "dub_player_modes":
                self.title.hide()
                lay.addStretch(1)
                lay.addWidget(extra, 0, Qt.AlignmentFlag.AlignVCenter)
                lay.addStretch(1)
            else:
                lay.addSpacing(8)
                lay.addWidget(extra, 1, Qt.AlignmentFlag.AlignVCenter)
        else:
            lay.addStretch(1)

    @staticmethod
    def _fit_extra(widget: QWidget):
        """Keep header extras from stretching the shared dock title height."""
        widget.setFixedHeight(_EXTRA_H)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for child in widget.findChildren(QWidget):
            if isinstance(child, QToolButton):
                child.setFixedHeight(min(_EXTRA_H, child.height() or _EXTRA_H))
            elif isinstance(child, QPushButton):
                child.setMaximumHeight(_EXTRA_H)

    def _button(self, name: str, tip: str, slot) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("dock_header_btn")
        btn.setIcon(icon(name, size=12))
        btn.setIconSize(QSize(12, 12))
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    def _toggle_float(self):
        self._dock.setFloating(not self._dock.isFloating())


class DockWorkspace(QWidget):
    """
    Embeddable QMainWindow that hosts rearrangable / floatable dock panels.
    Uses Qt's default dock title bar and native drag / dock layout behavior.
    """
    layout_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dock_workspace")
        self._docks: dict[str, QDockWidget] = {}
        self._headers: dict[str, DockHeader] = {}
        self._default_state = None

        self.host = QMainWindow()
        self.host.setObjectName("dock_host")
        self.host.setDockNestingEnabled(True)
        self.host.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.GroupedDragging
        )
        central = QWidget()
        central.setObjectName("dock_central_placeholder")
        central.setMinimumSize(1, 1)
        self.host.setCentralWidget(central)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.host)

    def add_panel(
        self,
        key: str,
        title: str,
        widget: QWidget,
        area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea,
        *,
        closable: bool = True,
        min_width: int | None = None,
        max_width: int | None = None,
    ) -> QDockWidget:
        dock = QDockWidget(title, self.host)
        dock.setObjectName(f"dock_{key}")
        dock.setWidget(widget)
        dock.setTitleBarWidget(None)
        features = (
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        if closable:
            features |= QDockWidget.DockWidgetFeature.DockWidgetClosable
        dock.setFeatures(features)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        # Dock owns the splitter min/max. Body fills the dock so aside content
        # never leaves an empty strip when the panel is dragged wider.
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget.setMaximumWidth(_QWIDGETSIZE_MAX)
        if min_width is not None:
            dock.setMinimumWidth(int(min_width))
            # Keep any stronger content min (e.g. script panel at 420).
            widget.setMinimumWidth(max(widget.minimumWidth(), max(1, int(min_width) - 8)))
        if max_width is not None:
            dock.setMaximumWidth(int(max_width))
        dock.setProperty("dock_min_w", min_width)
        dock.setProperty("dock_max_w", max_width)

        self.host.addDockWidget(area, dock)
        self._docks[key] = dock
        # Uniform 32px dock titles (distinct from 40px shelf panel headers).
        header = DockHeader(dock)
        self._headers[key] = header
        dock.setTitleBarWidget(header)

        dock.topLevelChanged.connect(lambda floating, d=dock: self._on_toplevel(d, floating))
        dock.visibilityChanged.connect(lambda *_: self.layout_changed.emit())
        dock.dockLocationChanged.connect(lambda *_: self.layout_changed.emit())

        self._apply_chrome(dock, floating=False)
        return dock

    def _on_toplevel(self, dock: QDockWidget, floating: bool):
        self._apply_chrome(dock, floating)
        # Floated panels grow freely; docked panels keep dock min/max.
        # Body always fills the dock (no body max clamp).
        max_w = dock.property("dock_max_w")
        min_w = dock.property("dock_min_w")
        body = dock.widget()
        if body is not None:
            body.setMaximumWidth(_QWIDGETSIZE_MAX)
        if floating:
            dock.setMaximumWidth(_QWIDGETSIZE_MAX)
        else:
            if min_w is not None:
                dock.setMinimumWidth(int(min_w))
            if max_w is not None:
                dock.setMaximumWidth(int(max_w))
            else:
                dock.setMaximumWidth(_QWIDGETSIZE_MAX)
        self.layout_changed.emit()

    def _apply_chrome(self, dock: QDockWidget, floating: bool):
        chrome = "float" if floating else "docked"
        dock.setProperty("chrome", chrome)
        # Keep the custom DockHeader — never fall back to native title heights.

        style = dock.style()
        if style is not None:
            style.unpolish(dock)
            style.polish(dock)
        dock.update()

        body = dock.widget()
        if body is not None:
            body.setProperty("chrome", chrome)
            if style is not None:
                style.unpolish(body)
                style.polish(body)
            body.update()

    def set_header_widget(self, key: str, widget: QWidget):
        """Replace a panel's native title bar with one that also hosts ``widget``."""
        dock = self._docks.get(key)
        if not dock:
            return
        header = DockHeader(dock, widget)
        self._headers[key] = header
        dock.setTitleBarWidget(header)

    def dock(self, key: str) -> QDockWidget | None:
        return self._docks.get(key)

    def panel(self, key: str) -> QWidget | None:
        dock = self._docks.get(key)
        return dock.widget() if dock else None

    def set_visible(self, key: str, visible: bool):
        dock = self._docks.get(key)
        if dock:
            dock.setVisible(visible)

    def is_visible(self, key: str) -> bool:
        dock = self._docks.get(key)
        return bool(dock and dock.isVisible())

    def pop_out(self, key: str, floating: bool = True):
        dock = self._docks.get(key)
        if dock:
            dock.setFloating(floating)
            if floating:
                dock.raise_()
                dock.activateWindow()

    def split(
        self,
        first_key: str,
        second_key: str,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
    ):
        a = self._docks.get(first_key)
        b = self._docks.get(second_key)
        if a and b:
            self.host.splitDockWidget(a, b, orientation)

    def tabify(self, first_key: str, second_key: str):
        a = self._docks.get(first_key)
        b = self._docks.get(second_key)
        if a and b:
            self.host.tabifyDockWidget(a, b)

    def save_default_layout(self):
        self._default_state = self.host.saveState()

    def reset_layout(self):
        if self._default_state is not None:
            self.host.restoreState(self._default_state)
            for dock in self._docks.values():
                dock.show()
                self._apply_chrome(dock, floating=dock.isFloating())
            self.layout_changed.emit()

    def save_state(self) -> bytes:
        return bytes(self.host.saveState())

    def restore_state(self, data: bytes) -> bool:
        if not data:
            return False
        ok = self.host.restoreState(data)
        if ok:
            for dock in self._docks.values():
                self._apply_chrome(dock, floating=dock.isFloating())
            self.layout_changed.emit()
        return bool(ok)
