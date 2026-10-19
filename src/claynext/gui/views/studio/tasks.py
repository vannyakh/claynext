"""Dub task list: queued, running, and finished jobs that open the timeline."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QObject, QEvent, QSize, QThreadPool, QTimer, Signal, QRect, QRectF, QModelIndex, QUrl
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QIcon, QKeySequence, QPainter, QPainterPath,
    QFont, QPen, QBrush, QPixmap, QDesktopServices, QDragEnterEvent,
    QDragMoveEvent, QDropEvent, QKeyEvent, QConicalGradient,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QCheckBox,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QFileDialog, QApplication,
)

from claynext.constants.theme_constants import (
    COLOR_ACCENT_CYAN, COLOR_ACCENT_EMERALD, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
    COLOR_TEXT_MAIN, COLOR_PRIMARY, COLOR_BORDER, COLOR_BG_CARD, COLOR_BG_SIDEBAR,
)
from claynext.gui.icons import icon
from claynext.models.thumbnails import VIDEO_EXTS, IMAGE_EXTS, icon_for, pixmap_for, thumb_path_for
from claynext.gui.worker import Worker

from claynext.gui.components.shell.shelf_header import make_shelf_button, make_shelf_header
from claynext.gui.components.controls.spinner import Spinner

_PAUSED_COLOR = "#f59e0b"
_STATUS_COLORS = {
    "queued": COLOR_TEXT_MUTED,
    "running": COLOR_ACCENT_CYAN,
    "paused": _PAUSED_COLOR,
    "done": COLOR_ACCENT_EMERALD,
    "failed": "#f87171",
    "cancelled": COLOR_TEXT_MUTED,
}
# Internal pipeline stages (progress mapping only — not shown as table columns).
STAGES = (
    ("AUD", "Audio · Demux and separate the movie audio", 0, 16),
    ("ASR", "ASR · Transcribe the dialogue", 16, 38),
    ("TR", "Translation · Translate the script", 38, 58),
    ("TTS", "TTS · Synthesize and fit the voice lines", 58, 82),
    ("MIX", "Mix · Voice track, music bed and mastering", 82, 100),
)
_CHECK_COL = 0
_INDEX_COL = 1
_NAME_COL = 2
_STATUS_COL = 3
_COL_COUNT = 4
_STATUS_LABELS = {
    "queued": "Queued",
    "running": "Dubbing",
    "paused": "Paused",
    "done": "Ready",
    "failed": "Failed",
    "cancelled": "Stopped",
}
_FILTERS = (
    ("all", "All"),
    ("done", "Ready"),
    ("queued", "Queued"),
    ("active", "Running"),
    ("failed", "Failed"),
)
_ACTIVE = {"running", "paused"}
_FAILED = {"failed", "cancelled"}
_THUMB_SIZE = 32
_ROW_H = 50
_CHECK_W = 22
_INDEX_W = 18
_STATUS_W = 108
# Extra roles on STATUS column items
_ROLE_PROGRESS = Qt.ItemDataRole.UserRole + 1
_ROLE_STAGE = Qt.ItemDataRole.UserRole + 2


class LiveBridge(QObject):
    """Carries live job events from the worker thread to the GUI thread."""

    event = Signal(str, object)

    def send(self, kind: str, payload):
        self.event.emit(kind, payload)


class _ClickOut(QObject):
    def __init__(self, table: QTableWidget, callback):
        super().__init__(table)
        self._table = table
        self._callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and not self._table.indexAt(event.position().toPoint()).isValid():
            self._callback()
        return False


class TaskNameDelegate(QStyledItemDelegate):
    """Paints a 2-line media cell: image thumbnail (or small placeholder icon fallback) + bold title + metadata subtitle."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        opt.state &= ~QStyle.StateFlag.State_KeyboardFocusChange
        rect = opt.rect

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setClipRect(rect)

        is_sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        if is_sel:
            painter.fillRect(rect, QColor(99, 102, 241, 40))
            painter.fillRect(QRect(rect.x(), rect.y(), 2, rect.height()), QColor(COLOR_PRIMARY))
        elif opt.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor(255, 255, 255, 8))

        # Thumbnail box: 34w x 26h with 5px radius (4:3 video ratio)
        thumb_w = 34
        thumb_h = 26
        ix = rect.x() + 4
        iy = rect.y() + (rect.height() - thumb_h) // 2
        thumb_rect = QRectF(ix, iy, thumb_w, thumb_h)
        radius = 5.0

        pix = index.data(Qt.ItemDataRole.UserRole + 4)
        if isinstance(pix, QPixmap) and not pix.isNull():
            # Real image thumbnail
            clip_path = QPainterPath()
            clip_path.addRoundedRect(thumb_rect, radius, radius)
            painter.save()
            painter.setClipPath(clip_path)

            scaled = pix.scaled(
                thumb_rect.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            sx = int(thumb_rect.x() + (thumb_rect.width() - scaled.width()) / 2)
            sy = int(thumb_rect.y() + (thumb_rect.height() - scaled.height()) / 2)
            painter.drawPixmap(sx, sy, scaled)

            # Subtle vignette at bottom
            painter.fillRect(
                QRectF(thumb_rect.x(), thumb_rect.bottom() - 6, thumb_rect.width(), 6),
                QColor(0, 0, 0, 50),
            )
            painter.restore()

            # Rounded border overlay
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(35, 51, 72, 200), 1))
            painter.drawRoundedRect(thumb_rect, radius, radius)
        else:
            # Fallback placeholder card: dark box + small centered placeholder icon
            painter.setPen(QPen(QColor(35, 51, 72), 1))
            painter.setBrush(QColor(18, 26, 38))
            painter.drawRoundedRect(thumb_rect, radius, radius)

            ico = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(ico, QIcon) and not ico.isNull():
                icon_size = 14
                icon_rect = QRect(
                    int(thumb_rect.center().x() - icon_size / 2),
                    int(thumb_rect.center().y() - icon_size / 2),
                    icon_size,
                    icon_size,
                )
                ico.paint(painter, icon_rect)

        # Text area
        tx = ix + thumb_w + 8
        tw = rect.right() - tx - 4
        if tw > 15:
            title = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            subtitle = str(index.data(Qt.ItemDataRole.UserRole + 3) or "")

            # Line 1: Title (ElideRight shows the actual beginning of the file name)
            f_title = QFont(painter.font())
            f_title.setPixelSize(12)
            f_title.setWeight(QFont.Weight.DemiBold)
            painter.setFont(f_title)
            painter.setPen(QColor("#ffffff" if is_sel else COLOR_TEXT_MAIN))
            fm = painter.fontMetrics()
            elided_title = fm.elidedText(title, Qt.TextElideMode.ElideRight, tw)
            painter.drawText(tx, rect.y() + 20, elided_title)

            # Line 2: Subtitle
            if tw > 30:
                f_sub = QFont(painter.font())
                f_sub.setPixelSize(10)
                f_sub.setWeight(QFont.Weight.Normal)
                painter.setFont(f_sub)
                painter.setPen(QColor("#a5b4fc" if is_sel else COLOR_TEXT_MUTED))
                fm_sub = painter.fontMetrics()
                elided_sub = fm_sub.elidedText(subtitle, Qt.TextElideMode.ElideRight, tw)
                painter.drawText(tx, rect.y() + 35, elided_sub)

        painter.restore()



class StatusBadgeDelegate(QStyledItemDelegate):
    """Status capsule — active rows also show a spinner + progress bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._angle = (self._angle + 14) % 360
        view = self.parent()
        if view is not None:
            view.viewport().update()

    def set_animating(self, on: bool):
        if on:
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        opt.state &= ~QStyle.StateFlag.State_KeyboardFocusChange
        rect = opt.rect

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(rect)

        if opt.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor(99, 102, 241, 40))
        elif opt.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor(255, 255, 255, 8))

        status = index.data(Qt.ItemDataRole.UserRole) or "done"
        try:
            progress = int(index.data(_ROLE_PROGRESS) or 0)
        except (TypeError, ValueError):
            progress = 0
        progress = max(0, min(100, progress))
        active = status in _ACTIVE

        styles = {
            "done": (QColor(16, 185, 129, 25), QColor(16, 185, 129, 75), "#10b981", "Ready"),
            "running": (QColor(6, 182, 212, 30), QColor(6, 182, 212, 120), "#06b6d4", "Dubbing"),
            "paused": (QColor(245, 158, 11, 25), QColor(245, 158, 11, 100), "#f59e0b", "Paused"),
            "failed": (QColor(248, 113, 113, 25), QColor(248, 113, 113, 100), "#f87171", "Failed"),
            "cancelled": (QColor(107, 119, 133, 20), QColor(107, 119, 133, 60), "#94a3b8", "Stopped"),
            "queued": (QColor(107, 119, 133, 20), QColor(107, 119, 133, 60), "#94a3b8", "Queued"),
        }
        bg, border, text_col, text_label = styles.get(status, styles["queued"])

        if active:
            # Layout: [spinner] [pill %] stacked over a thin progress track
            spin = 14
            gap = 5
            bw, bh = 44, 18
            total_w = spin + gap + bw
            left = rect.x() + (rect.width() - total_w) // 2
            cy = rect.y() + rect.height() // 2 - 2

            # Spinner
            sx = left
            sy = cy - spin // 2
            spin_rect = QRectF(sx + 1.5, sy + 1.5, spin - 3, spin - 3)
            accent = QColor("#f59e0b" if status == "paused" else "#06b6d4")
            grad = QConicalGradient(spin_rect.center(), -self._angle)
            grad.setColorAt(0.0, accent)
            grad.setColorAt(0.75, QColor(accent.red(), accent.green(), accent.blue(), 0))
            pen = QPen(QBrush(grad), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(spin_rect, 0, 360 * 16)

            # Percent / status pill
            pill_rect = QRectF(left + spin + gap, cy - bh / 2, bw, bh)
            painter.setBrush(bg)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(pill_rect, 9, 9)
            f = painter.font()
            f.setPixelSize(9)
            f.setWeight(QFont.Weight.DemiBold)
            painter.setFont(f)
            painter.setPen(QColor(text_col))
            label = f"{progress}%" if status == "running" else text_label
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, label)

            # Progress track under the controls
            bar_w = total_w
            bar_h = 3
            bar_x = left
            bar_y = cy + bh / 2 + 4
            track = QRectF(bar_x, bar_y, bar_w, bar_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.drawRoundedRect(track, 1.5, 1.5)
            fill_w = bar_w * (progress / 100.0)
            if fill_w > 0.5:
                fill = QRectF(bar_x, bar_y, fill_w, bar_h)
                painter.setBrush(accent)
                painter.drawRoundedRect(fill, 1.5, 1.5)
        else:
            bw, bh = 50, 20
            bx = rect.x() + (rect.width() - bw) // 2
            by = rect.y() + (rect.height() - bh) // 2
            pill_rect = QRectF(bx, by, bw, bh)

            painter.setBrush(bg)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(pill_rect, 10, 10)

            f = painter.font()
            f.setPixelSize(9)
            f.setWeight(QFont.Weight.DemiBold)
            painter.setFont(f)
            painter.setPen(QColor(text_col))
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, text_label)

        painter.restore()



class TaskTableWidget(QTableWidget):
    """QTableWidget with drag-and-drop media queuing and custom keyboard navigation."""

    files_dropped = Signal(list)
    delete_pressed = Signal()
    open_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        expanded = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        fp = os.path.join(root, f)
                        if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                            expanded.append(fp)
            elif os.path.splitext(p)[1].lower() in VIDEO_EXTS:
                expanded.append(p)
        if expanded:
            self.files_dropped.emit(expanded)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_pressed.emit()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.open_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class TaskTools:
    """Shelf tab listing dub jobs; selecting a job shows it live or opens its timeline."""

    def _build_tasks_panel(self) -> QWidget:
        self._tasks: list[dict] = []
        self._task_seq = 0
        self._active_task = -1
        self._timeline_open = True
        self._task_selected_id = -1
        self._viewing_task = -1
        self._live_return_index = -1
        self._task_filter = "all"
        self._task_checked: set[int] = set()
        self._task_cells: dict[int, dict] = {}
        self._task_thumbs: dict[str, QPixmap] = {}
        self._thumb_pending: set[str] = set()

        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(280)
        self._live_timer.timeout.connect(self._render_live_task)
        self._live_paint_keys = None
        self._live_scroll_row = None

        panel = QWidget()
        panel.setObjectName("dub_tasks_panel")
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Quick Add button (compact 24x24 icon button)
        self.btn_add_task = make_shelf_button(
            tip="Queue video files to dub…", icon_name="plus",
        )
        self.btn_add_task.setProperty("role", "add")
        self.btn_add_task.clicked.connect(self._choose_and_queue_files)

        # Status filter pill
        self.btn_task_filter = make_shelf_button(
            "All", tip="Filter tasks by status", icon_name="filter", menu=True,
        )
        self.btn_task_filter.setProperty("role", "filter")
        self._task_filter_menu = QMenu(self.btn_task_filter)
        self._task_filter_menu.setObjectName("media_lib_menu")
        self._task_filter_group = QActionGroup(self._task_filter_menu)
        self._task_filter_group.setExclusive(True)
        for key, label in _FILTERS:
            act = QAction(label, self._task_filter_menu)
            act.setCheckable(True)
            act.setData(key)
            act.setChecked(key == "all")
            self._task_filter_group.addAction(act)
            self._task_filter_menu.addAction(act)
        self._task_filter_group.triggered.connect(self._on_task_filter)
        self.btn_task_filter.setMenu(self._task_filter_menu)

        # Dynamic Delete button (shown when items checked, compact 24x24 icon button)
        self.btn_delete_tasks = make_shelf_button(
            tip="Remove checked tasks (Del)", icon_name="trash",
        )
        self.btn_delete_tasks.setProperty("role", "danger")
        self.btn_delete_tasks.setVisible(False)
        self.btn_delete_tasks.clicked.connect(self._delete_checked_tasks)

        # Export button (download icon + text)
        self.btn_export_tasks = make_shelf_button(
            "Export", tip="Export checked ready tasks — opens export settings", icon_name="download",
        )
        self.btn_export_tasks.setProperty("role", "primary")
        self.btn_export_tasks.setEnabled(False)
        self.btn_export_tasks.clicked.connect(self._export_checked_tasks)

        # More tools menu (compact 24x24 icon button)
        self.btn_task_menu = make_shelf_button(
            tip="More task actions", icon_name="more", menu=True,
        )

        self._task_tools_menu = QMenu(self.btn_task_menu)
        self._task_tools_menu.setObjectName("media_lib_menu")
        act_add = self._task_tools_menu.addAction(icon("plus", size=14), "Add video files…")
        act_add.setShortcut(QKeySequence.StandardKey.Open)
        act_add.triggered.connect(self._choose_and_queue_files)
        self._task_tools_menu.addSeparator()
        act_sel_all = self._task_tools_menu.addAction("Select all visible")
        act_sel_all.triggered.connect(lambda: self._select_all_tasks(True))
        act_sel_ready = self._task_tools_menu.addAction("Select ready tasks")
        act_sel_ready.triggered.connect(self._select_ready_tasks)
        act_clear_sel = self._task_tools_menu.addAction("Clear selection")
        act_clear_sel.triggered.connect(lambda: self._select_all_tasks(False))
        self._task_tools_menu.addSeparator()
        act_clear_done = self._task_tools_menu.addAction(icon("trash", size=14), "Clear finished tasks")
        act_clear_done.triggered.connect(self._clear_finished_tasks)
        self.btn_task_menu.setMenu(self._task_tools_menu)

        self._sync_task_filter_caption()

        root.addWidget(
            make_shelf_header(
                "Tasks",
                self.btn_add_task,
                self.btn_task_filter,
                self.btn_delete_tasks,
                self.btn_export_tasks,
                self.btn_task_menu,
            )
        )

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(10, 8, 10, 8)
        body_lay.setSpacing(6)

        self.task_table = TaskTableWidget()
        self.task_table.setObjectName("transcript_table")
        self.task_table.setColumnCount(_COL_COUNT)
        self.task_table.setHorizontalHeaderLabels(["", "#", "PROJECT", "STATUS"])
        self.task_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = self.task_table.horizontalHeader()
        header.setHighlightSections(False)
        header.setMinimumSectionSize(20)
        header.setSectionResizeMode(_CHECK_COL, QHeaderView.ResizeMode.Fixed)
        self.task_table.setColumnWidth(_CHECK_COL, _CHECK_W)
        header.setSectionResizeMode(_INDEX_COL, QHeaderView.ResizeMode.Fixed)
        self.task_table.setColumnWidth(_INDEX_COL, _INDEX_W)
        self.task_table.horizontalHeaderItem(_INDEX_COL).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setSectionResizeMode(_NAME_COL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_STATUS_COL, QHeaderView.ResizeMode.Fixed)
        self.task_table.setColumnWidth(_STATUS_COL, _STATUS_W)
        self.task_table.horizontalHeaderItem(_STATUS_COL).setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.task_table.setItemDelegateForColumn(_NAME_COL, TaskNameDelegate(self.task_table))
        self.task_table.setItemDelegateForColumn(_STATUS_COL, StatusBadgeDelegate(self.task_table))

        # Header checkbox for batch select / clear — centered in the check column.
        self._hdr_check = QCheckBox(header)
        self._hdr_check.setObjectName("task_row_check")
        self._hdr_check.setToolTip("Select all visible tasks")
        self._hdr_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hdr_check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hdr_check.stateChanged.connect(self._on_header_check)
        header.sectionResized.connect(lambda *_: self._place_header_check())
        header.geometriesChanged.connect(self._place_header_check)
        QTimer.singleShot(0, self._place_header_check)

        self.task_table.verticalHeader().setVisible(False)
        self.task_table.verticalHeader().setDefaultSectionSize(_ROW_H)
        self.task_table.setIconSize(QSize(_THUMB_SIZE, _THUMB_SIZE))
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.task_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.task_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.task_table.setShowGrid(False)
        self.task_table.setWordWrap(False)
        self.task_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.task_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.task_table.customContextMenuRequested.connect(self._task_context_menu)
        self.task_table.cellClicked.connect(self._on_task_clicked)
        self.task_table.files_dropped.connect(self._queue_tasks)
        self.task_table.delete_pressed.connect(self._on_table_delete_key)
        self.task_table.open_pressed.connect(self._on_table_open_key)

        self._click_out = _ClickOut(self.task_table, self._deselect_task)
        self.task_table.viewport().installEventFilter(self._click_out)
        body_lay.addWidget(self.task_table, 1)

        self.task_hint = QLabel("No tasks yet · Drag & drop video files or click + Add")
        self.task_hint.setObjectName("dub_panel_hint")
        self.task_hint.setWordWrap(True)
        body_lay.addWidget(self.task_hint)
        root.addWidget(body, 1)
        return panel

    def _place_header_check(self):
        if not hasattr(self, "_hdr_check") or not hasattr(self, "task_table"):
            return
        header = self.task_table.horizontalHeader()
        x = header.sectionViewportPosition(_CHECK_COL)
        width = header.sectionSize(_CHECK_COL)
        height = header.height()
        # Match row checkbox indicator size so header and rows share the same center.
        side = 14
        self._hdr_check.setParent(header)
        self._hdr_check.setGeometry(
            x + max(0, (width - side) // 2),
            max(0, (height - side) // 2),
            side,
            side,
        )
        self._hdr_check.show()


    def _make_row_check(self, task_id: int) -> QWidget:
        """Centered checkbox widget — aligns with the header check column."""
        wrap = QWidget()
        wrap.setObjectName("task_check_cell")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box = QCheckBox()
        box.setObjectName("task_row_check")
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        box.setChecked(task_id in self._task_checked)
        box.stateChanged.connect(lambda state, tid=task_id: self._on_row_check(tid, state))
        lay.addWidget(box)
        return wrap

    def _on_row_check(self, task_id: int, state: int):
        if state == Qt.CheckState.Checked.value:
            self._task_checked.add(task_id)
        else:
            self._task_checked.discard(task_id)
        self._sync_header_check()
        self._sync_export_enabled()
        self._sync_delete_enabled()

    def _visible_tasks(self) -> list[dict]:
        key = self._task_filter
        if key == "all":
            return list(self._tasks)
        if key == "active":
            return [t for t in self._tasks if t["status"] in _ACTIVE]
        if key == "failed":
            return [t for t in self._tasks if t["status"] in _FAILED]
        return [t for t in self._tasks if t["status"] == key]

    def _sync_task_filter_caption(self):
        if not hasattr(self, "btn_task_filter"):
            return
        counts = {
            "all": len(self._tasks),
            "done": sum(1 for t in self._tasks if t["status"] == "done"),
            "queued": sum(1 for t in self._tasks if t["status"] == "queued"),
            "active": sum(1 for t in self._tasks if t["status"] in _ACTIVE),
            "failed": sum(1 for t in self._tasks if t["status"] in _FAILED),
        }
        if hasattr(self, "_task_filter_group"):
            for act in self._task_filter_group.actions():
                key = str(act.data() or "all")
                base_label = next((label for k, label in _FILTERS if k == key), "All")
                act.setText(f"{base_label} ({counts.get(key, 0)})")

        active_key = self._task_filter
        base_name = next((name for key, name in _FILTERS if key == active_key), "All")
        count = counts.get(active_key, len(self._tasks))
        self.btn_task_filter.setText(f"{base_name} ({count})")
        self.btn_task_filter.setMinimumWidth(max(54, self.btn_task_filter.sizeHint().width()))

    def _on_task_filter(self, action: QAction):
        key = str(action.data() or "all")
        if key == self._task_filter:
            return
        self._task_filter = key
        self._sync_task_filter_caption()
        self._refresh_tasks()

    def _on_header_check(self, state: int):
        visible = self._visible_tasks()
        checked = state == Qt.CheckState.Checked.value
        if checked:
            self._task_checked.update(t["id"] for t in visible)
        else:
            self._task_checked.difference_update(t["id"] for t in visible)
        self._refresh_tasks()

    def _sync_header_check(self):
        if not hasattr(self, "_hdr_check"):
            return
        visible = self._visible_tasks()
        self._hdr_check.blockSignals(True)
        if not visible:
            self._hdr_check.setCheckState(Qt.CheckState.Unchecked)
        elif all(t["id"] in self._task_checked for t in visible):
            self._hdr_check.setCheckState(Qt.CheckState.Checked)
        elif any(t["id"] in self._task_checked for t in visible):
            self._hdr_check.setCheckState(Qt.CheckState.PartiallyChecked)
        else:
            self._hdr_check.setCheckState(Qt.CheckState.Unchecked)
        self._hdr_check.blockSignals(False)

    def _ready_checked_tasks(self) -> list[dict]:
        return [
            t for tid in self._task_checked
            if (t := self._task_by_id(tid)) and t["status"] == "done" and t["comp"] >= 0
        ]

    def _sync_export_enabled(self):
        if not hasattr(self, "btn_export_tasks"):
            return
        ready = self._ready_checked_tasks()
        n = len(ready)
        self.btn_export_tasks.setEnabled(n > 0)
        if n > 0:
            self.btn_export_tasks.setText(f"Export ({n})")
            self.btn_export_tasks.setToolTip(f"Export {n} checked ready task{'s' if n != 1 else ''}")
            self.btn_export_tasks.setIcon(icon("download", color="#ffffff", size=15))
        else:
            self.btn_export_tasks.setText("Export")
            self.btn_export_tasks.setToolTip("Export checked ready tasks — select tasks with '✓'")
            self.btn_export_tasks.setIcon(icon("download", color="#627184", size=15))
        self.btn_export_tasks.setMinimumWidth(max(56, self.btn_export_tasks.sizeHint().width()))

    def _sync_delete_enabled(self):
        if not hasattr(self, "btn_delete_tasks"):
            return
        n = len(self._task_checked)
        if n > 0:
            self.btn_delete_tasks.setToolTip(f"Delete {n} selected task{'s' if n != 1 else ''} (Del)")
            self.btn_delete_tasks.setIcon(icon("trash", color="#fca5a5", size=15))
            self.btn_delete_tasks.setVisible(True)
            self.btn_delete_tasks.setEnabled(True)
        else:
            self.btn_delete_tasks.setVisible(False)
            self.btn_delete_tasks.setEnabled(False)


    def _choose_and_queue_files(self):
        """Open native file dialog to queue video files directly."""
        parent = self.task_table if hasattr(self, "task_table") else None
        paths, _ = QFileDialog.getOpenFileNames(
            parent,
            "Add Video to Dubbing Queue",
            "",
            "Video Files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.flv);;All Files (*.*)",
        )
        if paths:
            self._queue_tasks(paths)
            self.log.info(f"Queued {len(paths)} video file(s)")

    def _select_all_tasks(self, check: bool):
        visible = self._visible_tasks()
        if check:
            self._task_checked.update(t["id"] for t in visible)
        else:
            self._task_checked.clear()
        self._refresh_tasks()

    def _select_ready_tasks(self):
        ready_ids = {t["id"] for t in self._visible_tasks() if t["status"] == "done"}
        self._task_checked = set(ready_ids)
        self._refresh_tasks()

    def _on_table_delete_key(self):
        if self._task_checked:
            self._delete_checked_tasks()
        elif self._task_selected_id >= 0:
            self._delete_task(self._task_selected_id)

    def _on_table_open_key(self):
        row = self.task_table.currentRow()
        visible = self._visible_tasks()
        if 0 <= row < len(visible):
            self._on_task_clicked(row, _NAME_COL)

    def _copy_task_path(self, task_id: int):
        task = self._task_by_id(task_id)
        if not task:
            return
        src = str(task.get("source") or "")
        if src:
            QApplication.clipboard().setText(src)
            self.log.info(f"Copied path · {os.path.basename(src)}")

    def _reveal_task_file(self, task_id: int):
        task = self._task_by_id(task_id)
        if not task:
            return
        src = str(task.get("source") or "")
        if not src:
            return
        folder = os.path.dirname(src) if os.path.isfile(src) else src
        if os.path.exists(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            self.log.warn(f"Folder not found: {folder}")

    def _export_single_task(self, task_id: int):
        self._task_checked = {task_id}
        self._sync_header_check()
        self._sync_export_enabled()
        self._sync_delete_enabled()
        self._export_checked_tasks()

    def _batch_export_tasks(self, ready: list[dict]):
        from claynext.utils.config import OUTPUTS_DIR
        parent = self.task_table if hasattr(self, "task_table") else None
        reply = QMessageBox.question(
            parent,
            "Batch Export",
            f"Export {len(ready)} ready compositions to output directory?\n\nDestination: {OUTPUTS_DIR}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        first = ready[0]
        row = next((i for i, t in enumerate(self._visible_tasks()) if t["id"] == first["id"]), -1)
        if row >= 0:
            self._task_selected_id = -1
            self._on_task_clicked(row, _NAME_COL)
        if hasattr(self, "open_export_dialog"):
            self.open_export_dialog()
        self.log.info(f"Batch export initiated for {len(ready)} tasks")

    def _export_checked_tasks(self):
        ready = self._ready_checked_tasks()
        if not ready:
            self.log.warn("Check a ready task to export")
            self._sync_export_enabled()
            return
        if len(ready) == 1:
            task = ready[0]
            # Load the composition onto the timeline, then open export settings.
            if task["id"] != self._task_selected_id:
                row = next((i for i, t in enumerate(self._visible_tasks()) if t["id"] == task["id"]), -1)
                if row >= 0:
                    self._task_selected_id = -1  # force open even if re-clicked
                    self._on_task_clicked(row, _NAME_COL)
            if hasattr(self, "open_export_dialog"):
                # Show full export config dialog (format, folder, encode options).
                self.open_export_dialog()
            else:
                self.log.info(f"Export · {task['name']}")
        else:
            self._batch_export_tasks(ready)

    # ── Task model ──────────────────────────────────────────────────────

    def _add_task(self, source: str, status: str = "queued", comp: int = -1) -> dict:
        self._task_seq += 1
        task = {
            "id": self._task_seq,
            "name": os.path.basename(source) if source else f"Dub {self._task_seq}",
            "source": source,
            "status": status,
            "stages": [100 if status == "done" else -1 for _stage in STAGES],
            "stage": len(STAGES) if status == "done" else -1,
            "progress": 100 if status == "done" else 0,
            "message": "",
            "comp": comp,
        }
        self._tasks.append(task)
        self._request_task_thumb(source)
        self._refresh_tasks()
        return task

    def _task_by_id(self, task_id: int) -> dict | None:
        return next((task for task in self._tasks if task["id"] == task_id), None)

    def _queue_tasks(self, sources: list[str]):
        for source in sources:
            self._add_task(source)
        if hasattr(self, "shelf"):
            self.shelf.show_key("tasks")

    def _start_next_task(self, source: str) -> dict:
        task = next(
            (t for t in self._tasks if t["status"] == "queued" and t["source"] == source),
            None,
        ) or self._add_task(source)
        task["status"] = "running"
        task["stages"] = [-1 for _stage in STAGES]
        task["stage"] = 0
        task["progress"] = 0
        task["message"] = "Starting…"
        task["live"] = []
        self._active_task = task["id"]
        self._refresh_tasks()
        return task

    def _task_progress(self, value: int, message: str):
        task = self._task_by_id(self._active_task)
        if not task or task["status"] not in _ACTIVE:
            return
        value = max(0, min(100, int(value)))
        index = next(
            (i for i, (_n, _t, start, end) in enumerate(STAGES) if start <= value < end),
            len(STAGES) - 1,
        )
        index = max(index, task["stage"])
        for i in range(index):
            task["stages"][i] = 100
        _n, _t, start, end = STAGES[index]
        done = int((value - start) * 100 / max(1, end - start))
        task["stages"][index] = max(task["stages"][index], min(100, max(0, done)))
        task["stage"] = index
        task["progress"] = value
        task["message"] = message
        # Prefer a light status-cell update while running (avoid full table rebuild)
        if hasattr(self, "task_table") and self._patch_status_progress(task):
            self._sync_task_hint()
            return
        self._refresh_tasks()

    def _link_task(self, comp_index: int, source: str):
        task = self._task_by_id(self._active_task)
        if task and task["status"] in _ACTIVE:
            task["comp"] = comp_index
            task["status"] = "done"
            task["stages"] = [100 for _stage in STAGES]
            task["stage"] = len(STAGES)
            task["progress"] = 100
            task["message"] = ""
            task.pop("live", None)
            task.pop("control", None)
            if self._viewing_task == task["id"]:
                self._viewing_task = -1
            self._active_task = -1
            self._refresh_tasks()
            return
        self._add_task(source, status="done", comp=comp_index)

    def _fail_tasks(self, message: str, status: str = "failed"):
        task = self._task_by_id(self._active_task)
        if task and task["status"] in _ACTIVE:
            task["status"] = status
            task["message"] = message
            task.pop("control", None)
        for item in self._tasks:
            if item["status"] == "queued":
                item["status"] = "cancelled"
        self._active_task = -1
        self._refresh_tasks()

    # ── Task actions ───────────────────────────────────────────────────

    def _toggle_task_pause(self, task_id: int):
        task = self._task_by_id(task_id)
        control = task.get("control") if task else None
        if not task or control is None or task["status"] not in _ACTIVE:
            return
        if task["status"] == "running":
            control.pause()
            task["status"] = "paused"
            self.log.info(f"Paused · {task['name']}")
        else:
            control.resume()
            task["status"] = "running"
            self.log.info(f"Continuing · {task['name']}")
        self._refresh_tasks()

    def _stop_task(self, task_id: int):
        task = self._task_by_id(task_id)
        if not task or task["status"] not in _ACTIVE:
            return
        control = task.get("control")
        if control is not None:
            control.cancel()
        else:
            task["status"] = "cancelled"
            task["message"] = "Stopped"
            task.pop("control", None)
            if self._active_task == task_id:
                self._active_task = -1
            self._refresh_tasks()
        # Also soft-stop any overlapping script segment worker
        if hasattr(self, "_cancel_script_job"):
            self._cancel_script_job()
        self.log.info(f"Stopping · {task['name']}")

    def _stop_active_job(self):
        if self._active_task >= 0:
            self._stop_task(self._active_task)

    def _start_task(self, task_id: int):
        """Start a queued task when the pipeline is idle."""
        task = self._task_by_id(task_id)
        if not task or task["status"] != "queued":
            return
        if getattr(self, "_dub_busy", False) or self._active_task >= 0:
            self.log.warn("A dub is already running")
            return
        source = str(task.get("source") or "")
        if not source or not os.path.isfile(source):
            self.log.warn(f"Missing media · {task['name']}")
            return
        voice_id = self.combo_voice.currentData() if hasattr(self, "combo_voice") else None
        if not voice_id:
            self._show_error("No voice", "Choose an Edge neural voice.")
            return
        from claynext.gui.dialogs.env_alert import ensure_job_environment

        sec = (
            self.combo_voice_sec.currentData()
            if hasattr(self, "combo_voice_sec")
            else ""
        )
        asr_model = (
            self.combo_model.currentText()
            if hasattr(self, "combo_model")
            else "whisper-small"
        )
        if not ensure_job_environment(
            self,
            voice_id=str(voice_id or ""),
            secondary_voice_id=str(sec or ""),
            asr_model=str(asr_model or ""),
            title="Download environment",
        ):
            self.log.warn("Task start blocked — missing environment")
            return
        self._dub_queue = [
            t["source"] for t in self._tasks
            if t["status"] == "queued" and t["id"] != task_id and t.get("source")
        ]
        self.set_dub_source(source)
        self._clear_error()
        self._fill_table([])
        self._set_busy(True)
        self._focus_script_shelf()
        self._launch_dub_job()

    def _confirm_remove(self, title: str, message: str) -> bool:
        parent = self.task_table if hasattr(self, "task_table") else None
        reply = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _delete_task(self, task_id: int, *, confirm: bool = True):
        task = self._task_by_id(task_id)
        if not task:
            return
        if confirm and not self._confirm_remove(
            "Remove task",
            f"Remove “{task['name']}” from the task list?\nThis cannot be undone.",
        ):
            return
        if task["status"] in _ACTIVE:
            self._stop_task(task_id)
        if self._task_selected_id == task_id:
            self._task_selected_id = -1
        if self._viewing_task == task_id:
            self._leave_live_view()
        self._task_cells.pop(task_id, None)
        self._task_checked.discard(task_id)
        self._tasks = [t for t in self._tasks if t["id"] != task_id]
        if self._active_task == task_id:
            self._active_task = -1
        self._refresh_tasks()
        self.log.info(f"Removed task · {task['name']}")

    def _clear_finished_tasks(self):
        keep = {"queued", "running", "paused"}
        removed_ids = {t["id"] for t in self._tasks if t["status"] not in keep}
        if not removed_ids:
            return
        n = len(removed_ids)
        if not self._confirm_remove(
            "Clear finished",
            f"Remove {n} finished task{'s' if n != 1 else ''} from the list?\nThis cannot be undone.",
        ):
            return
        before = len(self._tasks)
        if self._task_selected_id in removed_ids:
            self._task_selected_id = -1
        if self._viewing_task in removed_ids:
            self._leave_live_view()
        for tid in removed_ids:
            self._task_cells.pop(tid, None)
            self._task_checked.discard(tid)
        self._tasks = [t for t in self._tasks if t["status"] in keep]
        removed = before - len(self._tasks)
        self._refresh_tasks()
        if removed:
            self.log.info(f"Cleared {removed} finished task(s)")

    def _open_task(self, task_id: int):
        """Select and open a task (timeline or live view)."""
        row = next((i for i, t in enumerate(self._visible_tasks()) if t["id"] == task_id), -1)
        if row < 0:
            return
        if self._task_selected_id == task_id:
            return
        self._on_task_clicked(row, _NAME_COL)

    # ── Thumbnails ─────────────────────────────────────────────────────

    def _fallback_task_icon(self, path: str) -> QIcon:
        ext = os.path.splitext(path or "")[1].lower()
        if ext in VIDEO_EXTS:
            return icon("video", color="#64748b", size=14)
        if ext in IMAGE_EXTS:
            return icon("image", color="#64748b", size=14)
        return icon("image", color="#64748b", size=14)

    def _task_icon(self, task: dict) -> QIcon:
        path = str(task.get("source") or "")
        return self._fallback_task_icon(path)

    def _task_thumb_pixmap(self, path: str) -> QPixmap | None:
        path = str(path or "")
        if not path:
            return None
        if path in self._task_thumbs:
            return self._task_thumbs[path]
        # Fast synchronous lookup from disk thumbnail cache
        t_file = thumb_path_for(path, 160)
        if t_file.is_file() and t_file.stat().st_size > 0:
            pix = QPixmap(str(t_file))
            if not pix.isNull():
                self._task_thumbs[path] = pix
                return pix
        return None

    def _request_task_thumb(self, path: str):
        path = str(path or "")
        if not path or path in self._task_thumbs or path in self._thumb_pending:
            return
        if not os.path.isfile(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in VIDEO_EXTS and ext not in IMAGE_EXTS:
            return
        self._thumb_pending.add(path)

        def _load(progress_callback=None):
            return pixmap_for(path, QSize(160, 160))

        worker = Worker(_load)
        worker.signals.result.connect(lambda pix, p=path: self._on_task_thumb(p, pix))
        worker.signals.error.connect(lambda *_a, p=path: self._thumb_pending.discard(p))
        QThreadPool.globalInstance().start(worker)

    def _on_task_thumb(self, path: str, pix: QPixmap):
        self._thumb_pending.discard(path)
        if not isinstance(pix, QPixmap) or pix.isNull():
            return
        self._task_thumbs[path] = pix
        if not hasattr(self, "task_table"):
            return
        table = self.task_table
        for row, task in enumerate(self._visible_tasks()):
            if str(task.get("source") or "") != path:
                continue
            item = table.item(row, _NAME_COL)
            if item is not None:
                item.setData(Qt.ItemDataRole.UserRole + 4, pix)
        table.viewport().update()


    # ── Live job view ──────────────────────────────────────────────────

    def _on_live_event(self, task_id: int, kind: str, payload):
        task = self._task_by_id(task_id)
        if not task:
            return
        live = task.setdefault("live", [])
        if kind in {"transcript", "translated"} and isinstance(payload, list):
            done = {i: seg for i, seg in enumerate(live) if seg.get("audio_path")}
            task["live"] = [done.get(i, dict(seg)) for i, seg in enumerate(payload)]
        elif kind == "clip" and isinstance(payload, dict):
            index = int(payload.get("index", -1))
            segment = dict(payload.get("segment") or {})
            if index < 0:
                return
            while len(live) <= index:
                live.append({})
            live[index] = {**live[index], **segment}
            task["live_clip"] = index
        follow = int(getattr(self, "_script_follow_task", -1) or -1)
        if self._viewing_task == task_id or follow == task_id:
            self._live_timer.start()

    def _view_live_task(self, task: dict):
        if self._viewing_task != task["id"]:
            if self._composition_index >= 0:
                self._stash_composition()
                self._live_return_index = self._composition_index
            self._composition_index = -1
            self._viewing_task = task["id"]
            self._live_paint_keys = None
            self._live_scroll_row = None
            source = task.get("source") or ""
            if hasattr(self, "_ensure_source_sequence"):
                self._ensure_source_sequence(source)
        self._render_live_task()
        self._timeline_open = True
        self.show_timeline_player()
        self._sync_timeline_visibility()

    def _render_live_task(self):
        task_id = self._viewing_task
        if task_id < 0:
            task_id = int(getattr(self, "_script_follow_task", -1) or -1)
        task = self._task_by_id(task_id)
        if not task:
            return
        segments = [seg for seg in task.get("live") or [] if isinstance(seg, dict) and seg]
        source = str(task.get("source") or "")
        if source and hasattr(self, "_ensure_source_sequence"):
            already = (
                hasattr(self, "_source_already_on_track")
                and self._source_already_on_track(source)
            )
            if not already:
                self._ensure_source_sequence(source)
        keys = None
        if hasattr(self, "_script_row_key"):
            keys = tuple(self._script_row_key(seg, i) for i, seg in enumerate(segments))
        if keys is not None and keys == getattr(self, "_live_paint_keys", None):
            self._scroll_live_row(task)
            return
        same_shape = (
            len(segments) > 0
            and len(segments) == self.table.rowCount()
            and len(segments) == len(getattr(self, "_segments", []))
        )
        patched = same_shape and hasattr(self, "_patch_script_rows") and self._patch_script_rows(segments)
        if patched:
            if hasattr(self.timeline, "sync_dialogue"):
                self.timeline.sync_dialogue(segments)
            else:
                self.timeline.set_dialogue(segments)
        else:
            self._fill_table(segments)
        self._live_paint_keys = keys
        self._scroll_live_row(task)

    def _scroll_live_row(self, task: dict):
        row = int(task.get("live_clip", -1) if task.get("live_clip") is not None else -1)
        if row == getattr(self, "_live_scroll_row", None):
            return
        self._live_scroll_row = row
        if 0 <= row < self.table.rowCount():
            item = self.table.item(row, 0)
            if item is not None:
                self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _leave_live_view(self):
        if self._viewing_task < 0:
            return
        self._viewing_task = -1
        self._live_paint_keys = None
        self._live_scroll_row = None
        self._live_timer.stop()
        index = self._live_return_index
        self._live_return_index = -1
        if 0 <= index < len(self._compositions):
            self.timeline.set_compositions([c["name"] for c in self._compositions], index)
            self._apply_composition(index)
        else:
            self._fill_table([])

    # ── Selection ──────────────────────────────────────────────────────

    def _on_task_clicked(self, row: int, col: int):
        if col == _CHECK_COL:
            return
        visible = self._visible_tasks()
        if row < 0 or row >= len(visible):
            return
        task = visible[row]
        if task["id"] == self._task_selected_id:
            self._deselect_task()
            return
        self._task_selected_id = task["id"]
        if 0 <= task["comp"] < len(self._compositions):
            self._viewing_task = -1
            if task["comp"] != self._composition_index:
                self._stash_composition()
                self.timeline.set_compositions(
                    [item["name"] for item in self._compositions], task["comp"],
                )
                self._apply_composition(task["comp"])
            self._timeline_open = True
            self.show_timeline_player()
            self._sync_timeline_visibility()
        elif task["status"] in _ACTIVE:
            self._view_live_task(task)
            self.log.info(f"Watching {task['name']} live")
        self._refresh_tasks()

    def _deselect_task(self):
        if self._task_selected_id < 0 and self._viewing_task < 0:
            return
        self._task_selected_id = -1
        self._leave_live_view()
        self._sync_timeline_visibility()
        self._refresh_tasks()

    # ── Context menu ───────────────────────────────────────────────────

    def _task_context_menu(self, pos):
        row = self.task_table.rowAt(pos.y())
        visible = self._visible_tasks()
        if row < 0 or row >= len(visible):
            return
        task = visible[row]
        tid = task["id"]
        status = task["status"]
        busy = bool(getattr(self, "_dub_busy", False) or self._active_task >= 0)

        menu = QMenu(self.task_table)
        menu.setObjectName("media_lib_menu")

        if status == "queued":
            start = menu.addAction(icon("play", size=14), "Start Dubbing")
            start.setEnabled(not busy)
            start.triggered.connect(lambda: self._start_task(tid))
        elif status in _ACTIVE:
            if status == "running":
                pause = menu.addAction(icon("pause", size=14), "Pause")
                pause.setEnabled(task.get("control") is not None)
                pause.triggered.connect(lambda: self._toggle_task_pause(tid))
            else:
                cont = menu.addAction(icon("play", size=14), "Continue")
                cont.setEnabled(task.get("control") is not None)
                cont.triggered.connect(lambda: self._toggle_task_pause(tid))
            stop = menu.addAction(icon("stop", size=14), "Stop")
            stop.triggered.connect(lambda: self._stop_task(tid))
        elif status == "done" and task["comp"] >= 0:
            open_act = menu.addAction(icon("timeline", size=14), "Open in Timeline")
            open_act.triggered.connect(lambda: self._open_task(tid))
            exp_act = menu.addAction(icon("export", size=14), "Export Composition")
            exp_act.triggered.connect(lambda: self._export_single_task(tid))
        elif status in {"failed", "cancelled"} and task.get("source"):
            retry = menu.addAction(icon("refresh", size=14), "Retry Task")
            retry.setEnabled(not busy and os.path.isfile(str(task.get("source") or "")))
            retry.triggered.connect(lambda: self._retry_task(tid))

        menu.addSeparator()
        if task.get("source"):
            reveal_label = "Reveal in Finder" if os.name == "posix" else "Show in Explorer"
            reveal = menu.addAction(icon("folder", size=14), reveal_label)
            reveal.triggered.connect(lambda: self._reveal_task_file(tid))
            copy_p = menu.addAction(icon("copy", size=14), "Copy File Path")
            copy_p.triggered.connect(lambda: self._copy_task_path(tid))
            menu.addSeparator()

        checked = [i for i in self._task_checked if self._task_by_id(i)]
        if len(checked) > 1:
            batch = menu.addAction(icon("trash", size=14), f"Delete {len(checked)} selected tasks")
            batch.triggered.connect(self._delete_checked_tasks)
        else:
            delete = menu.addAction(icon("trash", size=14), "Delete Task")
            delete.triggered.connect(lambda: self._delete_task(tid))
        if any(t["status"] not in {"queued", "running", "paused"} for t in self._tasks):
            clear = menu.addAction("Clear finished tasks")
            clear.triggered.connect(self._clear_finished_tasks)
        menu.exec(self.task_table.viewport().mapToGlobal(pos))

    def _delete_checked_tasks(self):
        ids = [tid for tid in self._task_checked if self._task_by_id(tid)]
        if not ids:
            return
        n = len(ids)
        if not self._confirm_remove(
            "Remove tasks",
            f"Remove {n} selected task{'s' if n != 1 else ''} from the list?\nThis cannot be undone.",
        ):
            return
        for tid in ids:
            self._delete_task(tid, confirm=False)

    def _retry_task(self, task_id: int):
        task = self._task_by_id(task_id)
        if not task:
            return
        source = str(task.get("source") or "")
        if not source or not os.path.isfile(source):
            return
        task["status"] = "queued"
        task["stages"] = [-1 for _stage in STAGES]
        task["stage"] = -1
        task["message"] = ""
        task["comp"] = -1
        task.pop("control", None)
        task.pop("live", None)
        self._refresh_tasks()
        self._start_task(task_id)

    # ── Table rendering ────────────────────────────────────────────────

    def _format_task_subtitle(self, task: dict) -> str:
        status = task.get("status", "queued")
        msg = task.get("message", "")
        if status == "done":
            comp = task.get("comp", -1)
            comps = getattr(self, "_compositions", [])
            if 0 <= comp < len(comps):
                if comp == getattr(self, "_composition_index", -1) and getattr(self, "_timeline_open", False):
                    return f"Comp #{comp + 1} · Active on timeline"
                return f"Comp #{comp + 1} · Ready to export"
            return "Ready to export"
        if status == "running":
            stage_idx = task.get("stage", 0)
            stage_name = STAGES[stage_idx][0] if 0 <= stage_idx < len(STAGES) else "Processing"
            return f"{stage_name} · {msg}" if msg else f"Dubbing · {stage_name}"
        if status == "paused":
            return f"Paused · {msg}" if msg else "Paused"
        if status == "queued":
            return "Waiting in queue"

        if status in {"failed", "cancelled"}:
            return f"Error: {msg}" if msg else "Failed · Right-click to retry"
        return msg or status.capitalize()

    def _format_task_tooltip(self, task: dict) -> str:
        parts = []
        if task.get("name"):
            parts.append(f"Task: {task['name']}")
        if task.get("source"):
            parts.append(f"Source: {task['source']}")
        status = task.get("status", "queued")
        parts.append(f"Status: {_STATUS_LABELS.get(status, status)}")
        if task.get("message"):
            parts.append(f"Details: {task['message']}")
        if task.get("comp", -1) >= 0:
            parts.append(f"Composition: #{task['comp'] + 1}")
        return "\n".join(parts)

    def _refresh_tasks(self):
        if not hasattr(self, "task_table"):
            return
        table = self.task_table
        visible = self._visible_tasks()
        # Drop checks for tasks that no longer exist.
        live_ids = {t["id"] for t in self._tasks}
        # Clean up existing cell widgets to prevent orphans lingering in viewport
        for r in range(table.rowCount()):
            old_w = table.cellWidget(r, _CHECK_COL)
            if old_w is not None:
                table.removeCellWidget(r, _CHECK_COL)
                old_w.hide()
                old_w.deleteLater()

        table.blockSignals(True)
        table.setRowCount(len(visible))

        current = -1
        for row, task in enumerate(visible):
            src = str(task.get("source") or "")
            pix = self._task_thumb_pixmap(src)
            if pix is None and src:
                self._request_task_thumb(src)

            # Centered checkbox cell widget
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            check_item.setData(Qt.ItemDataRole.UserRole, task["id"])
            table.setItem(row, _CHECK_COL, check_item)
            table.setCellWidget(row, _CHECK_COL, self._make_row_check(task["id"]))

            index = QTableWidgetItem(str(row + 1))
            index.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            index.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            index.setForeground(QColor(COLOR_TEXT_MUTED))
            table.setItem(row, _INDEX_COL, index)

            name = QTableWidgetItem(task["name"])
            name.setIcon(self._task_icon(task))
            if pix is not None and not pix.isNull():
                name.setData(Qt.ItemDataRole.UserRole + 4, pix)
            name.setToolTip(self._format_task_tooltip(task))
            name.setData(Qt.ItemDataRole.UserRole, task["id"])
            name.setData(Qt.ItemDataRole.UserRole + 3, self._format_task_subtitle(task))
            table.setItem(row, _NAME_COL, name)
            table.setRowHeight(row, _ROW_H)
            self._sync_status_cell(row, task)
            if task["id"] == self._task_selected_id:
                current = row

        for task_id in [tid for tid in self._task_cells if tid not in live_ids]:
            self._task_cells.pop(task_id, None)
        if current >= 0:
            table.selectRow(current)
        else:
            table.clearSelection()
        table.blockSignals(False)

        self._sync_header_check()
        self._sync_export_enabled()
        self._sync_delete_enabled()
        self._sync_task_filter_caption()
        self._sync_task_hint()
        self._sync_timeline_button()
        self._place_header_check()
        # Animate STATUS spinner while any visible task is running/paused
        delegate = self.task_table.itemDelegateForColumn(_STATUS_COL)
        if isinstance(delegate, StatusBadgeDelegate):
            has_active = any(t.get("status") in _ACTIVE for t in visible)
            delegate.set_animating(has_active)

    def _sync_status_cell(self, row: int, task: dict):
        table = self.task_table
        status = task["status"]
        try:
            progress = int(task.get("progress") or 0)
        except (TypeError, ValueError):
            progress = 0
        if status == "done":
            progress = 100
        stage = ""
        if 0 <= int(task.get("stage", -1)) < len(STAGES):
            stage = STAGES[int(task["stage"])][0]
        label = QTableWidgetItem(_STATUS_LABELS.get(status, status))
        label.setData(Qt.ItemDataRole.UserRole, status)
        label.setData(_ROLE_PROGRESS, progress)
        label.setData(_ROLE_STAGE, stage)
        msg = task.get("message", "")
        tip = f"Status: {_STATUS_LABELS.get(status, status)}"
        if status in _ACTIVE:
            tip += f"\nProgress: {progress}%"
            if stage:
                tip += f" · {stage}"
        if msg:
            tip += f"\n{msg}"
        label.setToolTip(tip)
        table.setItem(row, _STATUS_COL, label)

    def _patch_status_progress(self, task: dict) -> bool:
        """Update STATUS cell data in-place for the given task. Returns True if found."""
        table = getattr(self, "task_table", None)
        if table is None:
            return False
        tid = task.get("id")
        for row in range(table.rowCount()):
            name_item = table.item(row, _NAME_COL)
            if name_item is None or name_item.data(Qt.ItemDataRole.UserRole) != tid:
                continue
            self._sync_status_cell(row, task)
            table.viewport().update()
            return True
        return False

    def _sync_task_hint(self):
        if not hasattr(self, "task_hint"):
            return
        if not self._tasks:
            self.task_hint.setText("No tasks yet · Drag & drop video files or click + Add")
            return
        active = self._task_by_id(self._active_task)
        if active and active["status"] == "paused":
            pct = int(active.get("progress") or 0)
            self.task_hint.setText(f"Paused · {pct}% · {active['name']}")
            return
        if active and active["status"] == "running":
            pct = int(active.get("progress") or 0)
            stage = STAGES[active["stage"]][0] if 0 <= active["stage"] < len(STAGES) else "…"
            msg = active["message"] or stage
            self.task_hint.setText(f"Dubbing · {pct}% · {active['name']} · {msg}")
            return
        ready = sum(1 for t in self._tasks if t["status"] == "done")
        queued = sum(1 for t in self._tasks if t["status"] == "queued")
        parts = [f"{len(self._tasks)} task" + ("" if len(self._tasks) == 1 else "s")]
        if ready:
            parts.append(f"{ready} ready")
        if queued:
            parts.append(f"{queued} queued")
        self.task_hint.setText(" · ".join(parts))

    def _toggle_timeline(self, checked: bool | None = None):
        if isinstance(checked, bool) and self.sender() is getattr(self, "act_timeline", None):
            self._timeline_open = checked
        else:
            self._timeline_open = not bool(self._timeline_open)
        self._sync_timeline_visibility()
        if hasattr(self, "_save_layout"):
            self._save_layout()

    def _sync_timeline_button(self):
        act = getattr(self, "act_timeline", None)
        if act is not None:
            act.blockSignals(True)
            act.setEnabled(True)
            act.setChecked(bool(self._timeline_open))
            tip = (
                f"{'Hide' if self._timeline_open else 'Show'} timeline "
                f"({QKeySequence('Ctrl+Shift+T').toString(QKeySequence.SequenceFormat.NativeText)})"
            )
            act.setToolTip(tip)
            act.blockSignals(False)

