"""Lite projects, overlay presets, and project settings."""
from __future__ import annotations

import json
import os

from PySide6.QtWidgets import QFileDialog, QInputDialog

from jela.core.dub_project import load_json, save_preset, save_project, write_project
from jela.gui.dialogs.project_settings_dialog import ProjectSettingsDialog
from jela.gui.views.studio.tasks import STAGES

_SESSION_KEY = "project_session"


class ProjectTools:
    """Project info, templates, and lite project files."""

    def _apply_template(self, path: str):
        try:
            data = load_json(path)
        except Exception as exc:
            self.log.warn(f"Template failed · {exc}")
            return
        self.timeline.replace_overlay_clips(data.get("overlays") or [])
        self.log.info(f"Template · {data.get('name', os.path.basename(path))}")
        self._sync_preview_overlays(force=True)

    def _save_overlay_preset(self):
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name")
        if not ok or not name.strip():
            return
        path = save_preset(name.strip(), self.timeline.export_overlays(include_hidden=True))
        self.log.success(f"Preset saved · {os.path.basename(path)}")

    def _tools_payload(self) -> dict:
        if hasattr(self, "_stash_composition"):
            self._stash_composition()
        return {
            "compositions": [dict(comp) for comp in getattr(self, "_compositions", [])],
            "composition_index": getattr(self, "_composition_index", -1),
            "tasks": self._tasks_for_save(),
            "media": self.selected_file,
            "source_language": self.combo_source_lang.currentText(),
            "language": self.combo_lang.currentText(),
            "voice": self.combo_voice.currentData() or "",
            "secondary_voice": self.combo_voice_sec.currentData() or "",
            "translator": self.combo_translator.currentData() or "auto",
            "ollama_model": self.edit_ollama.text().strip(),
            "asr_model": self.combo_model.currentText(),
            "background": self.slider_duck.value(),
            "sync_mode": self.combo_sync_mode.currentData() or "stretch",
            "auto_chain": self.chk_auto_chain.isChecked(),
            "vocal_master": self.chk_vocal_master.isChecked(),
            "center_attenuation": self.slider_center_att.value(),
            "voiceover_boost": self.slider_vo_boost.value(),
            "fade_ms": self.slider_fade_ms.value(),
            "overlays": self.timeline.export_overlays(include_hidden=True),
            "fx": self.timeline.export_fx(include_hidden=True),
            "tracks": self.timeline.export_tracks(),
            "segments": list(self._segments),
            "output": self._output_path,
            "stems": self._current_stems(),
            "footage": self.timeline.export_footage(),
            "takes": self.timeline.export_takes(),
            "project": dict(self._project),
        }

    def _current_stems(self) -> dict:
        comps = getattr(self, "_compositions", [])
        index = getattr(self, "_composition_index", -1)
        if 0 <= index < len(comps):
            return {"bed": comps[index].get("bed", ""), "dialogue": comps[index].get("dialogue", "")}
        return {}

    def _apply_tools_payload(self, data: dict):
        if not isinstance(data, dict):
            return
        self._restoring_project = True
        try:
            self._set_combo_text(self.combo_source_lang, data.get("source_language"))
            self._set_combo_text(self.combo_lang, data.get("language"))
            self._set_combo_text(self.combo_model, data.get("asr_model"))
            self._set_combo_data(self.combo_translator, data.get("translator"))
            self._set_combo_data(self.combo_sync_mode, data.get("sync_mode"))
            self._set_combo_data(self.combo_voice, data.get("voice"))
            self._set_combo_data(self.combo_voice_sec, data.get("secondary_voice"))
            if data.get("ollama_model"):
                self.edit_ollama.setText(str(data["ollama_model"]))
            self._set_check(self.chk_auto_chain, data.get("auto_chain"))
            self._set_check(self.chk_vocal_master, data.get("vocal_master"))
            self._set_slider(self.slider_duck, data.get("background"))
            self._set_slider(self.slider_center_att, data.get("center_attenuation"))
            self._set_slider(self.slider_vo_boost, data.get("voiceover_boost"))
            self._set_slider(self.slider_fade_ms, data.get("fade_ms"))
            if isinstance(data.get("project"), dict):
                self._project.update(data["project"])
            media = str(data.get("media") or "")
            if media and os.path.isfile(media):
                if media != self.selected_file:
                    self.set_dub_source(media)
                self.timeline.set_media(media)
                self.show_timeline_player()
            segments = data.get("segments")
            if isinstance(segments, list) and segments:
                self._fill_table(segments)
            if isinstance(data.get("takes"), list):
                self.timeline.apply_takes(data["takes"])
            comps = data.get("compositions")
            legacy_overlays = data.get("overlays") if isinstance(data.get("overlays"), list) else None
            legacy_fx = data.get("fx") if isinstance(data.get("fx"), list) else None
            legacy_tracks = data.get("tracks") if isinstance(data.get("tracks"), list) else None
            if isinstance(comps, list) and comps:
                self._restore_compositions(
                    comps, data.get("composition_index"), data.get("tasks"),
                    legacy_overlays=legacy_overlays, legacy_fx=legacy_fx, legacy_tracks=legacy_tracks,
                )
                self._refresh_project_info()
                self._sync_preview_overlays(force=True)
                return
            if legacy_tracks:
                self.timeline.apply_tracks(legacy_tracks)
            if legacy_overlays is not None:
                self.timeline.replace_overlay_clips(legacy_overlays)
            if legacy_fx is not None:
                self.timeline.apply_fx(legacy_fx)
            output = str(data.get("output") or "")
            has_clips = isinstance(segments, list) and any(
                isinstance(seg, dict) and os.path.isfile(str(seg.get("audio_path") or "")) for seg in segments
            )
            if (output and os.path.isfile(output)) or has_clips:
                if output and not os.path.isfile(output):
                    output = ""
                stems = data.get("stems") if isinstance(data.get("stems"), dict) else {}
                self._remember_composition(
                    output,
                    segments if isinstance(segments, list) else [],
                    media,
                    str(data.get("language") or ""),
                    str(data.get("voice") or ""),
                    bed=str(stems.get("bed") or ""),
                    dialogue=str(stems.get("dialogue") or ""),
                    footage=data.get("footage") if isinstance(data.get("footage"), list) else None,
                )
                if legacy_overlays:
                    self.timeline.replace_overlay_clips(legacy_overlays)
                if legacy_fx:
                    self.timeline.apply_fx(legacy_fx)
                self._stash_composition()
            else:
                self._sync_timeline_visibility()
            self._refresh_project_info()
            self._sync_preview_overlays(force=True)
        finally:
            self._restoring_project = False

    def _tasks_for_save(self) -> list[dict]:
        saved = []
        for task in getattr(self, "_tasks", []):
            item = {k: v for k, v in task.items() if k not in {"control", "live", "live_clip"}}
            if item.get("status") in {"running", "paused", "queued"}:
                item["status"] = "cancelled"
                item["message"] = "Stopped when the tool closed"
            saved.append(item)
        return saved

    @staticmethod
    def _composition_usable(comp: dict) -> bool:
        output = str(comp.get("output") or "")
        if output and os.path.isfile(output):
            return True
        return any(
            isinstance(seg, dict) and os.path.isfile(str(seg.get("audio_path") or ""))
            for seg in comp.get("segments") or []
        )

    def _restore_compositions(
        self, comps: list, index, tasks,
        *, legacy_overlays=None, legacy_fx=None, legacy_tracks=None,
    ) -> None:
        kept: list[dict] = []
        remap: dict[int, int] = {}
        for old, comp in enumerate(comps):
            if not isinstance(comp, dict) or not self._composition_usable(comp):
                continue
            comp = dict(comp)
            if comp.get("output") and not os.path.isfile(str(comp["output"])):
                comp["output"] = ""
            remap[old] = len(kept)
            kept.append(comp)
        self._compositions = kept
        self._composition_index = remap.get(index if isinstance(index, int) else -1, len(kept) - 1)
        self._tasks = []
        self._task_seq = 0
        self._active_task = -1
        for task in tasks if isinstance(tasks, list) else []:
            if not isinstance(task, dict):
                continue
            self._task_seq += 1
            item = dict(task)
            item["id"] = self._task_seq
            stages = list(item.get("stages") or [])[: len(STAGES)]
            item["stages"] = stages + [-1] * (len(STAGES) - len(stages))
            item.setdefault("stage", -1)
            item.setdefault("message", "")
            old = item.get("comp", -1)
            item["comp"] = remap.get(old, -1) if isinstance(old, int) else -1
            if item.get("status") == "done" and item["comp"] < 0:
                item["status"] = "failed"
                item["message"] = "Dub files were removed"
            self._tasks.append(item)
        linked = {task["comp"] for task in self._tasks}
        for i, comp in enumerate(kept):
            if i not in linked:
                self._add_task(str(comp.get("source") or ""), status="done", comp=i)
        if kept:
            self.timeline.set_compositions([c.get("name", "") for c in kept], self._composition_index)
            self._apply_composition(
                self._composition_index,
                legacy_overlays=legacy_overlays,
                legacy_fx=legacy_fx,
                legacy_tracks=legacy_tracks,
            )
        else:
            self._sync_timeline_visibility()
        self._refresh_tasks()

    def _set_combo_text(self, combo, value):
        if value in (None, ""):
            return
        index = combo.findText(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _set_combo_data(self, combo, value):
        if value in (None, ""):
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _set_check(self, box, value):
        if value is None:
            return
        checked = value if isinstance(value, bool) else str(value) in {"1", "true", "True"}
        if box.isChecked() != checked:
            box.setChecked(checked)

    def _set_slider(self, slider, value):
        if value is None:
            return
        try:
            number = int(value)
        except (TypeError, ValueError):
            return
        if slider.value() != number:
            slider.setValue(number)

    def _store_project_session(self):
        if getattr(self, "_restoring_project", False) or not hasattr(self, "combo_lang"):
            return
        payload = self._tools_payload()
        self.store.set_setting("dub", _SESSION_KEY, json.dumps(payload, ensure_ascii=False))
        path = str(self._project.get("path") or "")
        name = str(self._project.get("name") or "dub")
        if path and os.path.isfile(path):
            try:
                write_project(path, name, payload)
            except Exception as exc:
                self.log.warn(f"Project store failed · {exc}")

    def _restore_project_session(self):
        if getattr(self, "_startup_project_path", ""):
            return
        raw = self.store.get_setting("dub", _SESSION_KEY, "") or ""
        if not raw:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        self._apply_tools_payload(data)

    def open_startup_project(self, path: str):
        """Load a project file chosen from the home screen."""
        if not path or not os.path.isfile(path):
            self.log.warn(f"Project missing · {path}")
            return
        try:
            data = load_json(path)
        except Exception as exc:
            self.log.warn(f"Project failed · {exc}")
            return
        self._startup_project_path = path
        if data.get("name"):
            self._project["name"] = data["name"]
        self._project["path"] = path
        project = data.get("project") if isinstance(data.get("project"), dict) else {}
        if project:
            self._project.update(project)
            self._project["path"] = path
        self._apply_tools_payload(data)
        self._store_project_session()
        self._refresh_project_info()
        self.log.info(f"Opened · {os.path.basename(path)}")

    def _save_lite_project(self):
        name, ok = QInputDialog.getText(
            self, "Save lite project", "Project name",
            text=self._project.get("name") or os.path.splitext(os.path.basename(self.selected_file or "dub"))[0],
        )
        if not ok or not name.strip():
            return
        path = save_project(name.strip(), self._tools_payload())
        self._project["name"] = name.strip()
        self._project["path"] = path
        self._store_project_session()
        self._refresh_project_info()
        self.log.success(f"Lite project · {os.path.basename(path)}")

    def _open_lite_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open lite project", str(self._project.get("save_to") or os.path.expanduser("~")),
            "Jela lite project (*.jela.json *.json)",
        )
        if not path:
            return
        try:
            data = load_json(path)
        except Exception as exc:
            self.log.warn(f"Project failed · {exc}")
            return
        if data.get("name"):
            self._project["name"] = data["name"]
        self._project["path"] = path
        self._apply_tools_payload(data)
        self._store_project_session()
        self.log.info(f"Opened · {os.path.basename(path)}")

    def _refresh_project_info(self):
        self.project_info.bind(self._project, self._media_info)
        dock = self.workspace.dock("preview") if hasattr(self, "workspace") else None
        if dock:
            name = str(self._project.get("timeline_name") or self._project.get("name") or "Timeline 01")
            dock.setWindowTitle(f"Preview · {name}")

    def _open_project_settings(self):
        dlg = ProjectSettingsDialog(self._project, self)
        if dlg.exec():
            self._project = dlg.result_settings()
            self._refresh_project_info()
            self.log.info("Project settings updated")
