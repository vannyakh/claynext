"""Studio media browser."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QToolButton,
    QMenu,
    QStackedWidget,
    QAbstractItemView,
    QButtonGroup,
    QSizePolicy,
    QLineEdit,
    QPushButton,
)
from PySide6.QtCore import (
    Qt,
    Signal,
    QSize,
    QThreadPool,
)
from PySide6.QtGui import QIcon, QAction, QActionGroup

from claynext.constants.theme_constants import COLOR_PRIMARY
from claynext.gui.icons import icon
from claynext.models.thumbnails import VIDEO_EXTS, IMAGE_EXTS

from claynext.gui.components.media_library.files import LibraryFiles
from claynext.gui.components.media_library.footer import _MediaDetailFooter
from claynext.gui.components.media_library.jobs import _DurSignals, _ThumbSignals
from claynext.gui.components.media_library.list_view import _MediaList
from claynext.gui.components.media_library.select import LibrarySelect
from claynext.gui.components.media_library.table_view import _MediaTable

class MediaLibraryWidget(LibraryFiles, LibrarySelect, QWidget):
    """
    Modern studio media browser with video thumbnails, filter pills,
    command card footer, and Drag-and-Drop to timeline.
    """
    file_selected = Signal(str)
    selection_cleared = Signal()
    files_changed = Signal(int)
    status_message = Signal(str)
    localize_requested = Signal()

    AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
    IMAGE_EXTS = IMAGE_EXTS
    MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media_library")
        self.setAcceptDrops(True)
        self._paths: list[str] = []
        self._had_selection = False
        self._view_mode = "list"
        self._filter = "all"  # all | video | audio | image
        self._query = ""
        self._thumb_pool = QThreadPool.globalInstance()
        self._thumb_signals = _ThumbSignals()
        self._thumb_signals.ready.connect(self._on_thumb_ready)
        self._thumb_cache: dict[str, QIcon] = {}
        self._dur_signals = _DurSignals()
        self._dur_signals.ready.connect(self._on_duration_ready)
        self._dur_cache: dict[str, float] = {}
        self._meta_cache: dict[str, dict] = {}
        self._syncing_checks = False
        self.init_ui()

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(6)

        tools = QWidget()
        tools.setObjectName("media_lib_tools")
        tools_lay = QVBoxLayout(tools)
        tools_lay.setContentsMargins(0, 0, 0, 2)
        tools_lay.setSpacing(4)

        # ─── Row 1: Add Media, Search, Views, Actions ────────────────────
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)

        self.btn_add = QPushButton("+ Add Media")
        self.btn_add.setObjectName("media_lib_add_btn")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setFixedHeight(22)
        self.btn_add.setToolTip("Import video, audio, or images into the library")
        self.btn_add.clicked.connect(self.browse_add)
        row1.addWidget(self.btn_add, 0, Qt.AlignmentFlag.AlignVCenter)

        self.search = QLineEdit()
        self.search.setObjectName("media_lib_search")
        self.search.setPlaceholderText("Search media…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(120)
        self.search.setFixedHeight(22)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search.textChanged.connect(self._on_search)
        row1.addWidget(self.search, 1, Qt.AlignmentFlag.AlignVCenter)

        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.btn_list = self._icon_toggle("list", "List view")
        self.btn_grid = self._icon_toggle("grid", "Grid view")
        self.btn_list.setChecked(True)
        self.view_group.addButton(self.btn_list, 0)
        self.view_group.addButton(self.btn_grid, 1)
        self.view_group.idClicked.connect(self._on_view_id)
        row1.addWidget(self.btn_list, 0, Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(self.btn_grid, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_more = QToolButton()
        self.btn_more.setObjectName("media_lib_icon_btn")
        self.btn_more.setIcon(icon("more", color="#94a3b8", size=12))
        self.btn_more.setFixedSize(22, 22)
        self.btn_more.setToolTip("Library options")
        self.btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_more.setMenu(self._build_actions_menu())
        row1.addWidget(self.btn_more, 0, Qt.AlignmentFlag.AlignVCenter)

        self._header_actions = QHBoxLayout()
        self._header_actions.setContentsMargins(0, 0, 0, 0)
        self._header_actions.setSpacing(6)
        row1.addLayout(self._header_actions, 0)

        tools_lay.addLayout(row1)

        # ─── Row 2: Filter Pills + Summary Count Badge ───────────────────
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(4)

        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self._filter_buttons: dict[str, QPushButton] = {}
        for key, label in (("all", "All"), ("video", "Video"), ("audio", "Audio"), ("image", "Images")):
            btn = QPushButton(label)
            btn.setObjectName("media_lib_filter_chip")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(18)
            if key == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, k=key: self._set_filter(k))
            self.filter_group.addButton(btn)
            self._filter_buttons[key] = btn
            row2.addWidget(btn)

        row2.addStretch(1)
        tools_lay.addLayout(row2)

        self.filter_combo = None
        self._filter_actions: dict[str, QAction] = {}

        root.addWidget(tools)

        # ─── Main Stack: Empty, List, Grid ──────────────────────────────
        self.stack = QStackedWidget()

        empty = QWidget()
        empty.setObjectName("media_lib_empty_wrap")
        empty_lay = QVBoxLayout(empty)
        empty_lay.setContentsMargins(16, 20, 16, 20)
        empty_lay.setSpacing(8)
        empty_lay.addStretch(1)
        self.empty = QLabel("Drop video, audio, or images")
        self.empty.setObjectName("media_lib_empty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        empty_lay.addWidget(self.empty)
        self.empty_add = QPushButton("Browse files")
        self.empty_add.setObjectName("media_lib_browse_btn")
        self.empty_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.empty_add.setFixedHeight(24)
        self.empty_add.clicked.connect(self.browse_add)
        empty_lay.addWidget(self.empty_add, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_hint = QLabel("or drag a folder of clips")
        empty_hint.setObjectName("media_lib_empty_hint")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lay.addWidget(empty_hint)
        empty_lay.addStretch(2)
        self.empty_page = empty

        self.list_view = _MediaTable()
        self.list_view.itemSelectionChanged.connect(self._on_selection)
        self.list_view.cellDoubleClicked.connect(self._on_table_activate)
        self.list_view.header_check.clicked.connect(self._on_header_check)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)

        self.grid_view = _MediaList()
        self.grid_view.setObjectName("media_lib_grid")
        self.grid_view.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid_view.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid_view.setMovement(QListWidget.Movement.Static)
        self.grid_view.setIconSize(QSize(96, 72))
        self.grid_view.setGridSize(QSize(120, 118))
        self.grid_view.setWordWrap(True)
        self.grid_view.setSpacing(8)
        self.grid_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid_view.itemSelectionChanged.connect(self._on_selection)
        self.grid_view.itemDoubleClicked.connect(self._on_activate)
        self.grid_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid_view.customContextMenuRequested.connect(self._show_context_menu)

        self.stack.addWidget(self.empty_page)
        self.stack.addWidget(self.list_view)
        self.stack.addWidget(self.grid_view)
        root.addWidget(self.stack, 1)

        # ─── Selected Media Details & Command Footer ─────────────────────
        self.footer = _MediaDetailFooter(self)
        self.footer.preview_requested.connect(self._on_footer_preview)
        self.footer.localize_requested.connect(self.localize_requested.emit)
        self.footer.reveal_requested.connect(self.reveal_selected)
        self.footer.remove_requested.connect(self.remove_selected)
        self.footer.browse_requested.connect(self.browse_add)
        self.footer.clear_selection_requested.connect(self.clear_selection)
        self.footer.hide()
        root.addWidget(self.footer, 0)

        self._update_count()
        self._apply_view_mode()

    def set_header_actions(self, *widgets: QWidget):
        """Place action controls on the right of the tools row (search/view stay left)."""
        while self._header_actions.count():
            item = self._header_actions.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        for widget in widgets:
            if widget is None:
                continue
            self._header_actions.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def _icon_toggle(self, name: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("media_lib_icon_btn")
        btn.setCheckable(True)
        btn.setAutoRaise(True)
        btn.setIcon(icon(name, color="#94a3b8", size=12))
        btn.setFixedSize(22, 22)
        btn.setIconSize(QSize(12, 12))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return btn

    def _build_actions_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("media_lib_menu")

        menu.addAction("Add Files…", self.browse_add)
        menu.addAction("Deselect", self.clear_selection)
        menu.addAction("Reveal in Finder", self.reveal_selected)
        menu.addSeparator()

        filter_menu = menu.addMenu("Show")
        filter_menu.setObjectName("media_lib_menu")
        self._filter_actions = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        for key, label in (("all", "All media"), ("video", "Video only"), ("audio", "Audio only"), ("image", "Images")):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(key == self._filter)
            act.setData(key)
            act.triggered.connect(lambda checked=False, k=key: self._set_filter(k))
            group.addAction(act)
            filter_menu.addAction(act)
            self._filter_actions[key] = act

        menu.addSeparator()
        menu.addAction("Remove Selected", self.remove_selected)
        menu.addAction("Clear All", self.clear_all)
        return menu

    def _set_filter(self, key: str):
        self._filter = key if key in ("all", "video", "audio", "image") else "all"
        for k, act in self._filter_actions.items():
            act.blockSignals(True)
            act.setChecked(k == self._filter)
            act.blockSignals(False)
        for k, btn in self._filter_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(k == self._filter)
            btn.blockSignals(False)
        self._refresh_items()
        self._apply_view_mode()
        self._update_count()

    def _on_search(self, text: str):
        self._query = (text or "").strip().lower()
        self._refresh_items()
        self._apply_view_mode()
        self._update_count()

    def _on_filter(self, _index: int = 0):
        self._set_filter(self._filter)

    def _visible_paths(self) -> list[str]:
        paths = self._paths
        if self._filter == "video":
            paths = [p for p in paths if os.path.splitext(p)[1].lower() in VIDEO_EXTS]
        elif self._filter == "audio":
            paths = [p for p in paths if os.path.splitext(p)[1].lower() in self.AUDIO_EXTS]
        elif self._filter == "image":
            paths = [p for p in paths if os.path.splitext(p)[1].lower() in IMAGE_EXTS]
        if self._query:
            paths = [p for p in paths if self._query in os.path.basename(p).lower()]
        return paths

    def _update_count(self):
        n_total = len(self._paths)
        n_video = sum(1 for p in self._paths if os.path.splitext(p)[1].lower() in VIDEO_EXTS)
        n_audio = sum(1 for p in self._paths if os.path.splitext(p)[1].lower() in self.AUDIO_EXTS)
        n_image = sum(1 for p in self._paths if os.path.splitext(p)[1].lower() in IMAGE_EXTS)

        counts = {"all": n_total, "video": n_video, "audio": n_audio, "image": n_image}
        labels = {"all": "All", "video": "Video", "audio": "Audio", "image": "Images"}
        for key, btn in self._filter_buttons.items():
            btn.blockSignals(True)
            btn.setText(f"{labels.get(key, key)} ({counts.get(key, 0)})")
            btn.setChecked(key == self._filter)
            btn.blockSignals(False)

        self._update_detail_footer()

    def _update_detail_footer(self):
        if hasattr(self, "footer") and self.footer is not None:
            self.footer.update_state(
                selected_paths=self.selected_paths(),
                total_paths=self._paths,
                meta_cache=self._meta_cache,
                thumb_cache=self._thumb_cache,
                dur_cache=self._dur_cache,
                fallback_icon_fn=self._fallback_icon,
                format_dur_fn=self._format_duration,
                size_label_fn=self._size_label,
            )

    def _show_context_menu(self, pos):
        menu = self._build_actions_menu()
        view = self._active_view()
        menu.exec(view.mapToGlobal(pos))

    def _on_view_id(self, btn_id: int):
        self.set_view_mode("grid" if btn_id == 1 else "list")

    def set_view_mode(self, mode: str):
        self._view_mode = "grid" if mode == "grid" else "list"
        self.btn_list.blockSignals(True)
        self.btn_grid.blockSignals(True)
        self.btn_list.setChecked(self._view_mode == "list")
        self.btn_grid.setChecked(self._view_mode == "grid")
        self.btn_list.blockSignals(False)
        self.btn_grid.blockSignals(False)

        list_color = COLOR_PRIMARY if self._view_mode == "list" else "#94a3b8"
        grid_color = COLOR_PRIMARY if self._view_mode == "grid" else "#94a3b8"
        self.btn_list.setIcon(icon("list", color=list_color, size=14))
        self.btn_grid.setIcon(icon("grid", color=grid_color, size=14))

        self._refresh_items()
        self._apply_view_mode()

    def _apply_view_mode(self):
        if not self._visible_paths():
            if self._paths:
                self.empty.setText("No matches for this filter")
            else:
                self.empty.setText("Drop video, audio, or images")
            self.stack.setCurrentWidget(self.empty_page)
            return
        self.stack.setCurrentWidget(
            self.grid_view if self._view_mode == "grid" else self.list_view
        )
