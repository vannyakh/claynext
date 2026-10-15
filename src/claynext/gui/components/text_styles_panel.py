"""Text template grid: drag or add a styled text onto the timeline and preview."""
from __future__ import annotations

from functools import lru_cache
import json

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QDrag, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from claynext.models.text_style import anim_frame, clean_text_style, is_animated, preset_values
from claynext.gui.components.shelf_header import make_shelf_header
from claynext.gui.components.text_render import template_pixmap

TEXT_STYLE_MIME = "application/x-minj-text-style"
TILE = QSize(106, 62)

CATEGORIES: list[tuple[str, str]] = [
    ("all", "All"),
    ("titles", "Titles"),
    ("captions", "Captions"),
    ("motion", "Motion"),
    ("badges", "Badges"),
]


def _style(
    name: str,
    text: str,
    kind: str = "text",
    y: float = 0.5,
    size: int = 20,
    preset: str = "none",
    category: str = "titles",
    display_label: str = "",
    **extra,
) -> dict:
    out = {
        "name": name,
        "display_label": display_label or name,
        "kind": kind,
        "text": text,
        "x": 0.5,
        "y": y,
        "w": 0.6,
        "h": 0.12,
        "font_size": size,
        "opacity": 100,
        "rotation": 0,
        "live": False,
        "bold": True,
        "preset": "" if preset == "none" else preset,
        "category": category,
    }
    out.update(preset_values(preset))
    out.update(extra)
    return out


TEXT_STYLES: list[dict] = [
    _style("Default text", "Default text", bold=False, category="titles"),
    _style("Title", "Title", y=0.38, size=32, color="#fbbf24", stroke_on=True, stroke_color="#1c1917", stroke_width=2, category="titles"),
    _style("Subtitle", "Subtitle", y=0.84, size=18, preset="outline_black", category="captions"),
    _style("Yellow subtitle", "Subtitle", y=0.84, size=18, preset="yellow_outline", category="captions"),
    _style("Boxed caption", "Caption", kind="caption", y=0.86, size=16, preset="box_dark", bold=False, category="captions", display_label="Boxed Caption"),
    _style(
        "Live caption",
        "LIVE",
        kind="caption",
        y=0.86,
        size=16,
        preset="box_dark",
        bold=False,
        live=True,
        caption_fit=True,
        caption_width=80,
        category="captions",
        display_label="Live Caption",
    ),
    _style(
        "Word karaoke",
        "Sing Along",
        kind="caption",
        y=0.86,
        size=18,
        preset="outline_black",
        bold=False,
        live=True,
        anim_in="words",
        highlight_color="#facc15",
        caption_fit=True,
        caption_width=82,
        category="motion",
        display_label="Word Karaoke",
    ),
    _style(
        "Highlight caption",
        "Karaoke Glow",
        kind="caption",
        y=0.86,
        size=18,
        preset="box_dark",
        bold=False,
        live=True,
        anim_in="highlight",
        highlight_color="#22c55e",
        caption_fit=True,
        caption_width=82,
        category="motion",
        display_label="Karaoke Glow",
    ),
    _style("Lower third", "Lower Third", kind="caption", y=0.82, size=16, preset="box_white", x=0.3, align="left", category="captions", display_label="Lower Third"),
    _style("Credit", "Credit", y=0.9, size=13, color="#cbd5e1", bold=False, opacity=90, category="titles"),
    _style("Bold outline", "BOLD", size=34, preset="outline_heavy", case="upper", category="titles"),
    _style("Gold pop", "WOW", size=36, preset="gold_outline", anim_in="pop", anim_out="fade", category="motion", display_label="Gold Pop"),
    _style("Neon pink", "Neon", size=30, preset="pink_outline", shadow_on=True, shadow_color="#be185d", category="titles", display_label="Neon Pink"),
    _style("Mint glow", "Fresh", size=30, preset="mint_shadow", category="titles", display_label="Mint Glow"),
    _style("Purple tag", "Breaking", size=22, preset="box_purple", anim_in="slide_left", anim_out="slide_right", category="badges", display_label="Purple Tag"),
    _style("Typewriter", "Typing...", size=22, preset="outline_black", bold=False, anim_in="typewriter", anim_in_ms=1500, category="motion"),
    _style("Fade title", "Fade In", size=26, preset="shadow", anim_in="fade", anim_out="fade", anim_in_ms=800, anim_out_ms=800, category="motion", display_label="Fade Title"),
    _style("Rise", "Rise up", size=26, preset="outline_black", anim_in="slide_up", anim_out="fade", category="motion"),
    _style("Pulse", "Live", size=26, preset="red_outline", anim_loop="pulse", category="badges"),
    _style("Float", "Dream", size=26, preset="cream_shadow", italic=True, anim_loop="float", category="motion"),
]


def parse_text_style(mime: QMimeData | None) -> dict | None:
    if mime is None or not mime.hasFormat(TEXT_STYLE_MIME):
        return None
    try:
        return json.loads(bytes(mime.data(TEXT_STYLE_MIME)).decode("utf-8"))
    except Exception:
        return None


@lru_cache(maxsize=64)
def text_tile_poster(style_name: str) -> QIcon:
    style = next((s for s in TEXT_STYLES if s["name"] == style_name), None)
    if not style:
        return QIcon()
    pm = template_pixmap(style, style["text"], TILE.width(), TILE.height())
    return QIcon(pm)


@lru_cache(maxsize=256)
def text_tile_frame(style_name: str, step: int) -> QIcon:
    style = next((s for s in TEXT_STYLES if s["name"] == style_name), None)
    if not style:
        return QIcon()
    s = clean_text_style(style)
    dur = 1600
    t = int((step % 8) / 7.0 * dur)
    fr = anim_frame(s, t, dur)
    pm = template_pixmap(s, s["text"], TILE.width(), TILE.height(), frame=fr)
    return QIcon(pm)


class StyleList(QListWidget):
    """Shelf list supporting drag-and-drop plus interactive hover loops for animated styles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._hover_item: QListWidgetItem | None = None
        self._hover_frame = 0
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(125)
        self._hover_timer.timeout.connect(self._on_hover_tick)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        item = self.itemAt(event.pos())
        if item is not self._hover_item:
            self._stop_hover()
            if item is not None:
                style = item.data(Qt.ItemDataRole.UserRole)
                if style and is_animated(style):
                    self._hover_item = item
                    self._hover_frame = 0
                    self._hover_timer.start()

    def leaveEvent(self, event):
        self._stop_hover()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._stop_hover()
        super().hideEvent(event)

    def startDrag(self, supported):
        self._stop_hover()
        item = self.currentItem()
        if not item:
            return
        style = item.data(Qt.ItemDataRole.UserRole) or {}
        mime = QMimeData()
        mime.setData(TEXT_STYLE_MIME, QByteArray(json.dumps(style).encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(item.icon().pixmap(TILE))
        drag.exec(Qt.DropAction.CopyAction)

    def _stop_hover(self):
        self._hover_timer.stop()
        if self._hover_item is not None:
            style = self._hover_item.data(Qt.ItemDataRole.UserRole)
            if style:
                self._hover_item.setIcon(text_tile_poster(style["name"]))
            self._hover_item = None
            self._hover_frame = 0

    def _on_hover_tick(self):
        if self._hover_item is None:
            self._hover_timer.stop()
            return
        style = self._hover_item.data(Qt.ItemDataRole.UserRole)
        if not style:
            self._stop_hover()
            return
        self._hover_frame = (self._hover_frame + 1) % 8
        self._hover_item.setIcon(text_tile_frame(style["name"], self._hover_frame))


class TextStylesPanel(QWidget):
    add_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("text_styles_panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._active_category = "all"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(make_shelf_header("Text"))

        body = QWidget()
        body.setObjectName("text_styles_body")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self.search = QLineEdit()
        self.search.setObjectName("dub_setting_field")
        self.search.setPlaceholderText("Search text styles…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        # Quick category filter pills
        pill_row = QHBoxLayout()
        pill_row.setContentsMargins(0, 0, 0, 0)
        pill_row.setSpacing(6)
        self.pill_group = QButtonGroup(self)
        self.pill_group.setExclusive(True)

        for idx, (cat_id, cat_label) in enumerate(CATEGORIES):
            btn = QPushButton(cat_label)
            btn.setObjectName("text_cat_pill")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if idx == 0:
                btn.setChecked(True)
            self.pill_group.addButton(btn, idx)
            pill_row.addWidget(btn)
            btn.clicked.connect(lambda _, c=cat_id: self._set_category(c))

        pill_row.addStretch(1)
        lay.addLayout(pill_row)

        self.list = StyleList()
        self.list.setObjectName("text_style_list")
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(TILE)
        self.list.setGridSize(QSize(TILE.width() + 10, TILE.height() + 32))
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.setDragEnabled(True)
        self.list.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.list.itemDoubleClicked.connect(self._emit_current)

        for style in TEXT_STYLES:
            label = style.get("display_label", style["name"])
            item = QListWidgetItem(text_tile_poster(style["name"]), label)
            item.setData(Qt.ItemDataRole.UserRole, style)
            item.setToolTip(f"{style['name']} · double-click or drag onto timeline")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.list.addItem(item)

        self.list.setCurrentRow(0)
        lay.addWidget(self.list, 1)
        outer.addWidget(body, 1)

    def _set_category(self, cat: str):
        self._active_category = cat
        self._apply_filter()

    def _filter(self, _=None):
        self._apply_filter()

    def _apply_filter(self):
        query = self.search.text().strip().lower()
        cat = self._active_category
        for i in range(self.list.count()):
            item = self.list.item(i)
            style = item.data(Qt.ItemDataRole.UserRole) or {}

            # Category matching
            item_cat = style.get("category", "titles")
            if cat == "all":
                cat_match = True
            elif cat == "motion":
                cat_match = is_animated(style)
            elif cat == "badges":
                cat_match = item_cat == "badges" or "tag" in style["name"].lower()
            else:
                cat_match = item_cat == cat

            # Search text matching
            text_match = (
                (not query)
                or (query in item.text().lower())
                or (query in style.get("name", "").lower())
                or (query in style.get("text", "").lower())
            )

            item.setHidden(not (cat_match and text_match))

    def _emit_current(self, *_):
        item = self.list.currentItem()
        if not item:
            return
        style = item.data(Qt.ItemDataRole.UserRole)
        if style:
            self.add_requested.emit(dict(style))
