"""Bind a track or clip into the properties page."""
from __future__ import annotations

from claynext.constants.timeline_constants import FX_KINDS, OVERLAY_KINDS
from claynext.gui.components.collapsible_section import CollapsibleSection
from claynext.gui.components.overlay import TEXT_KINDS, OverlayItem
from claynext.gui.components.timeline.models import TimelineClip, TimelineTrack
from claynext.models.adjust import FILTER_PRESETS, clean_adjust

from claynext.gui.components.properties_panel.const import AUDIO_KINDS, VIDEO_TABS

class PropsBind:
    def current_tab(self) -> str:
        return self._tab if self.track is not None and self.track.kind == "video" else ""

    def _set_tab(self, tab: str):
        self._tab = tab
        self.tab_group.button(VIDEO_TABS.index(tab)).setChecked(True)
        self._sync_sections()
        self.tab_changed.emit(tab)

    def _sync_sections(self):
        track, clip = self.track, self.clip
        if track is None:
            return
        kind = track.kind
        is_master = bool(clip and clip.extra.get("master"))
        has_audio = kind in AUDIO_KINDS
        if kind == "video":
            tab = self._tab
            show = {
                self.sec_text: False,
                self.sec_shape: False,
                self.sec_fx: clip is not None and (
                    bool(clip.extra.get("transition")) or bool(clip.extra.get("applied_fx"))
                ),
                self.sec_canvas: tab == "video" and clip is not None,
                self.sec_clip: False,
                self.sec_audio: tab == "audio",
                self.sec_autokey: tab == "audio",
                self.sec_filter: tab == "adjust",
                self.sec_color: tab == "adjust",
            }
        else:
            show = {
                self.sec_text: clip is not None and clip.kind in TEXT_KINDS,
                self.sec_shape: clip is not None and clip.kind in {"shape", "mask"},
                self.sec_fx: clip is not None and clip.kind in FX_KINDS,
                self.sec_canvas: False,
                self.sec_clip: clip is not None and not is_master
                    and clip.kind in OVERLAY_KINDS
                    and clip.kind not in TEXT_KINDS | FX_KINDS | {"shape", "mask"},
                self.sec_audio: has_audio,
                self.sec_autokey: False,
                self.sec_filter: False,
                self.sec_color: False,
            }
        for widget, visible in show.items():
            widget.setVisible(visible)

    def bind(self, track: TimelineTrack | None, clip: TimelineClip | None = None, source_path: str = ""):
        del source_path  # kept for call-site compatibility
        self.track = track
        self.clip = clip
        if not track:
            return
        self._block = True
        kind = track.kind
        is_master = bool(clip and clip.extra.get("master"))
        self.title.setText(clip.label if clip and not is_master else track.name)
        fade_in = int(clip.extra.get("fade_in") or 0) if clip else 0
        fade_out = int(clip.extra.get("fade_out") or 0) if clip else 0
        self.spin_fade_in.setValue(round(fade_in / 100))
        self.spin_fade_out.setValue(round(fade_out / 100))
        self.lbl_fade_in.setText(f"Fade in · {fade_in / 1000:.1f}s")
        self.lbl_fade_out.setText(f"Fade out · {fade_out / 1000:.1f}s")
        for widget in (self.lbl_fade_in, self.spin_fade_in, self.lbl_fade_out, self.spin_fade_out,
                       self.spin_db, self.btn_key, self.btn_key_prev, self.btn_key_next):
            widget.setEnabled(clip is not None)

        auto = dict(clip.extra.get("auto_key") or {}) if clip else {}
        self.chk_autokey.setChecked(bool(auto.get("on")))
        self.chk_detect.setChecked(bool(auto.get("detect")))
        duck_val = int(auto.get("level", 0))
        self.spin_duck.setValue(duck_val)
        self.lbl_duck.setText(f"Duck to · {duck_val}%")
        self.show_key_count(len(clip.extra.get("keys") or []) if clip else 0)
        self._sync_autokey_enabled()

        self.set_canvas_state(clip.extra.get("canvas") if clip and kind == "video" else None)

        adjust = clean_adjust(clip.extra.get("adjust") if clip else None)
        for key, (lbl, spin, label) in self._adjust_spins.items():
            spin.setValue(adjust.get(key, 0))
            lbl.setText(label)
        self._check_preset(str(clip.extra.get("filter") or "custom") if adjust else "none")

        overlay = None
        if clip and clip.kind in OVERLAY_KINDS:
            data = dict(clip.extra.get("overlay") or {})
            data["id"] = clip.id
            data["kind"] = clip.kind
            data["start_ms"] = clip.start_ms
            data["duration_ms"] = clip.duration_ms
            overlay = OverlayItem.from_dict(data)
        is_text = overlay is not None and overlay.kind in TEXT_KINDS
        is_shape = overlay is not None and overlay.kind in {"shape", "mask"}
        styled = is_text or is_shape
        self.inspector.bind(None if styled else overlay)
        self.inspector.setVisible(overlay is not None and not styled)
        self.text_inspector.bind(overlay if is_text else None)
        self.shape_inspector.bind(overlay if is_shape else None)
        is_fx = clip is not None and clip.kind in FX_KINDS
        has_tr = clip is not None and bool(clip.extra.get("transition"))
        applied = list(clip.extra.get("applied_fx") or []) if clip is not None else []
        applied = [row for row in applied if isinstance(row, dict)]
        if applied:
            last = applied[-1]
            kind = str(last.get("kind") or "effect")
            self.fx_inspector.bind(kind if kind in {"effect", "filter"} else "effect", last)
            if isinstance(self.sec_fx, CollapsibleSection):
                self.sec_fx.set_title("Filter" if kind == "filter" else "Effect")
        elif is_fx:
            self.fx_inspector.bind(clip.kind, clip.extra.get("fx"))
            if isinstance(self.sec_fx, CollapsibleSection):
                self.sec_fx.set_title("Filter" if clip.kind == "filter" else "Effect")
        elif has_tr:
            self.fx_inspector.bind("transition", clip.extra.get("transition"))
            if isinstance(self.sec_fx, CollapsibleSection):
                self.sec_fx.set_title("Transition")

        self._sync_sections()
        self._block = False

    def apply_to(self, track: TimelineTrack, clip: TimelineClip | None = None):
        """Kept for inspector hook; mute and clip rename stay on the timeline."""
        del track, clip

    def adjust_values(self) -> dict[str, int]:
        return clean_adjust({key: spin.value() for key, (_l, spin, _n) in self._adjust_spins.items()})

    def _check_preset(self, key: str):
        self.preset_group.setExclusive(False)
        for i, name in enumerate(self._preset_keys):
            btn = self.preset_group.button(i)
            if btn is not None:
                btn.setChecked(name == key)
        self.preset_group.setExclusive(True)

    def _on_preset(self, index: int):
        key = self._preset_keys[index]
        values = FILTER_PRESETS[key][1]
        self._block = True
        for name, (lbl, spin, label) in self._adjust_spins.items():
            spin.setValue(values.get(name, 0))
            lbl.setText(label)
        self._block = False
        self._check_preset(key)
        self.adjust_changed.emit(self.adjust_values(), key)

    def _on_adjust_spin(self, key: str, value: int):
        lbl, _spin, label = self._adjust_spins[key]
        lbl.setText(label)
        if self._block:
            return
        values = self.adjust_values()
        self._check_preset("none" if not values else "")
        self.adjust_changed.emit(values, "none" if not values else "custom")

    def _emit(self, *_):
        if not self._block:
            self.changed.emit()
