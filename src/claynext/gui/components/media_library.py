from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QFileDialog, QToolButton, QMenu, QStackedWidget, QAbstractItemView,
    QButtonGroup, QSizePolicy, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QApplication,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem, QFrame,
)
from PySide6.QtCore import (
    Qt, Signal, QSize, QRunnable, QThreadPool, QObject, QUrl, QMimeData,
    QItemSelectionModel, QItemSelection, QPoint, QRectF, QModelIndex,
)
from PySide6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QIcon, QAction, QActionGroup,
    QMouseEvent, QPainter, QPainterPath, QPen, QFont, QPixmap,
)

from claynext.constants.theme_constants import (
    COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_SUB, COLOR_ACCENT_PURPLE,
    COLOR_BORDER, COLOR_BG_CARD, COLOR_BG_DARK, COLOR_PRIMARY,
)
from claynext.gui.icons import icon
from claynext.models.thumbnails import icon_for, VIDEO_EXTS, IMAGE_EXTS


class _MediaList(QListWidget):
    """Grid view that can drag local files onto the timeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def mimeData(self, items):
        mime = super().mimeData(items) or QMimeData()
        urls = []
        for item in items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and os.path.isfile(path):
                urls.append(QUrl.fromLocalFile(path))
        if urls:
            mime.setUrls(urls)
        return mime


# List columns: index · check · preview · name · type · duration · size
_COL_INDEX, _COL_CHECK, _COL_PREVIEW, _COL_NAME, _COL_TYPE, _COL_DUR, _COL_SIZE = range(7)


class _MediaTableDelegate(QStyledItemDelegate):
    """Sleek Cyber Dark table delegate for media rows, icons, and indicators."""

    def __init__(self, parent=None, accent: str = COLOR_PRIMARY):
        super().__init__(parent)
        self.accent = QColor(COLOR_PRIMARY)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = option.rect
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        col = index.column()

        # Row Background
        if is_selected:
            # Translucent primary accent wash
            painter.fillRect(rect, QColor(99, 102, 241, 44))
            # Subtle top and bottom border
            pen_border = QPen(QColor(99, 102, 241, 90), 1)
            painter.setPen(pen_border)
            painter.drawLine(rect.topLeft(), rect.topRight())
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        elif is_hover:
            painter.fillRect(rect, QColor(255, 255, 255, 9))
            painter.setPen(QPen(QColor(30, 45, 64, 120), 1))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        else:
            painter.setPen(QPen(QColor(30, 45, 64, 120), 1))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        # Accent bar indicator on first column when selected
        if is_selected and col == _COL_INDEX:
            painter.setBrush(QBrush(QColor(COLOR_PRIMARY)))
            painter.setPen(Qt.PenStyle.NoPen)
            indicator = QRectF(rect.x() + 2, rect.y() + 8, 3, rect.height() - 16)
            painter.drawRoundedRect(indicator, 1.5, 1.5)

        # Checkbox column is rendered via cellWidget
        if col == _COL_CHECK:
            pass
        elif col == _COL_PREVIEW:
            ico = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(ico, QIcon) and not ico.isNull():
                thumb_w, thumb_h = 44, 32
                tx = rect.x() + (rect.width() - thumb_w) // 2
                ty = rect.y() + (rect.height() - thumb_h) // 2
                thumb_rect = QRectF(tx, ty, thumb_w, thumb_h)

                clip_path = QPainterPath()
                clip_path.addRoundedRect(thumb_rect, 4, 4)
                painter.save()
                painter.setClipPath(clip_path)
                pix = ico.pixmap(QSize(thumb_w * 2, thumb_h * 2))
                painter.drawPixmap(thumb_rect.toRect(), pix)
                painter.restore()

                painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(thumb_rect, 4, 4)
        else:
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            align = int(index.data(Qt.ItemDataRole.TextAlignmentRole) or (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

            font = painter.font()
            if col == _COL_NAME:
                font.setWeight(QFont.Weight.DemiBold)
                painter.setFont(font)
                color = QColor("#ffffff" if is_selected else COLOR_TEXT_MAIN)
            elif col == _COL_INDEX:
                font.setWeight(QFont.Weight.Bold if is_selected else QFont.Weight.Normal)
                painter.setFont(font)
                color = QColor("#c4b5fd" if is_selected else COLOR_TEXT_MUTED)
            elif col == _COL_TYPE:
                font.setWeight(QFont.Weight.Medium)
                painter.setFont(font)
                color = QColor("#d8b4fe" if is_selected else COLOR_TEXT_SUB)
            else:
                color = QColor("#e2e8f0" if is_selected else COLOR_TEXT_MUTED)

            painter.setPen(color)
            pad_x = 8 if col == _COL_NAME else 4
            text_rect = rect.adjusted(pad_x, 0, -pad_x, 0)
            elided = painter.fontMetrics().elidedText(
                text,
                Qt.TextElideMode.ElideMiddle if col == _COL_NAME else Qt.TextElideMode.ElideRight,
                text_rect.width(),
            )
            painter.drawText(text_rect, align, elided)

        painter.restore()


class _MediaTable(QTableWidget):
    """Columned list: index, batch checkbox, rubber-band select, file drag-out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media_lib_list")
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(["#", "", "", "Name", "Type", "Duration", "Size"])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(48)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setIconSize(QSize(44, 44))
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setItemDelegate(_MediaTableDelegate(self))

        # Drag disabled so click-drag rubber-bands a selection; file DnD is manual.
        self.setDragEnabled(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self._press_pos: QPoint | None = None
        self._press_on_selected = False
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(_COL_INDEX, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_PREVIEW, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_TYPE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_DUR, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_SIZE, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(_COL_INDEX, 28)
        self.setColumnWidth(_COL_CHECK, 28)
        self.setColumnWidth(_COL_PREVIEW, 54)
        self.setColumnWidth(_COL_TYPE, 68)
        self.setColumnWidth(_COL_DUR, 74)
        self.setColumnWidth(_COL_SIZE, 76)

        self.header_check = QCheckBox(header)
        self.header_check.setObjectName("media_lib_row_check")
        self.header_check.setToolTip("Select all")
        self.header_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_check.setTristate(True)
        self.header_check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header.sectionResized.connect(self._place_header_check)
        header.geometriesChanged.connect(self._place_header_check)

    def _place_header_check(self, *_args):
        header = self.horizontalHeader()
        x = header.sectionViewportPosition(_COL_CHECK)
        w = header.sectionSize(_COL_CHECK)
        h = header.height()
        box_w, box_h = 16, 16
        self.header_check.setGeometry(
            x + max(0, (w - box_w) // 2),
            max(0, (h - box_h) // 2),
            box_w,
            box_h,
        )
        self.header_check.show()
        self.header_check.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._place_header_check()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            self._press_pos = pos
            item = self.itemAt(pos)
            self._press_on_selected = bool(item and item.isSelected())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (
            self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and self._press_on_selected
            and self.selectedItems()
        ):
            dist = (event.position().toPoint() - self._press_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._press_pos = None
                self.startDrag(Qt.DropAction.CopyAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._press_pos = None
        self._press_on_selected = False
        super().mouseReleaseEvent(event)

    def mimeData(self, items):
        mime = super().mimeData(items) or QMimeData()
        urls = []
        seen: set[str] = set()
        for item in items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and path not in seen and os.path.isfile(path):
                seen.add(path)
                urls.append(QUrl.fromLocalFile(path))
        if urls:
            mime.setUrls(urls)
        return mime


class _ThumbSignals(QObject):
    ready = Signal(str, object)  # path, QIcon


class _ThumbJob(QRunnable):
    def __init__(self, path: str, size: int, signals: _ThumbSignals):
        super().__init__()
        self.path = path
        self.size = size
        self.signals = signals

    def run(self):
        try:
            ico = icon_for(self.path, size=self.size)
            if not ico.isNull():
                self.signals.ready.emit(self.path, ico)
        except Exception:
            pass


class _DurSignals(QObject):
    ready = Signal(str, float, dict)  # path, seconds, meta dict


class _DurJob(QRunnable):
    def __init__(self, path: str, signals: _DurSignals):
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self):
        try:
            from claynext.adapters.ffmpeg_service import probe_media
            info = probe_media(self.path)
            dur = float(info.get("duration") or 0.0)
            self.signals.ready.emit(self.path, dur, info)
        except Exception:
            try:
                self.signals.ready.emit(self.path, 0.0, {})
            except Exception:
                pass


class _MediaDetailFooter(QFrame):
    """
    Docked interactive command card below the media library list/grid:
    Shows thumbnail preview with quick play, file meta, resolution, duration,
    and action buttons: '+ Add to Timeline', 'Reveal in Folder', and 'Remove'.
    """
    preview_requested = Signal(str)
    localize_requested = Signal()
    reveal_requested = Signal()
    remove_requested = Signal()
    browse_requested = Signal()
    clear_selection_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media_lib_detail_card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(52)

        self._active_path = ""
        self._selected_paths: list[str] = []

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        # Left: Interactive Thumbnail / Poster
        self.thumb_box = QLabel()
        self.thumb_box.setObjectName("media_lib_footer_thumb")
        self.thumb_box.setFixedSize(48, 36)
        self.thumb_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb_box.setToolTip("Click to preview in player")
        self.thumb_box.mousePressEvent = lambda ev: self._on_thumb_click(ev)
        lay.addWidget(self.thumb_box)

        # Center: Info & Meta
        mid = QVBoxLayout()
        mid.setSpacing(2)
        mid.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("media_lib_footer_title")
        title_row.addWidget(self.lbl_title)
        title_row.addStretch(1)
        mid.addLayout(title_row)

        self.meta_row = QHBoxLayout()
        self.meta_row.setSpacing(8)
        self.chip_dur, self.ico_dur, self.lbl_dur = self._meta_chip()
        self.chip_size, self.ico_size, self.lbl_size = self._meta_chip()
        self.chip_res, self.ico_res, self.lbl_res = self._meta_chip()
        self.meta_row.addWidget(self.chip_dur)
        self.meta_row.addWidget(self.chip_size)
        self.meta_row.addWidget(self.chip_res)
        self.meta_row.addStretch(1)
        mid.addLayout(self.meta_row)

        lay.addLayout(mid, 1)

        # Right: Dub + utility actions
        self.btn_localize = QPushButton("Localize")
        self.btn_localize.setObjectName("media_lib_btn_localize")
        self.btn_localize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_localize.setFixedHeight(22)
        self.btn_localize.setIcon(icon("activity", color="#c4b5fd", size=11))
        self.btn_localize.setIconSize(QSize(11, 11))
        self.btn_localize.setToolTip("Start localization for selected movies")
        self.btn_localize.clicked.connect(self.localize_requested.emit)
        lay.addWidget(self.btn_localize)

        self.btn_reveal = QToolButton()
        self.btn_reveal.setObjectName("media_lib_footer_btn")
        self.btn_reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reveal.setFixedSize(22, 22)
        self.btn_reveal.setIcon(icon("folder", color="#94a3b8", size=12))
        self.btn_reveal.setIconSize(QSize(12, 12))
        self.btn_reveal.setToolTip("Show file in Finder / Explorer")
        self.btn_reveal.clicked.connect(self.reveal_requested.emit)
        lay.addWidget(self.btn_reveal)

        self.btn_remove = QToolButton()
        self.btn_remove.setObjectName("media_lib_footer_btn")
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setFixedSize(22, 22)
        self.btn_remove.setIcon(icon("trash", color="#94a3b8", size=12))
        self.btn_remove.setIconSize(QSize(12, 12))
        self.btn_remove.setToolTip("Remove selected from library")
        self.btn_remove.clicked.connect(self.remove_requested.emit)
        lay.addWidget(self.btn_remove)

    def _meta_chip(self) -> tuple[QWidget, QLabel, QLabel]:
        chip = QWidget()
        chip.setObjectName("media_lib_footer_meta_chip")
        row = QHBoxLayout(chip)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        ico = QLabel()
        ico.setObjectName("media_lib_footer_meta_ico")
        ico.setFixedSize(10, 10)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt = QLabel("")
        txt.setObjectName("media_lib_footer_meta")
        row.addWidget(ico, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(txt, 0, Qt.AlignmentFlag.AlignVCenter)
        return chip, ico, txt

    def _set_meta(
        self,
        chip: QWidget,
        ico_lbl: QLabel,
        txt_lbl: QLabel,
        *,
        icon_name: str | None,
        text: str,
        visible: bool = True,
    ):
        if not visible or not text:
            chip.hide()
            return
        if icon_name:
            ico_lbl.setPixmap(icon(icon_name, color="#6b7785", size=10).pixmap(10, 10))
            ico_lbl.show()
        else:
            ico_lbl.clear()
            ico_lbl.hide()
        txt_lbl.setText(text)
        chip.show()

    def _on_thumb_click(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._active_path:
            self.preview_requested.emit(self._active_path)

    def update_state(
        self,
        selected_paths: list[str],
        total_paths: list[str],
        meta_cache: dict[str, dict],
        thumb_cache: dict[str, QIcon],
        dur_cache: dict[str, float],
        fallback_icon_fn,
        format_dur_fn,
        size_label_fn,
    ):
        self._selected_paths = list(selected_paths)
        n_selected = len(selected_paths)

        # Empty selection → hide command card (no overview filler).
        if n_selected == 0:
            self._active_path = ""
            self.hide()
            return

        self.show()

        if n_selected == 1:
            path = selected_paths[0]
            self._active_path = path
            name = os.path.basename(path)

            ico = thumb_cache.get(path) or fallback_icon_fn(path)
            self.thumb_box.clear()
            if isinstance(ico, QIcon) and not ico.isNull():
                self.thumb_box.setPixmap(ico.pixmap(48, 36))
            else:
                self.thumb_box.setPixmap(icon("play", color="#94a3b8", size=14).pixmap(14, 14))
            self.thumb_box.setCursor(Qt.CursorShape.PointingHandCursor)
            self.thumb_box.setToolTip("Click to preview in player")

            self.lbl_title.setText(name)
            self.lbl_title.setToolTip(path)

            dur_sec = dur_cache.get(path, 0.0)
            dur_txt = format_dur_fn(dur_sec) if dur_sec > 0 else "—"
            self._set_meta(self.chip_dur, self.ico_dur, self.lbl_dur, icon_name="clock", text=dur_txt)

            sz_txt = size_label_fn(path)
            self._set_meta(self.chip_size, self.ico_size, self.lbl_size, icon_name="hard-drive", text=sz_txt)

            meta = meta_cache.get(path, {})
            w = meta.get("width")
            h = meta.get("height")
            fps = meta.get("fps")
            if w and h:
                fps_txt = f" · {fps:.0f} fps" if fps else ""
                self._set_meta(
                    self.chip_res, self.ico_res, self.lbl_res,
                    icon_name="video", text=f"{w}×{h}{fps_txt}",
                )
            else:
                self.chip_res.hide()

            is_video = os.path.splitext(path)[1].lower() in VIDEO_EXTS
            self.btn_localize.setText("Localize")
            self.btn_localize.setEnabled(is_video)
            self.btn_localize.setToolTip(
                "Start localization for this movie" if is_video else "Select a video to localize"
            )

            self.btn_reveal.show()
            self.btn_remove.show()

        else:
            self._active_path = selected_paths[-1]
            total_bytes = 0
            video_count = 0
            for p in selected_paths:
                try:
                    total_bytes += os.path.getsize(p)
                except OSError:
                    pass
                if os.path.splitext(p)[1].lower() in VIDEO_EXTS:
                    video_count += 1
            sz_txt = size_label_fn(total_bytes) if callable(size_label_fn) else "—"

            ico = icon("check_on", color=COLOR_PRIMARY, size=24)
            self.thumb_box.setPixmap(ico.pixmap(32, 32))
            self.thumb_box.setCursor(Qt.CursorShape.ArrowCursor)
            self.thumb_box.setToolTip("")

            self.lbl_title.setText(f"{n_selected} items selected")
            self._set_meta(
                self.chip_dur, self.ico_dur, self.lbl_dur,
                icon_name="list", text=f"{n_selected} clips",
            )
            self._set_meta(
                self.chip_size, self.ico_size, self.lbl_size,
                icon_name="hard-drive", text=f"Total {sz_txt}",
            )
            self.chip_res.hide()

            self.btn_localize.setText(
                f"Localize · {video_count}" if video_count > 1 else "Localize"
            )
            self.btn_localize.setEnabled(video_count > 0)
            self.btn_localize.setToolTip(
                f"Start localization for {video_count} movie(s)"
                if video_count
                else "Select a video to localize"
            )

            self.btn_reveal.show()
            self.btn_remove.show()

class MediaLibraryWidget(QWidget):
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

    def _active_view(self) -> QWidget:
        return self.grid_view if self._view_mode == "grid" else self.list_view

    def _kind_for(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            return "Video"
        if ext in self.AUDIO_EXTS:
            return "Audio"
        if ext in IMAGE_EXTS:
            return "Image"
        return "Media"

    def paths(self) -> list[str]:
        return list(self._paths)

    def set_paths(self, paths: list[str], *, select: str | None = None, quiet: bool = False):
        seen: list[str] = []
        for path in paths:
            abs_path = os.path.abspath(path)
            if abs_path in seen or not os.path.isfile(abs_path):
                continue
            ext = os.path.splitext(abs_path)[1].lower()
            if ext not in self.MEDIA_EXTS:
                continue
            seen.append(abs_path)
        self._paths = seen
        self._refresh_items()
        self._apply_view_mode()
        self._update_count()
        if not quiet:
            self.files_changed.emit(len(self._paths))
        target = None
        if select and select in self._paths:
            target = select
        elif self._paths:
            target = self._paths[0]
        if target:
            self.select_path(target)

    def add_files(self, paths: list[str], *, select_last: bool = True):
        added = []
        for path in paths:
            if not path:
                continue
            abs_path = os.path.abspath(path)
            ext = os.path.splitext(abs_path)[1].lower()
            if ext not in self.MEDIA_EXTS:
                continue
            if abs_path in self._paths:
                continue
            if not os.path.isfile(abs_path):
                continue
            self._paths.append(abs_path)
            added.append(abs_path)

        if not added:
            return

        self._refresh_items()
        self._apply_view_mode()
        self._update_count()
        self.files_changed.emit(len(self._paths))
        self.status_message.emit(f"Added {len(added)} media file(s)")

        if select_last:
            self.select_paths(added)

    def browse_add(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Media Files",
            "",
            "Media Files (*.mp4 *.mkv *.avi *.mov *.webm *.mp3 *.wav *.flac *.png *.jpg *.jpeg *.webp *.gif);;All Files (*.*)",
        )
        if paths:
            self.add_files(paths)

    def remove_selected(self):
        view = self._active_view()
        selected = [item.data(Qt.ItemDataRole.UserRole) for item in view.selectedItems()]
        selected = [p for p in selected if p]
        if not selected:
            self.status_message.emit("No media selected to remove")
            return
        self._paths = [p for p in self._paths if p not in selected]
        for p in selected:
            self._thumb_cache.pop(p, None)
            self._meta_cache.pop(p, None)
            self._dur_cache.pop(p, None)
        self._refresh_items()
        self._apply_view_mode()
        self._update_count()
        self.files_changed.emit(len(self._paths))
        self.status_message.emit(f"Removed {len(selected)} file(s)")
        if not self._paths:
            self.file_selected.emit("")

    def clear_all(self):
        if not self._paths:
            return
        n = len(self._paths)
        self._paths.clear()
        self._thumb_cache.clear()
        self._meta_cache.clear()
        self._dur_cache.clear()
        self.list_view.setRowCount(0)
        self.grid_view.clear()
        self._apply_view_mode()
        self._update_count()
        self.files_changed.emit(0)
        self.status_message.emit(f"Cleared {n} file(s)")
        self.file_selected.emit("")

    def reveal_selected(self):
        view = self._active_view()
        items = view.selectedItems()
        path = items[-1].data(Qt.ItemDataRole.UserRole) if items else None
        if not path or not os.path.exists(path):
            self.status_message.emit("Nothing to reveal")
            return
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", path], check=False)
            elif sys.platform.startswith("win"):
                subprocess.run(["explorer", "/select,", os.path.normpath(path)], check=False)
            else:
                subprocess.run(["xdg-open", os.path.dirname(path)], check=False)
        except Exception:
            self.status_message.emit("Could not reveal file")

    def selected_paths(self) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        if self._view_mode == "grid":
            items = self.grid_view.selectedItems()
        else:
            items = self.list_view.selectedItems()
        for item in items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
        return paths

    def clear_selection(self):
        for view in (self.list_view, self.grid_view):
            view.blockSignals(True)
            view.clearSelection()
            view.blockSignals(False)
        self._sync_row_checks()
        self._update_detail_footer()

    def select_path(self, path: str):
        self.select_paths([path])

    def select_paths(self, paths: list[str]):
        wanted = []
        for path in paths:
            if path and path not in wanted:
                wanted.append(path)
        wanted_set = set(wanted)
        primary = wanted[-1] if wanted else ""

        self.grid_view.blockSignals(True)
        self.grid_view.clearSelection()
        current_grid = None
        for i in range(self.grid_view.count()):
            item = self.grid_view.item(i)
            item_path = item.data(Qt.ItemDataRole.UserRole) if item else None
            if item and item_path in wanted_set:
                item.setSelected(True)
                if item_path == primary:
                    current_grid = item
        if current_grid is not None:
            self.grid_view.setCurrentItem(current_grid, QItemSelectionModel.SelectionFlag.NoUpdate)
            current_grid.setSelected(True)
        self.grid_view.blockSignals(False)

        rows: list[int] = []
        primary_row: int | None = None
        for row in range(self.list_view.rowCount()):
            cell = self.list_view.item(row, _COL_INDEX)
            path = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if path in wanted_set:
                rows.append(row)
                if path == primary:
                    primary_row = row
        self._select_list_rows(rows, primary_row=primary_row)
        self._sync_row_checks()
        self._update_detail_footer()

        self._had_selection = bool(primary)
        if primary:
            self.file_selected.emit(primary)

    def _fallback_icon(self, path: str) -> QIcon:
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            return icon("video", color="#38bdf8", size=32)
        if ext in self.AUDIO_EXTS:
            return icon("volume", color="#a855f7", size=32)
        if ext in IMAGE_EXTS:
            return icon("grid", color="#a78bfa", size=32)
        return icon("folder", color="#94a3b8", size=32)

    def _refresh_items(self):
        selected = set(self.selected_paths())

        self.list_view.blockSignals(True)
        self.grid_view.blockSignals(True)
        self.list_view.setRowCount(0)
        self.grid_view.clear()

        muted = QBrush(QColor(COLOR_TEXT_MUTED))
        sub = QBrush(QColor(COLOR_TEXT_SUB))

        for path in self._visible_paths():
            name = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower()
            kind = self._kind_for(path)
            size_txt = self._size_label(path)
            dur_txt = self._duration_label(path)
            ico = self._thumb_cache.get(path) or self._fallback_icon(path)
            checked = path in selected

            row = self.list_view.rowCount()
            self.list_view.insertRow(row)

            index_item = QTableWidgetItem(str(row + 1))
            index_item.setData(Qt.ItemDataRole.UserRole, path)
            index_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            index_item.setForeground(muted)
            self.list_view.setItem(row, _COL_INDEX, index_item)

            check_item = QTableWidgetItem()
            check_item.setData(Qt.ItemDataRole.UserRole, path)
            check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.list_view.setItem(row, _COL_CHECK, check_item)
            self.list_view.setCellWidget(
                row, _COL_CHECK, self._make_row_check(path, checked)
            )

            preview = QTableWidgetItem()
            preview.setIcon(ico)
            preview.setData(Qt.ItemDataRole.UserRole, path)
            preview.setToolTip(path)
            preview.setFlags(preview.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.list_view.setItem(row, _COL_PREVIEW, preview)

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            name_item.setToolTip(path)
            self.list_view.setItem(row, _COL_NAME, name_item)

            type_item = QTableWidgetItem(kind)
            type_item.setData(Qt.ItemDataRole.UserRole, path)
            type_item.setForeground(sub)
            self.list_view.setItem(row, _COL_TYPE, type_item)

            dur_item = QTableWidgetItem(dur_txt)
            dur_item.setData(Qt.ItemDataRole.UserRole, path)
            dur_item.setForeground(muted)
            self.list_view.setItem(row, _COL_DUR, dur_item)

            size_item = QTableWidgetItem(size_txt)
            size_item.setData(Qt.ItemDataRole.UserRole, path)
            size_item.setForeground(muted)
            self.list_view.setItem(row, _COL_SIZE, size_item)

            tip_dur = f" · {dur_txt}" if dur_txt != "—" else ""
            grid_item = QListWidgetItem(ico, name)
            grid_item.setData(Qt.ItemDataRole.UserRole, path)
            grid_item.setToolTip(f"{name}\n{kind}{tip_dur} · {size_txt}\n{path}")
            grid_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.grid_view.addItem(grid_item)
            if checked:
                grid_item.setSelected(True)

            if ext in VIDEO_EXTS | IMAGE_EXTS and path not in self._thumb_cache:
                self._thumb_pool.start(_ThumbJob(path, 96, self._thumb_signals))
            if kind in ("Video", "Audio") and path not in self._dur_cache:
                self._thumb_pool.start(_DurJob(path, self._dur_signals))

        restore_rows = [
            r for r in range(self.list_view.rowCount())
            if (self.list_view.item(r, _COL_INDEX) or QTableWidgetItem()).data(
                Qt.ItemDataRole.UserRole
            ) in selected
        ]
        self._select_list_rows(restore_rows)
        self.list_view.blockSignals(False)
        self.grid_view.blockSignals(False)
        self._update_header_check()
        self._update_detail_footer()

    def _on_thumb_ready(self, path: str, ico: object):
        if path not in self._paths or not isinstance(ico, QIcon) or ico.isNull():
            return
        self._thumb_cache[path] = ico
        for row in range(self.list_view.rowCount()):
            cell = self.list_view.item(row, _COL_PREVIEW)
            if cell and cell.data(Qt.ItemDataRole.UserRole) == path:
                cell.setIcon(ico)
                break
        for i in range(self.grid_view.count()):
            item = self.grid_view.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                item.setIcon(ico)
                break
        self._update_detail_footer()

    def _on_duration_ready(self, path: str, seconds: float, info: dict | None = None):
        if path not in self._paths:
            return
        self._dur_cache[path] = max(0.0, float(seconds or 0.0))
        if info:
            self._meta_cache[path] = info
        label = self._format_duration(self._dur_cache[path])
        for row in range(self.list_view.rowCount()):
            cell = self.list_view.item(row, _COL_DUR)
            if cell and cell.data(Qt.ItemDataRole.UserRole) == path:
                cell.setText(label if self._dur_cache[path] > 0 else "—")
                break
        self._update_detail_footer()

    def _duration_label(self, path: str) -> str:
        kind = self._kind_for(path)
        if kind not in ("Video", "Audio"):
            return "—"
        if path not in self._dur_cache:
            return "…"
        secs = self._dur_cache[path]
        return self._format_duration(secs) if secs > 0 else "—"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = max(0, int(round(seconds)))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @classmethod
    def _size_label(cls, path_or_bytes: str | int | float) -> str:
        if isinstance(path_or_bytes, (int, float)):
            return cls._format_bytes(float(path_or_bytes))
        try:
            size = os.path.getsize(str(path_or_bytes))
            return cls._format_bytes(float(size))
        except OSError:
            return "—"

    @staticmethod
    def _format_bytes(size: float) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return "—"

    def _make_row_check(self, path: str, checked: bool) -> QWidget:
        """Tight centered checkbox widget for the trim check column."""
        wrap = QWidget()
        wrap.setObjectName("media_lib_check_wrap")
        wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box = QCheckBox()
        box.setObjectName("media_lib_row_check")
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        box.setChecked(checked)
        box.setProperty("media_path", path)
        box.stateChanged.connect(lambda state, p=path: self._on_row_check(p, state))
        lay.addWidget(box)
        return wrap

    def _row_check_at(self, row: int) -> QCheckBox | None:
        wrap = self.list_view.cellWidget(row, _COL_CHECK)
        if wrap is None:
            return None
        return wrap.findChild(QCheckBox, "media_lib_row_check")

    def _list_selected_paths(self) -> set[str]:
        selected: set[str] = set()
        for item in self.list_view.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                selected.add(path)
        return selected

    def _select_list_rows(self, rows: list[int], *, primary_row: int | None = None):
        """Select many rows without clear-on-each-selectRow."""
        self.list_view.blockSignals(True)
        model = self.list_view.model()
        sel_model = self.list_view.selectionModel()
        if not rows:
            sel_model.clearSelection()
            self.list_view.blockSignals(False)
            return
        selection = QItemSelection()
        last_col = self.list_view.columnCount() - 1
        for row in rows:
            left = model.index(row, 0)
            right = model.index(row, last_col)
            selection.select(left, right)
        sel_model.select(
            selection,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        focus = primary_row if primary_row is not None else rows[-1]
        sel_model.setCurrentIndex(
            model.index(focus, _COL_NAME),
            QItemSelectionModel.SelectionFlag.NoUpdate,
        )
        self.list_view.blockSignals(False)

    def _sync_row_checks(self):
        selected = self._list_selected_paths() if self._view_mode == "list" else set()
        self._syncing_checks = True
        for row in range(self.list_view.rowCount()):
            box = self._row_check_at(row)
            cell = self.list_view.item(row, _COL_CHECK)
            if not box or not cell:
                continue
            path = cell.data(Qt.ItemDataRole.UserRole)
            box.blockSignals(True)
            box.setChecked(path in selected)
            box.blockSignals(False)
        self._syncing_checks = False
        self._update_header_check()

    def _update_header_check(self):
        rows = self.list_view.rowCount()
        hdr = self.list_view.header_check
        hdr.blockSignals(True)
        if rows <= 0:
            hdr.setCheckState(Qt.CheckState.Unchecked)
            hdr.blockSignals(False)
            return
        n_checked = 0
        for r in range(rows):
            box = self._row_check_at(r)
            if box and box.isChecked():
                n_checked += 1
        if n_checked == 0:
            hdr.setCheckState(Qt.CheckState.Unchecked)
        elif n_checked == rows:
            hdr.setCheckState(Qt.CheckState.Checked)
        else:
            hdr.setCheckState(Qt.CheckState.PartiallyChecked)
        hdr.blockSignals(False)

    def _on_header_check(self, _checked: bool = False):
        rows = self.list_view.rowCount()
        if rows <= 0:
            return
        all_on = all(
            (box := self._row_check_at(r)) is not None and box.isChecked()
            for r in range(rows)
        )
        select_all = not all_on

        self._syncing_checks = True
        for row in range(rows):
            box = self._row_check_at(row)
            if not box:
                continue
            box.blockSignals(True)
            box.setChecked(select_all)
            box.blockSignals(False)
        self._syncing_checks = False

        self._select_list_rows(list(range(rows)) if select_all else [])
        self._update_header_check()
        self._on_selection()

    def _on_row_check(self, path: str, state: int):
        if self._syncing_checks or not path:
            return
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        selected = self._list_selected_paths()
        if checked:
            selected.add(path)
        else:
            selected.discard(path)
        rows = [
            r for r in range(self.list_view.rowCount())
            if (self.list_view.item(r, _COL_INDEX) or QTableWidgetItem()).data(
                Qt.ItemDataRole.UserRole
            ) in selected
        ]
        self._select_list_rows(rows)
        self._update_header_check()
        self._on_selection()

    def _on_selection(self):
        if self._view_mode == "list":
            self._sync_row_checks()
        self._update_detail_footer()
        paths = self.selected_paths()
        if not paths:
            if self._had_selection:
                self._had_selection = False
                self.selection_cleared.emit()
            return
        self._had_selection = True
        self.file_selected.emit(paths[-1])

    def _on_footer_preview(self, path: str):
        if path:
            self.file_selected.emit(path)

    def _on_activate(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.file_selected.emit(path)

    def _on_table_activate(self, row: int, _column: int):
        cell = self.list_view.item(row, _COL_INDEX)
        path = cell.data(Qt.ItemDataRole.UserRole) if cell else None
        if path:
            self.file_selected.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        expanded = []
        for p in paths:
            if os.path.isdir(p):
                for name in os.listdir(p):
                    fp = os.path.join(p, name)
                    if os.path.isfile(fp):
                        expanded.append(fp)
            else:
                expanded.append(p)
        self.add_files(expanded)
        event.acceptProposedAction()

