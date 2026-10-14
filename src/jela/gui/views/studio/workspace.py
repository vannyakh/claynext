"""Dock layout, window menus, and workspace lifecycle."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, QByteArray, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMenu, QMenuBar, QApplication, QLineEdit, QAbstractSpinBox, QComboBox,
    QPlainTextEdit, QTextEdit,
)

from jela.core.dub_project import list_presets
from jela.gui.views.studio.constants import LAYOUT_META_KEY, SETTINGS_KEY

_PANEL_KEYS = ("shelf", "preview", "props", "log")


class WorkspaceTools:
    """Panels menu, dock persistence, and playback shutdown."""

    def _build_panels_menu(self) -> QMenu:
        menu = QMenu(self)
        self._panel_actions: dict[str, QAction] = {}
        for key, label, default_on in (
            ("shelf", "Studio Library & Setup", True),
            ("preview", "Video Preview", True),
            ("props", "Properties", True),
            ("log", "Activity Log", False),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(default_on)
            act.toggled.connect(lambda checked, k=key: self.workspace.set_visible(k, checked))
            menu.addAction(act)
            self._panel_actions[key] = act
        self._panels_menu = menu
        return menu

    def install_window_menus(self, menu_bar: QMenuBar):
        file_menu = None
        view_menu = None
        tools_menu = None
        for action in menu_bar.actions():
            menu = action.menu()
            if not menu:
                continue
            title = menu.title().replace("&", "").lower()
            if title == "file":
                file_menu = menu
            elif title == "view":
                view_menu = menu
            elif title == "tools":
                tools_menu = menu
        if file_menu:
            act_add = QAction("Add &Media…", self)
            act_add.setShortcut(QKeySequence("Ctrl+O"))
            act_add.triggered.connect(self.browse_media)
            file_menu.insertAction(file_menu.actions()[0] if file_menu.actions() else None, act_add)
            self.act_open_out = QAction("Open &dubbed file", self)
            self.act_open_out.setEnabled(False)
            self.act_open_out.triggered.connect(self.open_output)
            file_menu.insertAction(file_menu.actions()[1] if len(file_menu.actions()) > 1 else None, self.act_open_out)
            act_export = QAction("&Export…", self)
            act_export.setShortcut(QKeySequence("Ctrl+E"))
            act_export.triggered.connect(lambda: self.open_export_dialog())
            file_menu.insertAction(file_menu.actions()[2] if len(file_menu.actions()) > 2 else None, act_export)

        # Studio tools for this workspace — not launcher tool switching.
        if tools_menu is not None:
            tools_menu.clear()
            self.act_dub = QAction("Start &Dubbing…", self)
            self.act_dub.setShortcut(QKeySequence("Ctrl+Return"))
            self.act_dub.triggered.connect(self.start_dubbing)
            tools_menu.addAction(self.act_dub)
            tools_menu.addSeparator()

            act_bed = QAction("Rebuild music/effects &bed", self)
            act_bed.setShortcut(QKeySequence("Ctrl+Shift+B"))
            act_bed.triggered.connect(self.rebuild_speech_bed)
            tools_menu.addAction(act_bed)

            act_mix = QAction("&Auto mix · speech to bed", self)
            act_mix.setShortcut(QKeySequence("Ctrl+Shift+M"))
            act_mix.triggered.connect(self.run_studio_auto_mix)
            tools_menu.addAction(act_mix)

            tools_menu.addSeparator()
            tmpl = tools_menu.addMenu("Apply &template")
            for row in list_presets():
                act = QAction(row["name"], self)
                act.triggered.connect(lambda _=False, p=row["path"]: self._apply_template(p))
                tmpl.addAction(act)
            act_preset = QAction("Save overlay &preset…", self)
            act_preset.triggered.connect(self._save_overlay_preset)
            tools_menu.addAction(act_preset)

            tools_menu.addSeparator()
            act_features = QAction("Feature &settings…", self)
            act_features.triggered.connect(self._open_feature_settings)
            tools_menu.addAction(act_features)
        else:
            self.act_dub = QAction("Start &Dubbing…", self)
            self.act_dub.setShortcut(QKeySequence("Ctrl+Return"))
            self.act_dub.triggered.connect(self.start_dubbing)

        if view_menu:
            view_menu.addSeparator()
            self.act_timeline = QAction("&Timeline Panel", self)
            self.act_timeline.setCheckable(True)
            self.act_timeline.setShortcut(QKeySequence("Ctrl+Shift+T"))
            self.act_timeline.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            self.act_timeline.setToolTip("Show or hide the editing timeline")
            self.act_timeline.setChecked(bool(getattr(self, "_timeline_open", True)))
            self.act_timeline.triggered.connect(self._toggle_timeline)
            view_menu.addAction(self.act_timeline)
            panels_menu = view_menu.addMenu("&Panels")
            for key, act in self._panel_actions.items():
                panels_menu.addAction(act)
            act_reset = QAction("&Reset Layout", self)
            act_reset.triggered.connect(self.reset_layout)
            view_menu.addAction(act_reset)

    def _bind_space_play(self):
        sc = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        sc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc.setAutoRepeat(False)
        sc.activated.connect(self._toggle_space_play)
        move = QShortcut(QKeySequence(Qt.Key.Key_V), self)
        move.setContext(Qt.ShortcutContext.WindowShortcut)
        move.setAutoRepeat(False)
        move.activated.connect(lambda: self._set_preview_tool("move"))
        hand = QShortcut(QKeySequence(Qt.Key.Key_H), self)
        hand.setContext(Qt.ShortcutContext.WindowShortcut)
        hand.setAutoRepeat(False)
        hand.activated.connect(lambda: self._set_preview_tool("hand"))
        undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo.setContext(Qt.ShortcutContext.WindowShortcut)
        undo.activated.connect(self._timeline_undo)
        redo = QShortcut(QKeySequence.StandardKey.Redo, self)
        redo.setContext(Qt.ShortcutContext.WindowShortcut)
        redo.activated.connect(self._timeline_redo)
        for seq, action in (
            ("Ctrl+Shift+S", "show"),
            ("Ctrl+Shift+A", "retry"),
            ("Ctrl+Shift+L", "translate"),
            ("Ctrl+Shift+V", "tts"),
            ("Ctrl+Shift+R", "all"),
        ):
            sc_tx = QShortcut(QKeySequence(seq), self)
            sc_tx.setContext(Qt.ShortcutContext.WindowShortcut)
            sc_tx.setAutoRepeat(False)
            sc_tx.activated.connect(
                lambda checked=False, a=action: self._on_timeline_transcript_action(a)
            )

    def rebuild_speech_bed(self):
        """Tools menu: re-isolate music/effects from dialogue for the active dub."""
        import os

        index = getattr(self, "_composition_index", -1)
        comps = getattr(self, "_compositions", None) or []
        if index < 0 or index >= len(comps):
            self.log.info("Add or select a dub composition before rebuilding the stem bed")
            return
        source = str(comps[index].get("source") or "")
        if not source or not os.path.isfile(source):
            self.log.info("No source media for stem separation")
            return
        # Drop cached bed so Demucs / FFmpeg runs again with current Features prefs.
        comps[index]["bed"] = ""
        comps[index].pop("vocals_stem", None)
        self._build_speech_bed(index, source)

    def run_studio_auto_mix(self):
        """Tools menu: duck original speech onto the music bed under dubbed lines."""
        timeline = getattr(self, "timeline", None)
        if timeline is None:
            return
        if not timeline.auto_mix():
            self.log.info("Auto mix needs voice lines on the timeline")
            return
        index = getattr(self, "_composition_index", -1)
        comps = getattr(self, "_compositions", None) or []
        if 0 <= index < len(comps):
            comps[index]["auto_mix"] = True
            comps[index]["footage"] = timeline.export_footage()
        self.log.info("Auto mix · detecting original speech under dubbed lines…")

    def _open_feature_settings(self):
        window = self.window()
        opener = getattr(window, "open_settings_dialog", None)
        if callable(opener):
            opener("Features")
            return
        from jela.gui.dialogs.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        for i in range(dialog.tabs.count()):
            if dialog.tabs.tabText(i).replace("&", "").lower() == "features":
                dialog.tabs.setCurrentIndex(i)
                break
        dialog.exec()

    def _set_preview_tool(self, tool: str):
        if self._text_field_focused():
            return
        overlay = getattr(self, "overlay", None)
        preview = getattr(self, "preview", None)
        if overlay is not None and hasattr(overlay, "set_view_tool"):
            overlay.set_view_tool(tool)
        elif preview is not None and hasattr(preview, "set_view_tool"):
            preview.set_view_tool(tool)

    def _text_field_focused(self) -> bool:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextEdit)):
            return True
        if isinstance(focus, QAbstractSpinBox):
            return True
        if isinstance(focus, QComboBox) and focus.isEditable() and focus.lineEdit() and focus.lineEdit().hasFocus():
            return True
        return False

    def _toggle_space_play(self):
        if self._text_field_focused():
            return
        self.preview.toggle_play()

    def _editable_text_focused(self) -> bool:
        focus = QApplication.focusWidget()
        return isinstance(focus, (QLineEdit, QPlainTextEdit, QTextEdit)) or (
            isinstance(focus, QComboBox) and focus.isEditable()
            and focus.lineEdit() is not None and focus.lineEdit().hasFocus()
        )

    def _timeline_undo(self):
        if self._editable_text_focused():
            focus = QApplication.focusWidget()
            target = focus.lineEdit() if isinstance(focus, QComboBox) else focus
            if target is not None and hasattr(target, "undo"):
                target.undo()
            return
        if hasattr(self, "timeline") and self.timeline.canvas.can_undo():
            self.timeline.canvas.undo()

    def _timeline_redo(self):
        if self._editable_text_focused():
            focus = QApplication.focusWidget()
            target = focus.lineEdit() if isinstance(focus, QComboBox) else focus
            if target is not None and hasattr(target, "redo"):
                target.redo()
            return
        if hasattr(self, "timeline") and self.timeline.canvas.can_redo():
            self.timeline.canvas.redo()

    # ── layout persistence ─────────────────────────────────────────
    def _settings(self) -> QSettings:
        return QSettings("Jela", "JelaStudio")

    def _load_layout_meta(self) -> dict:
        raw = self._settings().value(LAYOUT_META_KEY, "")
        if isinstance(raw, QByteArray):
            raw = bytes(raw).decode("utf-8", errors="ignore")
        if not isinstance(raw, str) or not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _read_dock_bytes(self) -> bytes | None:
        data = self._settings().value(SETTINGS_KEY)
        if isinstance(data, QByteArray) and not data.isEmpty():
            return bytes(data)
        if isinstance(data, (bytes, bytearray)) and data:
            return bytes(data)
        # Fall back to previous key if present
        legacy = self._settings().value("dubbing_view/dock_state_v16")
        if isinstance(legacy, QByteArray) and not legacy.isEmpty():
            return bytes(legacy)
        if isinstance(legacy, (bytes, bytearray)) and legacy:
            return bytes(legacy)
        return None

    def _restore_layout(self):
        """Load saved layout into pending state; apply after the window is shown."""
        self._layout_ready = False
        self._layout_bootstrapped = False
        self._pending_dock_state = self._read_dock_bytes()
        self._layout_meta = self._load_layout_meta()
        meta = self._layout_meta
        # Keep timeline panel visible (ignore older saved closed state).
        self._timeline_open = True
        self._restored_layout = bool(self._pending_dock_state)
        # Default: hide activity log until a saved preference says otherwise
        if "panels" not in meta:
            self.workspace.set_visible("log", False)
        self._sync_panel_actions()

    def _apply_pending_layout(self):
        if getattr(self, "_layout_bootstrapped", False):
            return
        self._layout_bootstrapped = True
        meta = getattr(self, "_layout_meta", {}) or {}
        restored = False
        pending = getattr(self, "_pending_dock_state", None)
        if pending:
            restored = bool(self.workspace.restore_state(pending))
        self._restored_layout = restored

        panels = meta.get("panels") if isinstance(meta.get("panels"), dict) else None
        if panels:
            for key in _PANEL_KEYS:
                if key in panels:
                    self.workspace.set_visible(key, bool(panels[key]))
        elif not restored:
            self.workspace.set_visible("log", False)

        if not restored:
            self._apply_default_sizes()
            self.workspace.save_default_layout()

        shelf_tab = str(meta.get("shelf_tab") or "").strip()
        if shelf_tab in {"dub", "props", "captions"}:
            # Legacy: props/captions moved to the right Inspector dock.
            shelf_tab = "script" if shelf_tab in {"props", "captions"} else "media"
        if shelf_tab and hasattr(self, "shelf"):
            self.shelf.show_key(shelf_tab)

        setup_page = meta.get("setup_page")
        if isinstance(setup_page, int) and hasattr(self, "setup_pages"):
            btn = self.setup_pages.button(setup_page)
            if btn is not None:
                btn.setChecked(True)
                if hasattr(self, "_show_setup_page"):
                    self._show_setup_page(setup_page)

        if hasattr(self, "_sync_timeline_visibility"):
            self._sync_timeline_visibility()
        self._sync_panel_actions()
        self._layout_ready = True
        self._pending_dock_state = None
        self._save_layout()

    def _panel_visibility(self) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for key in _PANEL_KEYS:
            dock = self.workspace.dock(key)
            if dock is None:
                continue
            # isHidden tracks user close/show; isVisible is false while ancestors are hidden
            out[key] = not dock.isHidden()
        return out

    def _save_layout(self):
        if not getattr(self, "_layout_ready", False):
            return
        if not hasattr(self, "workspace"):
            return
        settings = self._settings()
        settings.setValue(SETTINGS_KEY, QByteArray(self.workspace.save_state()))
        meta = {
            "panels": self._panel_visibility(),
            "timeline_open": bool(getattr(self, "_timeline_open", False)),
            "shelf_tab": self.shelf.current_key() if hasattr(self, "shelf") else "",
            "setup_page": 0,
        }
        settings.setValue(LAYOUT_META_KEY, json.dumps(meta))
        settings.sync()
        try:
            if hasattr(self, "store"):
                self.store.set_setting("dub", "layout_meta", json.dumps(meta))
        except Exception:
            pass

    def reset_layout(self):
        self._layout_ready = False
        self.workspace.reset_layout()
        self._apply_default_sizes()
        self.workspace.save_default_layout()
        self.workspace.set_visible("log", False)
        for key in ("shelf", "preview", "props"):
            self.workspace.set_visible(key, True)
        self._sync_panel_actions()
        self._layout_ready = True
        self._save_layout()

    def _sync_panel_actions(self):
        if not hasattr(self, "_panel_actions"):
            return
        for key, act in self._panel_actions.items():
            act.blockSignals(True)
            dock = self.workspace.dock(key)
            visible = bool(dock and not dock.isHidden())
            act.setChecked(visible)
            act.blockSignals(False)

    def _on_layout_changed(self):
        self._sync_panel_actions()
        self._save_layout()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_layout_bootstrapped", False):
            QTimer.singleShot(0, self._apply_pending_layout)

    def _apply_default_sizes(self):
        if not hasattr(self, "workspace"):
            return
        shelf = self.workspace.dock("shelf")
        preview = self.workspace.dock("preview")
        props = self.workspace.dock("props")
        if not shelf or not preview:
            return
        w = max(900, self.width())
        h = max(500, self.height())
        from jela.gui.views.studio.constants import (
            PANEL_MAX_W, PANEL_MIN_W, PROPS_MAX_W, PROPS_MIN_W, SHELF_MAX_W, SHELF_MIN_W,
        )
        shelf_w = max(SHELF_MIN_W, min(SHELF_MAX_W, int(w * 0.30)))
        preview_w = max(PANEL_MIN_W, min(PANEL_MAX_W, int(w * 0.40)))
        props_w = max(PROPS_MIN_W, min(PROPS_MAX_W, int(w * 0.22)))
        top_h = max(320, int(h * 0.58))

        docks = [shelf, preview]
        sizes = [shelf_w, preview_w]
        if props and not props.isHidden():
            docks.append(props)
            sizes.append(props_w)
        self.workspace.host.resizeDocks(docks, sizes, Qt.Orientation.Horizontal)
        self.workspace.host.resizeDocks(docks, [top_h] * len(docks), Qt.Orientation.Vertical)

    def hideEvent(self, event):
        self.stop_playback()
        self._save_layout()
        if hasattr(self, "_store_project_session"):
            self._store_project_session()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_playback()
        if hasattr(self, "timeline"):
            self.timeline.stop_recording()
        if hasattr(self, "_stop_active_job"):
            self._stop_active_job()
        self._save_layout()
        if hasattr(self, "_store_project_session"):
            self._store_project_session()
        super().closeEvent(event)

    def stop_playback(self):
        if hasattr(self, "preview"):
            self.preview.stop_playback()
        if hasattr(self, "_clip_lanes"):
            self._stop_clip_lanes()
        if hasattr(self, "stop_voice_preview"):
            self.stop_voice_preview()
