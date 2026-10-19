"""Add, edit, and remove overlays, plus the selection tool menu."""
from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu

from claynext.constants.theme_constants import COLOR_TEXT_MAIN
from claynext.gui.components.overlay.const import HANDLE_KINDS, MEDIA_KINDS
from claynext.gui.components.overlay.item import OverlayItem, default_item
from claynext.gui.icons import icon

class CanvasItems:
    def _commit(self, item: OverlayItem):
        self.update()
        self.item_edited.emit(item)
        self.items_changed.emit()

    def _toggle_flip(self, item: OverlayItem, axis: str):
        if axis == "h":
            item.flip_h = not item.flip_h
        else:
            item.flip_v = not item.flip_v
        self._commit(item)

    def _toggle_hidden(self, item: OverlayItem):
        item.hidden = not item.hidden
        self._commit(item)

    def _toggle_lock(self, item: OverlayItem):
        item.lock_aspect = not item.lock_aspect
        self._commit(item)

    def _center_item(self, item: OverlayItem):
        item.x = 0.5
        item.y = 0.5
        self._commit(item)

    def _reset_item(self, item: OverlayItem):
        item.x = 0.5
        item.y = 0.5
        item.rotation = 0.0
        item.opacity = 100
        item.flip_h = False
        item.flip_v = False
        self._commit(item)

    def _request_delete(self):
        self.command.emit("delete")

    def _open_tools_menu(self, item: OverlayItem, global_pos: QPoint):
        menu = QMenu(self)

        def act(label: str, slot, *, icon_name: str = "", checked: bool | None = None, color: str = COLOR_TEXT_MAIN):
            action = menu.addAction(icon(icon_name, color=color, size=13), label) if icon_name else menu.addAction(label)
            if checked is not None:
                action.setCheckable(True)
                action.setChecked(checked)
            action.triggered.connect(lambda *_args, fn=slot: fn())
            return action

        act("Flip Horizontal", lambda: self._toggle_flip(item, "h"), checked=item.flip_h)
        act("Flip Vertical", lambda: self._toggle_flip(item, "v"), checked=item.flip_v)
        menu.addSeparator()
        if item.kind in MEDIA_KINDS | {"shape", "mask"}:
            act(
                "Lock Aspect Ratio",
                lambda: self._toggle_lock(item),
                icon_name="lock" if item.lock_aspect else "unlock",
                checked=item.lock_aspect,
            )
        act("Center", lambda: self._center_item(item), icon_name="align-center")
        act("Reset Transform", lambda: self._reset_item(item), icon_name="refresh")
        menu.addSeparator()
        act("Duplicate", lambda: self.command.emit("duplicate"), icon_name="copy")
        act("Delete", self._request_delete, icon_name="trash", color="#f87171")
        menu.popup(global_pos)

    def _run_tool(self, item: OverlayItem, name: str, global_pos: QPoint):
        if name == "delete":
            self._request_delete()
        elif name == "eye":
            self._toggle_hidden(item)
        elif name == "more":
            rect = self._toolbar_rects(item).get("more")
            if rect is not None:
                global_pos = self.mapToGlobal(rect.bottomLeft().toPoint()) + QPoint(0, 4)
            self._open_tools_menu(item, global_pos)

    def _open_item_menu(self, event):
        pos = event.position()
        item = self._item_at(pos.toPoint()) if self._in_content(pos) else None
        picked = self.selected_item()
        on_chrome = False
        if picked is not None and picked.kind in HANDLE_KINDS:
            on_chrome = bool(self._tool_at(picked, pos) or self._text_handle_at(picked, pos))
        if item is None and on_chrome:
            item = picked
        if item is None:
            return
        if item.id != self.selected_id:
            self.selected_id = item.id
            self.item_selected.emit(item)
            self.update()
        self._open_tools_menu(item, event.globalPosition().toPoint())

    def set_items(self, rows: list[dict] | list[OverlayItem]):
        parsed = []
        for row in rows or []:
            parsed.append(row if isinstance(row, OverlayItem) else OverlayItem.from_dict(row))
        prev = self.selected_id
        self.items = parsed
        # Keep selection if the item still exists; never auto-pick the first overlay
        # (that was stealing focus to Text properties during playhead sync).
        if not any(it.id == self.selected_id for it in parsed):
            self.selected_id = ""
        self.update()
        self.items_changed.emit()
        # Only notify when the selected item identity actually changed.
        if self.selected_id != prev:
            self.item_selected.emit(self.selected_item())

    def dumps(self) -> list[dict]:
        return [it.to_dict() for it in self.items]

    def selected_item(self) -> OverlayItem | None:
        return next((it for it in self.items if it.id == self.selected_id), None)

    def add_item(self, kind: str, **kwargs) -> OverlayItem:
        item = default_item(kind)
        for k, v in kwargs.items():
            if hasattr(item, k):
                setattr(item, k, v)
        self.items.append(item)
        self.selected_id = item.id
        self.update()
        self.items_changed.emit()
        self.item_selected.emit(item)
        return item

    def remove_selected(self):
        self.items = [it for it in self.items if it.id != self.selected_id]
        self.selected_id = self.items[-1].id if self.items else ""
        self.update()
        self.items_changed.emit()
        self.item_selected.emit(self.selected_item())

    def update_selected(self, **fields):
        item = self.selected_item()
        if not item:
            return
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
        self.update()
        self.items_changed.emit()

    def set_live_caption(self, text: str, start_ms: int = 0, end_ms: int = 0, has_lines: bool = False):
        """The dubbed line under the playhead and its span, so live captions animate per line.
        Without any dubbed lines a live caption shows its own text as a placeholder."""
        state = (text or "", (int(start_ms), int(end_ms)), bool(has_lines))
        if state == (self._live_caption, self._live_span, self._live_has_lines):
            return
        self._live_caption, self._live_span, self._live_has_lines = state
        self.update()
