"""Track inspector (right-dock Properties), text/fx shelves, and timeline selection."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea, QStackedWidget, QSizePolicy,
)

from claynext.constants.timeline_constants import FX_KINDS, OVERLAY_KINDS
from claynext.models.thumbnails import pixmap_for
from claynext.models.adjust import clean_adjust
from claynext.gui.components.overlay_canvas import TEXT_KINDS
from claynext.gui.components.fx_shelf import FxShelfPanel
from claynext.gui.components.properties_panel import TrackPropsPage
from claynext.gui.components.text_styles_panel import TextStylesPanel
from claynext.gui.dialogs.project_settings_dialog import ProjectInfoPage

_PROPS_PAGE = 0
_PROJECT_PAGE = 1
_CAPTION_PAGE = 2
_PAGE_MIN_W = 240


class InspectorTools:
    """Clip inspector, text styles, and timeline selection."""

    def _build_text_panel(self) -> QWidget:
        self.text_styles = TextStylesPanel()
        self.text_styles.add_requested.connect(self._add_text_style)
        return self.text_styles

    def _build_fx_panel(self, kind: str) -> QWidget:
        panel = FxShelfPanel(kind)
        panel.add_requested.connect(self._add_text_style)
        return panel

    def _build_properties_panel(self) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("properties_panel")
        wrap.setMinimumWidth(_PAGE_MIN_W + 36)
        wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(0)

        # Title lives on the dock panel header — no inner shelf header.
        self.prop_stack = QStackedWidget()
        self.track_props = TrackPropsPage()
        self.track_props.changed.connect(self._apply_track_props)
        self.track_props.overlay_changed.connect(self._apply_inspector)
        self.track_props.overlay_delete.connect(self._remove_selected_overlay)
        self.track_props.text_animation.connect(self._on_text_animation)
        self.track_props.text_align.connect(self._on_text_align)
        self.track_props.text_inspector.apply_all_requested.connect(self._apply_caption_style_all)
        self.track_props.clear_keys.connect(self._clear_source_keys)
        self.track_props.adjust_changed.connect(self._on_adjust_changed)
        self.track_props.level_changed.connect(self._on_props_level)
        self.track_props.key_toggle.connect(self._on_props_key_toggle)
        self.track_props.key_step.connect(self._on_props_key_step)
        self.track_props.fades_changed.connect(self._on_props_fades)
        self.track_props.auto_key_changed.connect(self._on_props_auto_key)
        self.track_props.canvas_changed.connect(self._on_props_canvas)
        self.track_props.fx_changed.connect(self._on_fx_changed)
        self.inspector = self.track_props.inspector

        # Sticky Video / Audio / Adjust — full-width compact tabs for Cover / project video.
        self._props_tabs_host = QFrame()
        self._props_tabs_host.setObjectName("dub_props_tabs_host")
        self._props_tabs_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tabs_lay = QHBoxLayout(self._props_tabs_host)
        tabs_lay.setContentsMargins(10, 4, 10, 4)
        tabs_lay.setSpacing(0)
        tabs_lay.addWidget(self.track_props.tab_bar, 1)
        outer.addWidget(self._props_tabs_host)
        self._props_tabs_host.hide()

        self.prop_stack.addWidget(self._scroll_page(self.track_props))

        self.project_info = ProjectInfoPage()
        self.project_info.modify_requested.connect(self._open_project_settings)
        self.prop_stack.addWidget(self._scroll_page(self.project_info))

        # Captions Look / Motion / Layout — shown when a Caption track is selected.
        self.prop_stack.addWidget(self._build_caption_body())

        self.project_info.show_empty()
        self.prop_stack.setCurrentIndex(_PROJECT_PAGE)
        outer.addWidget(self.prop_stack, 1)
        self._sync_props_header()
        return wrap

    @staticmethod
    def _scroll_page(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("dub_props_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("dub_props_scroll_body")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(14, 8, 18, 16)
        lay.setSpacing(4)
        page.setMinimumWidth(_PAGE_MIN_W)
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(page, 1000)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def _sync_props_header(self):
        """Drive the dock title; hide Video/Audio/Adjust when not on a video clip."""
        page = (
            self.prop_stack.currentIndex()
            if getattr(self, "prop_stack", None) is not None
            else _PROJECT_PAGE
        )
        if page == _PROJECT_PAGE:
            title = "Project"
            if hasattr(self, "_props_tabs_host"):
                self._props_tabs_host.hide()
        elif page == _CAPTION_PAGE:
            title = "Captions"
            if hasattr(self, "_props_tabs_host"):
                self._props_tabs_host.hide()
        else:
            title = ""
            if hasattr(self, "track_props") and self.track_props.title is not None:
                title = (self.track_props.title.text() or "").strip()
            title = title or "Properties"
            if hasattr(self, "track_props") and hasattr(self, "_props_tabs_host"):
                track = self.track_props.track
                self._props_tabs_host.setVisible(bool(track and track.kind == "video"))
        if hasattr(self, "workspace"):
            dock = self.workspace.dock("props")
            if dock is not None:
                dock.setWindowTitle(title)

    def _show_inspector_tab(self, index: int):
        if index == 2:
            self._show_project_page()

    def _focus_props_dock(self):
        """Show / raise the right-side Properties dock."""
        if not hasattr(self, "workspace"):
            return
        self.workspace.set_visible("props", True)
        dock = self.workspace.dock("props")
        if dock is not None:
            dock.raise_()
            dock.activateWindow()

    def _show_props_page(self, title: str, *, focus_shelf: bool = False):
        """Refresh the Properties page. Only raise the dock when explicitly asked."""
        self.prop_stack.setCurrentIndex(_PROPS_PAGE)
        if hasattr(self, "track_props") and title:
            self.track_props.title.setText(title)
        self._sync_props_header()
        if focus_shelf:
            self._focus_props_dock()

    def _show_project_page(self):
        if not hasattr(self, "prop_stack"):
            return
        self.prop_stack.setCurrentIndex(_PROJECT_PAGE)
        self._sync_props_header()
        self._focus_props_dock()

    def _show_caption_page(self, *, focus: bool = True):
        """Show Captions controls in the Inspector (Caption track / clip selected)."""
        if not hasattr(self, "prop_stack"):
            return
        self.prop_stack.setCurrentIndex(_CAPTION_PAGE)
        self._sync_props_header()
        if focus:
            self._focus_props_dock()

    def _add_text_style(self, style: dict):
        clip = self.timeline.add_text_style(style)
        if clip:
            kind = {"effect": "Effect", "filter": "Filter", "shape": "Element"}.get(clip.kind, "Text")
            self.log.info(f"{kind} · {clip.label}")
            self._on_timeline_selection(clip.id, clip.track_id, focus_shelf=True)
        self._sync_preview_overlays(force=True)

    def _editor_for(self, item):
        kind = item.kind if item is not None else ""
        return self._editor_for_kind(kind)

    def _editor_for_kind(self, kind: str):
        if kind in TEXT_KINDS:
            return self.track_props.text_inspector
        if kind in {"shape", "mask"}:
            return self.track_props.shape_inspector
        return self.inspector

    def _bind_overlay_editor(self, item):
        if item is not None and self.track_props.clip is not None and self.track_props.clip.id != item.id:
            return
        self._editor_for(item).bind(item)

    def _on_overlay_selected(self, item):
        # Overlay rebuild during playhead sync must not hijack selection / shelf.
        if getattr(self, "_syncing_overlays", False):
            return
        if item:
            self._on_timeline_selection(item.id, "")
        else:
            # Clicked empty / letterbox — clear timeline selection too.
            canvas = self.timeline.canvas
            if canvas.selected_ids or any(t.selected for t in canvas.tracks):
                canvas.selected_ids.clear()
                for t in canvas.tracks:
                    t.selected = False
                canvas.update()
                self.timeline.rail.rebuild(canvas.tracks)
                self.timeline._on_clip_selected("")
        self._bind_overlay_editor(item)

    def _on_overlays_changed(self):
        if self._syncing_overlays:
            return
        item = self.overlay.selected_item()
        self._bind_overlay_editor(item)
        if item:
            self.timeline.update_overlay_extra(item.id, item.to_dict())

    def _on_overlay_command(self, name: str):
        if name == "delete":
            self._remove_selected_overlay()
            return
        if name == "duplicate":
            item = self.overlay.selected_item()
            if item is not None:
                self.timeline.canvas.selected_ids = {item.id}
            self.timeline.canvas.duplicate_selected()

    def _on_overlay_edited(self, item):
        if getattr(self, "_syncing_overlays", False) or item is None:
            return
        editor = self._editor_for(item)
        if hasattr(editor, "sync_live"):
            editor.sync_live(item)

    def _apply_inspector(self):
        clip = self.track_props.clip
        editor = self._editor_for_kind(clip.kind if clip is not None else "")
        src = editor.current()
        if not src:
            return
        item = next((it for it in self.overlay.items if it.id == src.id), None)
        target = item or src
        editor.apply_to(target)
        if item:
            self.overlay.update()
        self.timeline.update_overlay_extra(target.id, target.to_dict())

    def _apply_caption_style_all(self):
        """Copy the open caption's look onto every caption, leaving each line's words and timing."""
        editor = self.track_props.text_inspector
        src = editor.current()
        if src is None or getattr(src, "kind", "") != "caption":
            return
        editor.apply_to(src)
        style = src.style()
        layout = {
            "x": float(src.x),
            "y": float(src.y),
            "rotation": float(src.rotation),
            "w": float(src.w),
            "h": float(src.h),
            "live": bool(src.live),
        }
        count = 0
        for clip in list(self.timeline.canvas.clips):
            if clip.kind != "caption":
                continue
            ov = dict(clip.extra.get("overlay") or {})
            text = str(ov.get("text") or clip.label or "")
            start = ov.get("start_ms", clip.start_ms)
            dur = ov.get("duration_ms", clip.duration_ms)
            path = str(ov.get("path") or clip.extra.get("path") or "")
            extra = ov.get("extra") if isinstance(ov.get("extra"), dict) else None
            ov.update(style)
            ov.update(layout)
            ov["id"] = clip.id
            ov["kind"] = "caption"
            ov["text"] = text
            ov["start_ms"] = start
            ov["duration_ms"] = dur
            if path:
                ov["path"] = path
            if extra is not None:
                ov["extra"] = extra
            self.timeline.update_overlay_extra(clip.id, ov)
            count += 1
        if count:
            self._sync_preview_overlays(force=True)
            if hasattr(self, "log"):
                self.log.info(f"Caption style · {count} line{'s' if count != 1 else ''}")

    def _on_text_animation(self, slot: str):
        clip = self.track_props.clip
        if clip is not None and any(it.id == clip.id for it in self.overlay.items):
            self.overlay.preview_animation(clip.id, slot)

    def _on_text_align(self, where: str):
        clip = self.track_props.clip
        editor = self._editor_for_kind(clip.kind if clip is not None else "text")
        item = editor.current()
        if item is None:
            return
        x, y = self.overlay.aligned_position(item, where)
        editor.set_position(x, y)

    def _remove_selected_overlay(self):
        clip = self.track_props.clip
        target = clip.id if clip is not None and clip.kind in OVERLAY_KINDS else ""
        if not target:
            item = self.overlay.selected_item()
            target = item.id if item else ""
        if not target:
            return
        self.timeline.canvas.selected_ids = {target}
        self.timeline.canvas.remove_selected()

    def _sync_preview_overlays(self, force: bool = False):
        if not hasattr(self, "overlay"):
            return
        self._sync_preview_fx()
        self._sync_master_transport()
        self.overlay.set_playhead(self.timeline.canvas.playhead_ms)
        clips = self.timeline.overlay_clips()
        ids = tuple((c.id, c.start_ms, c.duration_ms) for c in clips)
        if not force and ids == self._shown_overlay_ids:
            return
        self._shown_overlay_ids = ids
        rows = []
        for clip in clips:
            ov = dict(clip.extra.get("overlay") or {})
            ov["id"] = clip.id
            ov["kind"] = clip.kind
            ov["start_ms"] = clip.start_ms
            ov["duration_ms"] = clip.duration_ms
            if clip.extra.get("path"):
                ov["path"] = clip.extra["path"]
            rows.append(ov)
        self._syncing_overlays = True
        self.overlay.set_items(rows)
        self._syncing_overlays = False
        self._bind_overlay_editor(self.overlay.selected_item())

    def _sync_preview_fx(self):
        live = self._player_mode == "timeline" and bool(self._timeline_media())
        spans = self.timeline.export_fx() if live else []
        self.preview.set_video_effects(spans, self.timeline.canvas.playhead_ms)

    def _on_timeline_clip(self, clip_id: str):
        self._sync_preview_overlays()
        item = next((it for it in self.overlay.items if it.id == clip_id), None)
        if item:
            self.overlay.selected_id = item.id
            self.overlay.update()

    def _on_timeline_selection(self, clip_id: str, track_id: str, *, focus_shelf: bool = False):
        self._sel_clip_id = clip_id
        self._sel_track_id = track_id
        canvas = self.timeline.canvas
        clip = next((c for c in canvas.clips if c.id == clip_id), None) if clip_id else None
        track = canvas.track_by_id(track_id) if track_id else None
        if clip and not track:
            track = canvas.track_by_id(clip.track_id)
        # Captions are text — their settings live in the track inspector.
        if track:
            source = ""
            if track.kind == "video":
                if clip is None:
                    clip = next((c for c in canvas.footage_clips() if c.track_id == track.id), None)
                source = str(clip.extra.get("path") or "") if clip else canvas.media_path
            fresh = clip is not self.track_props.clip
            self.track_props.bind(track, clip, source_path=source)
            self._sync_props_audio()
            self._show_props_page(
                clip.label if clip and not clip.extra.get("master") else track.name,
                focus_shelf=focus_shelf,
            )
            is_footage = clip is not None and clip in canvas.footage_clips()
            self._set_canvas_edit(is_footage)
            if is_footage and fresh:
                self.track_props.set_blur_source(pixmap_for(source, QSize(320, 180)).toImage() if source else QImage())
            return
        self._set_canvas_edit(False)
        self._refresh_project_info()
        self._show_project_page()

    def _set_canvas_edit(self, on: bool):
        if hasattr(self, "overlay"):
            self.overlay.set_video_edit(on and self._player_mode == "timeline")
        if on:
            self.track_props.show_canvas_hint(self.preview.canvas_covered())

    def _on_props_canvas(self, state: dict):
        if not self._footage_bound():
            return
        self._set_footage_canvas(state)

    def _apply_track_props(self):
        track = self.track_props.track
        clip = self.track_props.clip
        if not track:
            return
        self.track_props.apply_to(track, clip)
        self.timeline.rail.rebuild(self.timeline.canvas.tracks)
        self.timeline.canvas._relayout(notify=False)
        self.timeline.canvas.update()
        self.timeline._emit_mix()
        if clip and clip.kind in OVERLAY_KINDS:
            if clip.kind not in TEXT_KINDS:
                ov = dict(clip.extra.get("overlay") or {})
                ov["text"] = clip.label
                clip.extra["overlay"] = ov
            self._sync_preview_overlays(force=True)
        elif clip and clip.kind in FX_KINDS:
            self._sync_preview_fx()

    def _on_transition_split_clicked(self, clip_id: str, cut_ms: int):
        if hasattr(self, "shelf"):
            self.shelf.show_key("transitions")

    def _on_transition_selected(self, clip_id: str):
        clip = self.timeline.canvas.clip_by_id(clip_id)
        if clip:
            self._on_timeline_selection(clip.id, clip.track_id)

    def _on_fx_changed(self, fx: dict):
        clip = self.track_props.clip
        if clip is None:
            return
        applied = clip.extra.get("applied_fx") if clip.kind == "video" else None
        if isinstance(applied, list) and applied:
            from claynext.models.fx import clean_fx

            last = applied[-1] if isinstance(applied[-1], dict) else {}
            kind = str(last.get("kind") or "effect")
            applied[-1] = clean_fx(kind, {**last, **fx, "kind": kind})
            self.timeline.canvas.update()
            self._sync_preview_fx()
        elif clip.kind in FX_KINDS:
            self.timeline.update_fx_extra(clip.id, fx)
            self.track_props.title.setText(clip.label)
            self._sync_preview_fx()
        elif "transition" in clip.extra:
            clip.extra["transition"].update(fx)
            self.timeline.canvas.update()
            self._sync_preview_fx()

    def _audio_clip(self):
        clip = self.track_props.clip
        return clip if clip is not None and clip.kind in {"video", "voice", "audio"} else None

    def _sync_props_audio(self):
        """Mirror the clip level under the playhead, key count, and bed state into the Audio section."""
        if not hasattr(self, "track_props"):
            return
        clip = self._audio_clip()
        if clip is None:
            return
        canvas = self.timeline.canvas
        ms = canvas.playhead_ms
        self.track_props.show_level(
            canvas.level_at(clip, ms, fades=False),
            canvas.key_index_near(clip, ms) >= 0,
            canvas.neighbour_key(clip, ms, -1) is not None,
            canvas.neighbour_key(clip, ms, 1) is not None,
        )
        self.track_props.show_key_count(len(canvas.clip_keys(clip)))
        self.track_props.show_bed_state(bool(canvas.bed_path))

    def _on_props_level(self, level: float):
        clip = self._audio_clip()
        if clip is None:
            return
        self.timeline.canvas.set_level_at(clip, self.timeline.canvas.playhead_ms, level)
        self.timeline._emit_mix()

    def _on_props_key_toggle(self):
        clip = self._audio_clip()
        if clip is None:
            return
        self.timeline.canvas.toggle_key_at(clip, self.timeline.canvas.playhead_ms)
        self.timeline._emit_mix()
        self._sync_props_audio()

    def _on_props_key_step(self, step: int):
        clip = self._audio_clip()
        if clip is None:
            return
        ms = self.timeline.canvas.neighbour_key(clip, self.timeline.canvas.playhead_ms, step)
        if ms is None:
            return
        self.timeline.set_playhead_ms(ms)
        self._on_timeline_seek(ms)
        self._sync_props_audio()

    def _on_props_fades(self, fade_in: int, fade_out: int):
        clip = self._audio_clip()
        if clip is None:
            return
        for key, value in (("fade_in", fade_in), ("fade_out", fade_out)):
            if value > 0:
                clip.extra[key] = int(value)
            else:
                clip.extra.pop(key, None)
        self.timeline.canvas.update()
        self.timeline._emit_mix()

    def _on_props_auto_key(self, state: dict):
        clip = self._audio_clip()
        if clip is None or clip.kind != "video":
            return
        clip.extra["auto_key"] = dict(state)
        tl = self.timeline
        if not state.get("on"):
            tl.canvas.clear_keys()
            tl._emit_mix()
            self.log.info("Auto key off · source volume restored")
        else:
            tl.duck_level = int(state.get("level", 0)) / 100.0
            if state.get("detect") and tl.auto_mix():
                self.log.info("Auto key · finding original voices…")
            else:
                spans = tl.auto_duck(0.0 if tl.canvas.bed_path else tl.duck_level)
                self.log.info(f"Auto key · source pinned down under {spans} dubbed span(s), music and effects kept")
        self._sync_props_audio()

    def _on_adjust_changed(self, adjust: dict, preset: str):
        clip = self.track_props.clip
        if clip is None or clip.kind != "video":
            return
        values = clean_adjust(adjust)
        if values:
            clip.extra["adjust"] = values
            clip.extra["filter"] = preset
        else:
            clip.extra.pop("adjust", None)
            clip.extra.pop("filter", None)
        if self._player_mode == "timeline" and clip in self.timeline.canvas.footage_clips():
            self.preview.set_video_adjust(values)

    def _clear_source_keys(self):
        self.timeline.canvas.clear_keys()
        self.timeline._emit_mix()
        track = self.track_props.track
        if track:
            self.track_props.bind(track, self.track_props.clip, source_path=self.timeline.canvas.media_path)
            self._sync_props_header()

