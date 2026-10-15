"""Premiere-style project home: New / Open / Recent before entering Studio."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QPoint, QEvent, QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from claynext.constants import (
    CUSTOM_WINDOW_CHROME,
    EDGE_CURSORS,
    FRAME_MARGIN,
    NAV_ITEMS,
)
from claynext.constants.theme_constants import COLOR_ACCENT_PURPLE, build_palette
from claynext.services.dub_project import (
    PROJECT_DIR,
    create_blank_project,
    forget_project,
    remember_project,
)
from claynext.gui.icons import image_icon
from claynext.gui.components.home_mode_toggle import MODE_GRID, MODE_LIST
from claynext.gui.components.home_rail import HomeRail
from claynext.gui.components.home_recent_panel import HomeRecentPanel
from claynext.gui.components.title_bar import CustomTitleBar
from claynext.gui.dialogs.new_project_dialog import NewProjectDialog
from claynext.gui.dialogs.project_settings_dialog import default_project_settings
from claynext.gui.styles import build_stylesheet
from claynext.utils.config import APP_NAME, APP_VERSION


class ProjectHomeWindow(QMainWindow):
    """Start screen: create, open, or continue a recent project."""

    project_chosen = Signal(str)

    def __init__(self):
        super().__init__()
        self._studio = None
        self._frame_cursor = None
        self._custom_chrome = CUSTOM_WINDOW_CHROME

        settings = QSettings("Claynext", "ClaynextStudio")
        mode = str(settings.value("home/view_mode", MODE_LIST) or MODE_LIST).lower()
        self._view_mode = MODE_GRID if mode == MODE_GRID else MODE_LIST

        if self._custom_chrome:
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowSystemMenuHint
                | Qt.WindowType.WindowMinimizeButtonHint
                | Qt.WindowType.WindowMaximizeButtonHint
                | Qt.WindowType.WindowCloseButtonHint
            )
            self.setMouseTracking(True)

        self.setWindowTitle(f"{APP_NAME} — Home")
        app_ico = image_icon("app", 64)
        if not app_ico.isNull():
            self.setWindowIcon(app_ico)

        self.resize(1120, 700)
        self.setMinimumSize(920, 580)

        app = QApplication.instance()
        if app:
            app.setPalette(build_palette(dark=True))
        self.setStyleSheet(build_stylesheet())

        self._build_ui()
        self.recent_panel.refresh()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        if self._custom_chrome:
            self.title_bar = CustomTitleBar(self)
            self.title_bar.minimize_requested.connect(self.showMinimized)
            self.title_bar.maximize_requested.connect(self._toggle_maximize)
            self.title_bar.close_requested.connect(self.close)
            self.title_bar.settings_requested.connect(self._open_settings)
            self.title_bar.set_tool_info({
                "label": "Home",
                "badge": "Projects",
                "color": COLOR_ACCENT_PURPLE,
                "icon": "folder",
            })
            self._setup_menus(self.title_bar.menu_bar)
            outer.addWidget(self.title_bar)
            self.menuBar().setVisible(False)
        else:
            self.title_bar = None
            self._setup_menus(self.menuBar())

        body = QFrame()
        body.setObjectName("home_body")
        lay = QHBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.rail = HomeRail()
        self.rail.new_requested.connect(self.create_project)
        self.rail.open_requested.connect(self.open_project_dialog)
        lay.addWidget(self.rail)

        self.recent_panel = HomeRecentPanel(self._view_mode)
        self.recent_panel.open_requested.connect(self.open_project_path)
        lay.addWidget(self.recent_panel, 1)

        outer.addWidget(body, 1)

    def _setup_menus(self, menu_bar):
        file_menu = menu_bar.addMenu("&File")
        act_new = QAction("&New Project…", self)
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self.create_project)
        file_menu.addAction(act_new)
        act_open = QAction("&Open Project…", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self.open_project_dialog)
        file_menu.addAction(act_open)
        file_menu.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = menu_bar.addMenu("&View")
        act_list = QAction("&List", self)
        act_list.triggered.connect(lambda: self.recent_panel.set_view_mode(MODE_LIST))
        view_menu.addAction(act_list)
        act_grid = QAction("&Grid", self)
        act_grid.triggered.connect(lambda: self.recent_panel.set_view_mode(MODE_GRID))
        view_menu.addAction(act_grid)

        help_menu = menu_bar.addMenu("&Help")
        act_about = QAction(f"About {APP_NAME}", self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

    def create_project(self):
        dlg = NewProjectDialog(self, defaults=default_project_settings(name="Untitled"))
        if not dlg.exec():
            return
        result = dlg.result_settings()
        name = str(result.get("name") or "Untitled").strip() or "Untitled"
        save_to = str(result.get("save_to") or PROJECT_DIR)
        try:
            path = create_blank_project(name, save_to=save_to, settings=result)
        except Exception as exc:
            QMessageBox.warning(self, "New Project", f"Could not create project.\n{exc}")
            return
        if dlg.open_after_create():
            self.open_project_path(path)
        else:
            self.recent_panel.refresh()

    def open_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(PROJECT_DIR),
            "Claynext Project (*.claynext.json);;JSON (*.json)",
        )
        if path:
            self.open_project_path(path)

    def open_project_path(self, path: str):
        dest = Path(path)
        if not dest.is_file():
            QMessageBox.warning(self, "Open Project", f"Project file not found:\n{path}")
            forget_project(path)
            self.recent_panel.refresh()
            return
        remember_project(dest)
        self._launch_studio(str(dest))

    def _launch_studio(self, project_path: str):
        from claynext.gui.main_window import ToolWindow

        if self._studio is not None:
            try:
                self._studio.close()
            except Exception:
                pass
            self._studio = None

        tool_index = NAV_ITEMS[0]["index"] if NAV_ITEMS else 0
        win = ToolWindow(
            tool_index=tool_index,
            home_window=self,
            project_path=project_path,
        )
        self._studio = win
        self.hide()
        win.show()
        win.raise_()
        win.activateWindow()
        self.project_chosen.emit(project_path)

    def show_home(self):
        """Return from studio to the project home screen."""
        self._studio = None
        self.recent_panel.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def _open_settings(self):
        from claynext.gui.dialogs.settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

    def _about(self):
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} v{APP_VERSION}</h3>"
            f"<p>AI movie dubbing & timeline editor.</p>"
            f"<p>Create or open a project to enter the studio.</p>",
        )

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        if self.title_bar:
            self.title_bar.set_maximized(self.isMaximized())

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self.title_bar:
            self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def _detect_edge(self, pos: QPoint):
        if self.isMaximized():
            return Qt.Edge(0)
        rect = self.rect()
        edge = Qt.Edge(0)
        if pos.x() < FRAME_MARGIN:
            edge |= Qt.Edge.LeftEdge
        elif pos.x() > rect.width() - FRAME_MARGIN:
            edge |= Qt.Edge.RightEdge
        if pos.y() < FRAME_MARGIN:
            edge |= Qt.Edge.TopEdge
        elif pos.y() > rect.height() - FRAME_MARGIN:
            edge |= Qt.Edge.BottomEdge
        return edge

    def mousePressEvent(self, event):
        if self._custom_chrome and event.button() == Qt.MouseButton.LeftButton:
            edge = self._detect_edge(event.pos())
            if edge:
                handle = self.windowHandle()
                if handle:
                    handle.startSystemResize(edge)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._custom_chrome:
            edge = self._detect_edge(event.pos())
            cursor = EDGE_CURSORS.get(edge)
            if cursor:
                if self._frame_cursor != cursor:
                    self._frame_cursor = cursor
                    self.setCursor(cursor)
            elif self._frame_cursor is not None:
                self._frame_cursor = None
                self.unsetCursor()
        super().mouseMoveEvent(event)
