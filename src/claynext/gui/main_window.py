"""
Claynext Studio dedicated tool window.
Custom frameless chrome with tool identity in the title/menu bar.
"""
import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QApplication, QMenuBar, QFrame
)
from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtGui import QAction, QKeySequence, QShortcut

from claynext.gui.styles import build_stylesheet
from claynext.gui.components.title_bar import CustomTitleBar
from claynext.gui.components.status_bar import CustomStatusBar
from claynext.gui.views.studio import StudioView
from claynext.gui.dialogs.settings_dialog import SettingsDialog
from claynext.utils.config import APP_NAME, APP_VERSION
from claynext.constants import (
    DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT, NAV_ITEMS,
    CUSTOM_WINDOW_CHROME, FRAME_MARGIN, EDGE_CURSORS,
)
from claynext.constants.theme_constants import build_palette
from claynext.gui.icons import icon, image_icon


class MainWindow(QMainWindow):
    """Dedicated studio window with custom chrome + in-bar menus."""

    def __init__(
        self,
        tool_index: int = 0,
        project_path: str | None = None,
        home_window=None,
        **_unused,
    ):
        super().__init__()

        self.tool_index = tool_index
        self.tool_data = NAV_ITEMS[tool_index] if 0 <= tool_index < len(NAV_ITEMS) else NAV_ITEMS[0]
        self.home_window = home_window
        self.project_path = project_path or ""
        self._returning_home = False

        self._custom_chrome = CUSTOM_WINDOW_CHROME
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
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._frame_cursor = None

        tool_title = self.tool_data["label"]
        self.setWindowTitle(f"{tool_title} — {APP_NAME}")
        app_ico = image_icon("app", 64)
        if not app_ico.isNull():
            self.setWindowIcon(app_ico)

        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        app = QApplication.instance()
        if app:
            app.setPalette(build_palette(dark=True))
        self.setStyleSheet(build_stylesheet())

        self.init_ui()
        self._setup_shortcuts()

    def return_to_home(self):
        """Close studio and show the project home window."""
        if self.home_window is None:
            self.close()
            return
        self._returning_home = True
        self._persist_tool_view()
        self._stop_tool_media()
        self.hide()
        self.home_window.show_home()
        self.close()

    def quit_app(self):
        """Exit the whole application (do not bounce back to home)."""
        self._returning_home = True
        home = self.home_window
        self.close()
        if home is not None:
            home.close()
        app = QApplication.instance()
        if app:
            app.quit()

    def closeEvent(self, event):
        self._persist_tool_view()
        self._stop_tool_media()
        home = self.home_window
        returning = self._returning_home
        event.accept()
        super().closeEvent(event)
        if home is not None and not returning:
            home.show_home()

    def _persist_tool_view(self):
        """Write dock layout / session before the tool window is hidden or closed."""
        view = getattr(self, "tool_view", None)
        if view is None:
            return
        if hasattr(view, "_layout_ready"):
            view._layout_ready = True
        saver = getattr(view, "_save_layout", None)
        if callable(saver):
            saver()
        store = getattr(view, "_store_project_session", None)
        if callable(store):
            store()

    def _stop_tool_media(self):
        view = getattr(self, "tool_view", None)
        stopper = getattr(view, "stop_playback", None)
        if callable(stopper):
            stopper()
            return
        preview = getattr(view, "preview", None)
        if preview is not None and hasattr(preview, "stop_playback"):
            preview.stop_playback()

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("root")
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Custom title bar hosts menus + tool identity (no separate header)
        if self._custom_chrome:
            self.title_bar = CustomTitleBar(self)
            self.title_bar.minimize_requested.connect(self.showMinimized)
            self.title_bar.maximize_requested.connect(self.toggle_maximize)
            self.title_bar.close_requested.connect(self.close)
            self.title_bar.settings_requested.connect(self.open_settings_dialog)
            self.title_bar.set_tool_info(self.tool_data)
            self.setup_menus(self.title_bar.menu_bar)
            root_layout.addWidget(self.title_bar)
            self.menuBar().setVisible(False)
        else:
            self.title_bar = None
            self.setup_menus(self.menuBar())
            self.menuBar().setVisible(True)

        # Tool workspace fills the window
        workspace = QFrame()
        workspace.setObjectName("tool_workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        self.tool_view = self._create_tool_view(self.tool_index)
        workspace_layout.addWidget(self.tool_view, 1)
        root_layout.addWidget(workspace, 1)

        menu_bar = self.title_bar.menu_bar if self.title_bar else self.menuBar()
        installer = getattr(self.tool_view, "install_window_menus", None)
        if callable(installer):
            installer(menu_bar)
        self._ensure_studio_tools_menu(menu_bar)

        self.status_bar = CustomStatusBar(self)
        self.status_bar.set_active_tool_name(self.tool_data["label"])
        self.status_bar.set_status_message(f"Ready — {self.tool_data['label']}")
        root_layout.addWidget(self.status_bar)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(self.open_settings_dialog)

    def _create_tool_view(self, index: int) -> QWidget:
        return StudioView(startup_project_path=self.project_path or "")

    def setup_menus(self, menu_bar: QMenuBar):
        file_menu = menu_bar.addMenu("&File")

        if self.home_window is not None:
            act_home = QAction("&Close Project", self)
            act_home.setShortcut(QKeySequence("Ctrl+0"))
            act_home.triggered.connect(self.return_to_home)
            file_menu.addAction(act_home)
            file_menu.addSeparator()

        act_settings = QAction("&Settings…", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        # Keep in-app menus (custom chrome); avoid OS Application menu roles
        act_settings.setMenuRole(QAction.MenuRole.NoRole)
        act_settings.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(act_settings)
        file_menu.addSeparator()

        act_close_tool = QAction("&Close Window", self)
        act_close_tool.setShortcut(QKeySequence("Ctrl+W"))
        act_close_tool.setMenuRole(QAction.MenuRole.NoRole)
        act_close_tool.triggered.connect(self.close)
        file_menu.addAction(act_close_tool)

        act_exit = QAction("&Quit Claynext Studio" if sys.platform != "win32" else "E&xit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.setMenuRole(QAction.MenuRole.NoRole)
        act_exit.triggered.connect(self.quit_app)
        file_menu.addAction(act_exit)

        edit_menu = menu_bar.addMenu("&Edit")
        for text, key in (("&Undo", "Ctrl+Z"), ("&Redo", "Ctrl+Y")):
            act = QAction(text, self)
            act.setShortcut(QKeySequence(key))
            edit_menu.addAction(act)
        edit_menu.addSeparator()
        act_copy = QAction("&Copy", self)
        act_copy.setShortcut(QKeySequence("Ctrl+C"))
        edit_menu.addAction(act_copy)
        act_select = QAction("Select &All", self)
        act_select.setShortcut(QKeySequence("Ctrl+A"))
        edit_menu.addAction(act_select)

        view_menu = menu_bar.addMenu("&View")
        act_fullscreen = QAction("Toggle &Full Screen", self)
        act_fullscreen.setShortcut(QKeySequence("F11"))
        act_fullscreen.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(act_fullscreen)

        # Tools = studio utilities for the active workspace (filled by the tool view).
        self._tools_menu = menu_bar.addMenu("&Tools")
        placeholder = QAction(f"{self.tool_data['label']} studio tools", self)
        placeholder.setEnabled(False)
        self._tools_menu.addAction(placeholder)

        help_menu = menu_bar.addMenu("&Help")
        act_docs = QAction("&Documentation", self)
        act_docs.setShortcut(QKeySequence("F1"))
        act_docs.setMenuRole(QAction.MenuRole.NoRole)
        act_docs.triggered.connect(self.open_documentation)
        help_menu.addAction(act_docs)

        help_menu.addSeparator()
        act_show_log = QAction("Show &Activity Log", self)
        act_show_log.setShortcut(QKeySequence("Ctrl+Shift+G"))
        act_show_log.setMenuRole(QAction.MenuRole.NoRole)
        act_show_log.triggered.connect(self.show_activity_log)
        help_menu.addAction(act_show_log)

        act_open_log = QAction("Open &Log File…", self)
        act_open_log.setMenuRole(QAction.MenuRole.NoRole)
        act_open_log.triggered.connect(self.open_log_file)
        help_menu.addAction(act_open_log)

        act_logs_folder = QAction("Open Logs &Folder", self)
        act_logs_folder.setMenuRole(QAction.MenuRole.NoRole)
        act_logs_folder.triggered.connect(self.open_logs_folder)
        help_menu.addAction(act_logs_folder)

        help_menu.addSeparator()
        act_about = QAction(f"&About {APP_NAME}", self)
        act_about.setMenuRole(QAction.MenuRole.NoRole)
        act_about.triggered.connect(self.open_about_dialog)
        help_menu.addAction(act_about)

    def _ensure_studio_tools_menu(self, menu_bar: QMenuBar):
        """Fill Tools with studio actions when the active view did not populate it."""
        tools_menu = getattr(self, "_tools_menu", None)
        if tools_menu is None:
            for action in menu_bar.actions():
                menu = action.menu()
                if menu and menu.title().replace("&", "").lower() == "tools":
                    tools_menu = menu
                    break
        if tools_menu is None:
            return
        # View already replaced the placeholder with real actions.
        if tools_menu.actions() and any(a.isEnabled() for a in tools_menu.actions()):
            return
        tools_menu.clear()
        label = self.tool_data.get("label", "Studio")
        hdr = QAction(f"{label} tools", self)
        hdr.setEnabled(False)
        tools_menu.addAction(hdr)
        tools_menu.addSeparator()
        act_features = QAction("Feature &settings…", self)
        act_features.triggered.connect(lambda: self.open_settings_dialog("Features"))
        tools_menu.addAction(act_features)
        act_settings = QAction("&Settings…", self)
        act_settings.triggered.connect(self.open_settings_dialog)
        tools_menu.addAction(act_settings)

    def open_documentation(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl("https://github.com/vannyakh/claynext"))

    def show_activity_log(self):
        """Reveal the Activity Log dock for on-screen issue tracking."""
        view = getattr(self, "tool_view", None)
        workspace = getattr(view, "workspace", None)
        if workspace is not None and hasattr(workspace, "set_visible"):
            workspace.set_visible("log", True)
            actions = getattr(view, "_panel_actions", None) or {}
            act = actions.get("log")
            if act is not None:
                act.blockSignals(True)
                act.setChecked(True)
                act.blockSignals(False)
            return
        self.open_log_file()

    def open_log_file(self):
        """Open today's session log in the system editor (for bug reports)."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from claynext.utils.logging import configure_logging, session_log_path

        configure_logging()
        path = session_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            path.write_text(
                f"# Claynext session log\n# Created {path.name}\n",
                encoding="utf-8",
            )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def open_logs_folder(self):
        """Open data/logs in Explorer / Finder."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from claynext.utils.paths import LOGS_DIR, ensure_data_dirs

        ensure_data_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOGS_DIR.resolve())))

    def open_about_dialog(self):
        from PySide6.QtWidgets import QMessageBox

        from claynext.utils.logging import session_log_path

        log_hint = ""
        try:
            log_hint = f"<p>Session log: <code>{session_log_path()}</code></p>"
        except Exception:
            pass
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} v{APP_VERSION}</h3>"
            f"<p><b>Tool:</b> {self.tool_data['label']}</p>"
            f"<p>{self.tool_data.get('long_desc', self.tool_data.get('desc', ''))}</p>"
            f"<p>Running on <b>{sys.platform.capitalize()}</b> with PySide6.</p>"
            f"{log_hint}"
        )

    def open_settings_dialog(self, tab: str | None = None):
        dialog = SettingsDialog(self)
        if tab:
            for i in range(dialog.tabs.count()):
                if dialog.tabs.tabText(i).replace("&", "").lower() == tab.lower():
                    dialog.tabs.setCurrentIndex(i)
                    break
        dialog.exec()

    def open_api_keys_dialog(self):
        self.open_settings_dialog("API Keys")

    def toggle_maximize(self):
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

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

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


ToolWindow = MainWindow
ToolsWindow = MainWindow

