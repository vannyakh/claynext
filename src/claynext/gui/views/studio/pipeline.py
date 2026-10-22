"""Start, progress, and finish the dubbing job."""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices

from claynext.models.dubbing_service import DubbingEngine
from claynext.utils.job_control import JobControl
from claynext.gui.worker import Worker
from claynext.gui.views.studio.captions import is_managed_caption
from claynext.utils.config import OUTPUTS_DIR


def _format_cue(seconds: float) -> str:
    ms = int(round(max(0.0, float(seconds)) * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, milli = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milli:03d}"


class PipelineTools:
    """Background dubbing job and the finished file."""

    def _open_api_keys(self):
        win = self.window()
        if win is not None and hasattr(win, "open_settings_dialog"):
            win.open_settings_dialog("API Keys")
            return
        from claynext.gui.dialogs.settings_dialog import SettingsDialog

        dlg = SettingsDialog(self)
        for i in range(dlg.tabs.count()):
            if dlg.tabs.tabText(i).replace("&", "").lower() == "api keys":
                dlg.tabs.setCurrentIndex(i)
                break
        dlg.exec()

    def start_dubbing(self):
        sources = self._dub_sources()
        if not sources:
            self._show_error(
                "No media",
                "Select one or more movies in the Media library, then start localization.",
            )
            self.log.warn("Localization blocked — no media selected")
            return

        from PySide6.QtWidgets import QDialog
        from claynext.gui.dialogs.start_localize_dialog import StartLocalizeDialog

        dlg = StartLocalizeDialog(self, sources=sources, defaults=self._start_dub_defaults())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.options()
        self._apply_start_dub_options(opts)
        self.store.set_setting("dub", "batch_mode", opts.get("batch_mode") or "separate")

        voice_id = self.combo_voice.currentData()
        if not voice_id:
            self._show_error("No voice", "Choose a voice.")
            return

        # Environment preflight runs in StartLocalizeDialog before Accept.

        # Dedicated: one sequence and one job per movie.
        # Merge: one sequence, a job per movie, then each movie lands on the master track.
        layout = "merge" if len(sources) >= 2 and opts.get("batch_mode") == "merge" else "separate"
        self._begin_dub_jobs(sources, layout=layout)

    def _begin_dub_jobs(self, sources: list[str], layout: str = "separate"):
        """Queue sources and launch the first dub job."""
        self._batch_layout = "merge" if layout == "merge" and len(sources) >= 2 else "separate"
        self._merge_open = self._batch_layout == "merge"
        self._merge_offsets = {}
        self._merge_durations = {}
        self._merge_seq_tokens = {}
        self._merge_layout_wait = []
        self._merge_comp_index = -1
        self._batch_failed = []
        self._flight = {}
        self._batch_stopping = False
        self._dub_queue = list(sources)
        self.set_dub_source(sources[0])
        self._queue_tasks(sources)
        self._clear_error()
        self._fill_table([])
        self._set_busy(True)
        if hasattr(self, "workspace"):
            self._focus_script_shelf()
        plan = self._load_hardware_plan()
        self.log.info(
            f"Hardware · {plan['logical_cores']} threads · {plan['physical_cores']} cores · "
            f"{plan['dub_jobs']} movies at once · {plan['tts_workers']} voice workers"
        )
        if self._merge_open:
            self._detach_other_sequence()
            self.log.info(
                f"Merge movie · {len(sources)} jobs · one sequence · master track"
            )
            self._measure_merge_sources(sources)
            return
        if len(sources) > 1:
            self.log.info(
                f"Dedicated · {len(sources)} sequences · "
                f"{self._batch_width()} at a time"
            )
        # Paint the queue first. The movie job starts on the next turn.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._launch_next_or_finish)

    def _start_dub_defaults(self) -> dict:
        try:
            caption_y = int(self.store.get_setting("dub", "caption_y", "86"))
        except (TypeError, ValueError):
            caption_y = 86
        return {
            "source_lang": self.combo_source_lang.currentText(),
            "target_lang": self.combo_lang.currentText(),
            "voice": self.combo_voice.currentData() or "",
            "secondary_voice": self.combo_voice_sec.currentData() or "",
            "asr_model": self.combo_model.currentText(),
            "translator": self.combo_translator.currentData() or "auto",
            "ollama_model": self.edit_ollama.text().strip() if hasattr(self, "edit_ollama") else "qwen3:8b",
            "sync_mode": self.combo_sync_mode.currentData() or "stretch",
            "background": self.slider_duck.value(),
            "center_attenuation": self.slider_center_att.value(),
            "voiceover_boost": self.slider_vo_boost.value(),
            "fade_ms": self.slider_fade_ms.value(),
            "auto_chain": bool(getattr(self, "chk_auto_chain", None) and self.chk_auto_chain.isChecked()),
            "auto_captions": bool(getattr(self, "chk_auto_captions", None) and self.chk_auto_captions.isChecked()),
            "caption_look": self.store.get_setting("dub", "caption_look", "") or "",
            "caption_lock": self.store.get_setting("dub", "caption_lock", "0") == "1",
            "caption_anim": self.store.get_setting("dub", "caption_anim", "none") or "none",
            "caption_fit": self.store.get_setting("dub", "caption_fit", "1") == "1",
            "caption_y": caption_y,
            "picture_effect": self.store.get_setting("dub", "picture_effect", "none") or "none",
            "picture_filter": self.store.get_setting("dub", "picture_filter", "clean") or "clean",
            "picture_transition": self.store.get_setting("dub", "picture_transition", "none") or "none",
            "export_srt": self.store.get_setting("dub", "export_srt", "0") == "1",
            "gender_detect": self.store.get_setting("dub", "gender_detect", "1") == "1",
            "translate_fit_duration": self.store.get_setting("dub", "translate_fit_duration", "1") == "1",
            "translate_slang": self.store.get_setting("dub", "translate_slang", "1") == "1",
            "translate_expression": self.store.get_setting("dub", "translate_expression", "1") == "1",
            "auto_mix": bool(getattr(self, "chk_auto_mix", None) and self.chk_auto_mix.isChecked()),
            "vocal_master": bool(getattr(self, "chk_vocal_master", None) and self.chk_vocal_master.isChecked()),
            # Default: dedicated tasks — merge is opt-in for episode → one movie.
            "batch_mode": self.store.get_setting("dub", "batch_mode", "separate") or "separate",
            "speed_preset": self.store.get_setting("dub", "speed_preset", "balanced") or "balanced",
            "clone_voices": self.store.get_setting("dub", "clone_voices", "1") == "1",
        }

    def _apply_start_dub_options(self, opts: dict):
        """Push confirm-dialog choices onto hidden Dub settings + store."""
        source = opts.get("source_lang") or ""
        target = opts.get("target_lang") or ""
        if source and hasattr(self, "combo_source_lang"):
            self.combo_source_lang.setCurrentText(source)
            self.store.set_setting("dub", "source_language", source)
        if target and hasattr(self, "combo_lang"):
            self.combo_lang.setCurrentText(target)
            self.store.set_setting("dub", "language", target)

        if hasattr(self, "_fill_voices") and target:
            self._fill_voices(target)
        self._set_combo_data(self.combo_voice, opts.get("voice"))
        self._set_combo_data(self.combo_voice_sec, opts.get("secondary_voice"))
        if self.combo_voice.currentData():
            self.store.set_setting("dub", "voice", self.combo_voice.currentData())
        if self.combo_voice_sec.currentData():
            self.store.set_setting("dub", "secondary_voice", self.combo_voice_sec.currentData())

        model = opts.get("asr_model") or ""
        if model and hasattr(self, "combo_model"):
            self.combo_model.setCurrentText(model)
            self.store.set_setting("dub", "asr_model", model)

        translator = opts.get("translator") or "auto"
        if hasattr(self, "combo_translator"):
            idx = self.combo_translator.findData(translator)
            if idx >= 0:
                self.combo_translator.setCurrentIndex(idx)
            self.store.set_setting("dub", "translator", translator)

        if hasattr(self, "edit_ollama"):
            ollama = str(opts.get("ollama_model") or "qwen3:8b").strip() or "qwen3:8b"
            self.edit_ollama.setText(ollama)
            self.store.set_setting("dub", "ollama_model", ollama)

        sync = opts.get("sync_mode") or "stretch"
        if hasattr(self, "combo_sync_mode"):
            idx = self.combo_sync_mode.findData(sync)
            if idx >= 0:
                self.combo_sync_mode.setCurrentIndex(idx)
            self.store.set_setting("dub", "sync_mode", sync)

        duck = int(opts.get("background", self.slider_duck.value()))
        if hasattr(self, "slider_duck"):
            self.slider_duck.setValue(duck)
            self.store.set_setting("dub", "background", str(duck))

        for key, spin in (
            ("center_attenuation", getattr(self, "slider_center_att", None)),
            ("voiceover_boost", getattr(self, "slider_vo_boost", None)),
            ("fade_ms", getattr(self, "slider_fade_ms", None)),
        ):
            if spin is None or opts.get(key) is None:
                continue
            spin.setValue(int(opts[key]))
            self.store.set_setting("dub", key, str(int(opts[key])))

        if opts.get("speed_preset"):
            self.store.set_setting("dub", "speed_preset", str(opts.get("speed_preset")))
        self._apply_start_check(getattr(self, "chk_auto_chain", None), opts.get("auto_chain"), "auto_chain")
        self._apply_start_check(getattr(self, "chk_auto_captions", None), opts.get("auto_captions"), "auto_captions")
        self._apply_start_check(getattr(self, "chk_auto_mix", None), opts.get("auto_mix"), "auto_mix")
        self._apply_start_check(getattr(self, "chk_vocal_master", None), opts.get("vocal_master"), "vocal_master")
        self._apply_start_check(None, opts.get("export_srt"), "export_srt")
        self._apply_start_check(None, opts.get("gender_detect"), "gender_detect")
        if "clone_voices" in opts:
            self.store.set_setting("dub", "clone_voices", "1" if opts.get("clone_voices") else "0")
        self._apply_start_check(
            getattr(self, "chk_translate_fit", None),
            opts.get("translate_fit_duration"),
            "translate_fit_duration",
        )
        self._apply_start_check(
            getattr(self, "chk_translate_slang", None),
            opts.get("translate_slang"),
            "translate_slang",
        )
        self._apply_start_check(
            getattr(self, "chk_translate_expression", None),
            opts.get("translate_expression"),
            "translate_expression",
        )
        self._apply_start_check(None, opts.get("caption_lock"), "caption_lock")
        self._apply_caption_start_options(opts)

    def _apply_caption_start_options(self, opts: dict):
        """Push Captions-tab choices into store + Captions shelf widgets."""
        look = str(opts.get("caption_look") or "").strip()
        if look:
            self.store.set_setting("dub", "caption_look", look)
        anim = str(opts.get("caption_anim") or "none")
        self.store.set_setting("dub", "caption_anim", anim)
        fit = bool(opts.get("caption_fit", True))
        self.store.set_setting("dub", "caption_fit", "1" if fit else "0")
        try:
            caption_y = int(opts.get("caption_y", 86))
        except (TypeError, ValueError):
            caption_y = 86
        self.store.set_setting("dub", "caption_y", str(caption_y))
        effect = str(opts.get("picture_effect") or "none")
        look = str(opts.get("picture_filter") or "clean")
        transition = str(opts.get("picture_transition") or "none")
        self.store.set_setting("dub", "picture_effect", effect)
        self.store.set_setting("dub", "picture_filter", look)
        self.store.set_setting("dub", "picture_transition", transition)

        if look and hasattr(self, "caption_look_grid"):
            from claynext.gui.views.studio.captions import CAPTION_STYLES
            idx = next(
                (i for i, s in enumerate(CAPTION_STYLES) if str(s.get("name") or "") == look),
                -1,
            )
            if idx >= 0:
                self.caption_look_grid.set_current(idx)

        if hasattr(self, "caption_motion_grid"):
            from claynext.models.text_style import CAPTION_ANIMS
            anim_idx = next((i for i, (key, _) in enumerate(CAPTION_ANIMS) if key == anim), 0)
            self.caption_motion_grid.set_current(anim_idx)
        elif hasattr(self, "caption_anim_group"):
            from claynext.models.text_style import CAPTION_ANIMS
            anim_idx = next((i for i, (key, _) in enumerate(CAPTION_ANIMS) if key == anim), 0)
            btn = self.caption_anim_group.button(anim_idx)
            if btn is not None:
                btn.setChecked(True)

        if hasattr(self, "chk_caption_fit"):
            self.chk_caption_fit.blockSignals(True)
            self.chk_caption_fit.setChecked(fit)
            self.chk_caption_fit.blockSignals(False)
        if hasattr(self, "spin_caption_y"):
            self.spin_caption_y.blockSignals(True)
            self.spin_caption_y.setValue(caption_y)
            self.spin_caption_y.blockSignals(False)

    def _apply_start_check(self, box, value, setting: str):
        if value is None:
            return
        checked = bool(value)
        if box is not None:
            box.blockSignals(True)
            box.setChecked(checked)
            box.blockSignals(False)
        self.store.set_setting("dub", setting, "1" if checked else "0")

    def _source_already_on_track(self, path: str) -> bool:
        if not path or not hasattr(self, "timeline"):
            return False
        canvas = self.timeline.canvas
        target = os.path.normcase(os.path.abspath(path))
        current_media = os.path.normcase(os.path.abspath(canvas.media_path or ""))
        on_track = any(
            clip.kind == "video"
            and os.path.normcase(os.path.abspath(str(clip.extra.get("path") or ""))) == target
            for clip in canvas.clips
        )
        return on_track and current_media == target

    def _ensure_source_sequence(self, path: str) -> None:
        """Probe the movie off the interface thread, then place it on Source."""
        if not path or not os.path.isfile(path) or not hasattr(self, "timeline"):
            return
        if getattr(self, "_merge_open", False):
            self._queue_merge_source(path)
            return
        abspath = os.path.normcase(os.path.abspath(path))
        if self._source_already_on_track(abspath):
            return
        if getattr(self, "_source_seq_path", "") == abspath:
            return
        self._source_seq_path = abspath
        token = int(getattr(self, "_source_seq_token", 0)) + 1
        self._source_seq_token = token

        def probe(progress_callback=None):
            from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter
            return int(get_ffmpeg_adapter().duration(abspath) * 1000)

        worker = Worker(probe)
        worker.signals.result.connect(
            lambda ms, media=abspath, seq=token: self._apply_source_sequence(media, int(ms or 0), seq)
        )
        worker.signals.error.connect(
            lambda *_err, media=abspath, seq=token: self._apply_source_sequence(media, 0, seq)
        )
        pending = getattr(self, "_source_seq_workers", None)
        if not isinstance(pending, list):
            pending = []
            self._source_seq_workers = pending
        pending.append(worker)

        def _release(done=worker):
            held = getattr(self, "_source_seq_workers", None)
            if isinstance(held, list) and done in held:
                held.remove(done)

        worker.signals.finished.connect(_release)
        self._source_seq_worker = worker
        pool = getattr(self, "thread_pool", None)
        if pool is None:
            from PySide6.QtCore import QThreadPool
            pool = QThreadPool.globalInstance()
        pool.start(worker)

    def _apply_source_sequence(self, path: str, duration_ms: int, token: int) -> None:
        if token != int(getattr(self, "_source_seq_token", 0)):
            return
        norm_path = os.path.normcase(os.path.abspath(path))
        if getattr(self, "_source_seq_path", "") == norm_path:
            self._source_seq_path = ""
        if not path or not os.path.isfile(path) or not hasattr(self, "timeline"):
            return
        if self._source_already_on_track(path):
            return
        if duration_ms > 0:
            self.timeline.set_media(path, duration_ms)
        else:
            self.timeline.set_media(path)
        self._timeline_open = True
        if hasattr(self, "_sync_timeline_visibility"):
            self._sync_timeline_visibility()
        self._live_paint_keys = None
        segments = [seg for seg in (getattr(self, "_segments", None) or []) if isinstance(seg, dict)]
        if segments and hasattr(self.timeline, "sync_dialogue"):
            self.timeline.sync_dialogue(segments)
        self.log.info(f"Source on track · {os.path.basename(path)}")
        if hasattr(self, "show_timeline_player") and not getattr(self, "_merge_open", False):
            self.show_timeline_player()

    def _merge_duration_ms(self, path: str) -> int:
        stored = int((getattr(self, "_merge_durations", {}) or {}).get(path) or 0)
        if stored > 0:
            return stored
        if not hasattr(self, "timeline"):
            return 0
        for clip in self.timeline.canvas.master_clips():
            if os.path.abspath(str(clip.extra.get("path") or "")) == path:
                return int(clip.duration_ms or 0)
        return 0

    def _queue_merge_source(self, path: str) -> None:
        """Place this movie at the end of the one merge sequence. Do not replace the master."""
        if not path or not os.path.isfile(path) or not hasattr(self, "timeline"):
            return
        abspath = os.path.abspath(path)
        offsets = getattr(self, "_merge_offsets", None)
        if not isinstance(offsets, dict):
            offsets = {}
            self._merge_offsets = offsets
        durations = getattr(self, "_merge_durations", None)
        if not isinstance(durations, dict):
            durations = {}
            self._merge_durations = durations
        existing = next(
            (
                clip for clip in self.timeline.canvas.master_clips()
                if os.path.abspath(str(clip.extra.get("path") or "")) == abspath
            ),
            None,
        )
        if existing is not None:
            offsets.setdefault(abspath, int(existing.start_ms))
            durations.setdefault(abspath, int(existing.duration_ms or 0))
            return
        if abspath in offsets:
            return
        waiting = getattr(self, "_merge_layout_wait", None)
        if not isinstance(waiting, list):
            waiting = []
            self._merge_layout_wait = waiting
        if any(self._merge_duration_ms(reserved) <= 0 for reserved in offsets):
            if abspath not in waiting:
                waiting.append(abspath)
            return
        span = self.timeline.canvas.master_span()
        offset = int(span[0] + span[1]) if span else 0
        for reserved, at in offsets.items():
            offset = max(offset, int(at) + self._merge_duration_ms(reserved))
        offsets[abspath] = offset
        tokens = getattr(self, "_merge_seq_tokens", None)
        if not isinstance(tokens, dict):
            tokens = {}
            self._merge_seq_tokens = tokens
        token = int(tokens.get(abspath) or 0) + 1
        tokens[abspath] = token

        def probe(progress_callback=None):
            from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter
            return int(get_ffmpeg_adapter().duration(abspath) * 1000)

        worker = Worker(probe)
        worker.signals.result.connect(
            lambda ms, media=abspath, at=offset, seq=token: self._apply_merge_source(
                media, int(ms or 0), at, seq,
            )
        )
        worker.signals.error.connect(
            lambda *_err, media=abspath, at=offset, seq=token: self._apply_merge_source(
                media, 1000, at, seq,
            )
        )
        self.thread_pool.start(worker)

    def _apply_merge_source(self, path: str, duration_ms: int, start_ms: int, token: int) -> None:
        tokens = getattr(self, "_merge_seq_tokens", None) or {}
        if int(tokens.get(path) or 0) != int(token):
            self._flush_merge_wait()
            return
        if not path or not os.path.isfile(path) or not hasattr(self, "timeline"):
            return
        durations = getattr(self, "_merge_durations", None)
        if not isinstance(durations, dict):
            durations = {}
            self._merge_durations = durations
        durations[path] = max(1, int(duration_ms or 0))
        self.timeline.append_master(path, durations[path], start_ms)
        self._timeline_open = True
        if hasattr(self, "_sync_timeline_visibility"):
            self._sync_timeline_visibility()
        name = os.path.basename(path)
        if start_ms <= 0:
            self.log.info(f"Master · {name}")
        else:
            self.log.info(f"Master · {name} at {start_ms / 1000:.1f}s")
        self._flush_merge_wait()

    def _flush_merge_wait(self) -> None:
        waiting = list(getattr(self, "_merge_layout_wait", []) or [])
        self._merge_layout_wait = []
        for media in waiting:
            self._queue_merge_source(media)

    def _detach_other_sequence(self) -> None:
        """Keep the open sequence saved, then leave the timeline free for this source."""
        index = int(getattr(self, "_composition_index", -1))
        compositions = list(getattr(self, "_compositions", None) or [])
        selected = os.path.abspath(getattr(self, "selected_file", "") or "")
        comp_source = ""
        if 0 <= index < len(compositions):
            comp_source = os.path.abspath(str(compositions[index].get("source") or ""))
            if hasattr(self, "_stash_composition"):
                self._stash_composition()
        self._composition_index = -1
        self._viewing_task = -1
        if not hasattr(self, "timeline"):
            return
        current = os.path.abspath(getattr(self.timeline.canvas, "media_path", "") or "")
        other_film = bool(selected) and (
            (bool(current) and current != selected)
            or (bool(comp_source) and comp_source != selected)
        )
        if other_film:
            # Drop it before the dub job reads overlays.
            self.timeline.drop_other_sequence(selected)
        names = [str(comp.get("name") or "") for comp in compositions]
        if names:
            self.timeline.set_compositions(names, -1)

    def _load_hardware_plan(self) -> dict:
        from claynext.adapters.resources import apply_process_threads, resource_plan

        plan = apply_process_threads(resource_plan())
        self._hardware_plan = plan
        return plan

    def _batch_width(self) -> int:
        plan = getattr(self, "_hardware_plan", None)
        if not isinstance(plan, dict):
            plan = self._load_hardware_plan()
        return max(1, int(plan.get("dub_jobs") or 1))

    def _measure_merge_sources(self, sources: list[str]) -> None:
        """Read every movie length off the UI thread, then lay them on the master in order."""
        self.log.info(f"Measuring {len(sources)} movies…")

        def work(progress_callback=None):
            from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter

            ff = get_ffmpeg_adapter()
            rows = []
            total = max(1, len(sources))
            for index, path in enumerate(sources):
                ms = int(float(ff.duration(path) or 0) * 1000)
                rows.append((os.path.abspath(path), max(1000, ms)))
                if progress_callback:
                    progress_callback(int((index + 1) * 100 / total), os.path.basename(path))
            return rows

        worker = Worker(work)
        worker.signals.result.connect(self._on_merge_measured)
        worker.signals.error.connect(lambda msg, _tb: self._on_merge_measure_failed(str(msg)))
        self.thread_pool.start(worker)

    def _on_merge_measured(self, rows) -> None:
        if not isinstance(rows, list):
            self._launch_next_or_finish()
            return
        offset = 0
        self._merge_offsets = {}
        for path, ms in rows:
            if not path:
                continue
            self._merge_offsets[path] = offset
            self.timeline.append_master(path, int(ms), offset)
            offset += int(ms)
        self.log.info(f"Master laid out · {len(self._merge_offsets)} movies · {offset / 1000:.1f}s")
        self._launch_next_or_finish()

    def _on_merge_measure_failed(self, message: str) -> None:
        self.log.warn(f"Could not measure movies · {message}")
        self._launch_next_or_finish()

    def _release_slot(self, path: str, task_id: int | None) -> None:
        flight = getattr(self, "_flight", None)
        if isinstance(flight, dict) and path:
            flight.pop(os.path.abspath(path), None)
        if path:
            self.selected_file = path
        if task_id is not None:
            self._active_task = task_id

    def _cancel_inflight(self) -> None:
        flight = getattr(self, "_flight", None)
        if not isinstance(flight, dict):
            return
        for slot in list(flight.values()):
            task = self._task_by_id(int(slot.get("task_id") or -1))
            control = task.get("control") if task else None
            if control is not None:
                control.cancel()

    def _halt_batch(self) -> None:
        if getattr(self, "_batch_stopping", False):
            return
        self._batch_stopping = True
        self._cancel_inflight()
        self._dub_queue = []
        self._merge_open = False
        self._set_busy(False)
        self._fail_tasks("Stopped", status="cancelled")
        self.log.info("Dub stopped")

    def _finish_job(self, path: str, task_id: int, res) -> None:
        self._release_slot(path, task_id)
        self._on_complete(res)

    def _fail_job(self, path: str, task_id: int, message: str, stack: str) -> None:
        self._release_slot(path, task_id)
        if str(message) == "Dub stopped" or getattr(self, "_batch_stopping", False):
            task = self._task_by_id(task_id)
            if task and task.get("status") in {"running", "paused"}:
                task["status"] = "cancelled"
                task["message"] = "Stopped"
                task.pop("control", None)
                self._refresh_tasks()
            self._halt_batch()
            return
        self._on_error(message, stack)

    def _launch_dub_job(self):
        from claynext.gui.views.studio.tasks import LiveBridge

        owns_script = not bool(getattr(self, "_flight", None))
        headless = not owns_script and not getattr(self, "_merge_open", False)
        # Dedicated swaps to a fresh sequence. Merge keeps the one sequence and appends.
        if getattr(self, "_merge_open", False):
            self._queue_merge_source(self.selected_file)
        elif not headless:
            self._detach_other_sequence()
            self._ensure_source_sequence(self.selected_file)

        # Don't let a script TTS/translate retry race the main dub worker
        if hasattr(self, "_cancel_script_job"):
            self._cancel_script_job()

        task = self._start_next_task(self.selected_file)
        control = JobControl()
        task["control"] = control
        # Own the script panel until this job's transcript list arrives.
        # Extra movies keep the script that is already on screen.
        if owns_script:
            self._segments = []
            self._live_paint_keys = None
            self._live_scroll_row = None
            self._script_follow_task = task["id"]
            if hasattr(self, "_set_script_loading"):
                self._set_script_loading(True, "Transcribing…", "Reading dialogue from the movie")
            if hasattr(self, "_fill_table"):
                # Clearing the script must not wipe voice lines already laid on the merge.
                self._skip_dialogue_sync = bool(getattr(self, "_merge_open", False))
                self._fill_table([])
                self._skip_dialogue_sync = False
        bridge = LiveBridge()
        bridge.event.connect(lambda kind, payload, tid=task["id"]: self._on_live_event(tid, kind, payload))
        self._live_bridge = bridge
        self._refresh_tasks()
        voice_id = self.combo_voice.currentData()
        source_lang = self.combo_source_lang.currentText()
        lang = self.combo_lang.currentText()
        sec_voice_id = self.combo_voice_sec.currentData() or ""
        model = self.combo_model.currentText()
        bg = self.slider_duck.value() / 100.0
        translator = self.combo_translator.currentData() or "auto"
        ollama_model = self.edit_ollama.text().strip() or "qwen3:8b"
        self.store.set_setting("dub", "translator", translator)
        self.store.set_setting("dub", "ollama_model", ollama_model)
        self.log.info(f"Starting dub · {source_lang} → {lang} · {voice_id} & {sec_voice_id} · {model} · {translator}")

        vocal_master = self.chk_vocal_master.isChecked()
        center_att = self.slider_center_att.value() / 100.0
        vo_boost = self.slider_vo_boost.value() / 100.0
        fade_ms = self.slider_fade_ms.value()
        sync_mode = self.combo_sync_mode.currentData() or "stretch"
        auto_chain = bool(getattr(self, "chk_auto_chain", None) and self.chk_auto_chain.isChecked())
        translate_fit = self.store.get_setting("dub", "translate_fit_duration", "1") == "1"
        translate_slang = self.store.get_setting("dub", "translate_slang", "1") == "1"
        translate_expression = self.store.get_setting("dub", "translate_expression", "1") == "1"
        plan = getattr(self, "_hardware_plan", None) or {}
        tts_workers = max(1, int(plan.get("tts_workers") or 1))
        media = os.path.abspath(self.selected_file)

        worker = Worker(
            DubbingEngine.process_dubbing,
            video_path=media,
            source_lang=source_lang,
            target_lang=lang,
            voice_id=voice_id,
            secondary_voice_id=sec_voice_id,
            background_vol=bg,
            asr_model=model,
            asr_language=source_lang,
            translator=translator,
            ollama_model=ollama_model,
            overlays=[] if not owns_script else self.timeline.export_overlays(),
            vocal_master=vocal_master,
            center_attenuation=center_att,
            voiceover_boost=vo_boost,
            fade_ms=fade_ms,
            sync_mode=sync_mode,
            auto_chain=auto_chain,
            render=False,
            control=control,
            live=bridge.send,
            translate_fit_duration=translate_fit,
            translate_slang=translate_slang,
            translate_expression=translate_expression,
            tts_workers=tts_workers,
        )
        worker.signals.progress.connect(
            lambda val, msg, tid=task["id"]: self._on_progress(val, msg, tid)
        )
        worker.signals.result.connect(
            lambda res, path=media, tid=task["id"]: self._finish_job(path, tid, res)
        )
        worker.signals.error.connect(
            lambda msg, stack, path=media, tid=task["id"]: self._fail_job(path, tid, msg, stack)
        )
        self._worker = worker
        flight = getattr(self, "_flight", None)
        if not isinstance(flight, dict):
            flight = {}
            self._flight = flight
        flight[media] = {"task_id": task["id"], "worker": worker, "bridge": bridge}
        self.thread_pool.start(worker)

    def _on_progress(self, val: int, msg: str, task_id: int | None = None):
        self._task_progress(val, msg, task_id=task_id)
        pinned = int(getattr(self, "_script_pinned", -1) or -1)
        follow = int(getattr(self, "_script_follow_task", -1) or -1)
        shown = pinned if pinned >= 0 else follow
        if task_id is not None and task_id != shown:
            return
        text = str(msg or "")
        task = self._task_by_id(task_id) if task_id is not None and hasattr(self, "_task_by_id") else None
        name = str(task.get("name") or "") if task else ""
        if name and text:
            text = f"{name} · {text}"
        elif name:
            text = name
        if hasattr(self, "_set_script_loading_hint"):
            self._set_script_loading_hint(text or f"{int(val)}%")
        self._set_footer_progress(True, int(val), text)
        self._set_window_status(
            f"{int(val)}% · {text}" if text else f"{int(val)}%",
            int(val),
        )
        from claynext.utils.console_noise import status_worth_logging

        if status_worth_logging(str(getattr(self, "_progress_logged", "") or ""), text):
            self._progress_logged = text
            self.log.info(text)

    def _on_complete(self, res: dict):
        if not res:
            self._skip_failed_movie("No result returned.")
            self._launch_next_or_finish()
            return
        segs = res.get("segments") or []
        if not segs:
            self._skip_failed_movie("No dubbed lines were produced.")
            self._launch_next_or_finish()
            return
        self._error = ""
        output = res.get("output_path") or ""
        count = res.get("segments_dubbed", len(segs))
        if getattr(self, "_merge_open", False):
            self._fold_merge_movie(res, segs, count, output)
            return
        owns = int(getattr(self, "_active_task", -1)) == int(getattr(self, "_script_follow_task", -1) or -1)
        wide = self._batch_width() > 1
        if hasattr(self, "workspace") and owns:
            self._focus_script_shelf()
        if wide and not owns:
            self._remember_composition(
                output,
                segs,
                self.selected_file,
                self.combo_lang.currentText(),
                self.combo_voice.currentText(),
                bed=str(res.get("bed_path") or ""),
                dialogue=str(res.get("dialogue_path") or ""),
                clean_audio=str(res.get("clean_audio") or ""),
                vocals=str(res.get("vocals_path") or ""),
                effects=str(res.get("effects_path") or ""),
                music=str(res.get("music_path") or ""),
                duck=True,
                apply=False,
                stash=False,
                select=False,
            )
            if self.chk_auto_captions.isChecked() and self._compositions:
                self._compositions[-1]["pending_captions"] = True
        else:
            others = bool(self._dub_queue) or (wide and bool(getattr(self, "_flight", None)))
            apply_now = (wide and owns) or not others
            self._remember_composition(
                output,
                segs,
                self.selected_file,
                self.combo_lang.currentText(),
                self.combo_voice.currentText(),
                bed=str(res.get("bed_path") or ""),
                dialogue=str(res.get("dialogue_path") or ""),
                clean_audio=str(res.get("clean_audio") or ""),
                vocals=str(res.get("vocals_path") or ""),
                effects=str(res.get("effects_path") or ""),
                music=str(res.get("music_path") or ""),
                duck=True,
                apply=apply_now,
            )
            if not apply_now and self.chk_auto_captions.isChecked() and self._compositions:
                self._compositions[-1]["pending_captions"] = True
            elif self.chk_auto_captions.isChecked():
                self._ensure_auto_captions(force=True)
            if apply_now:
                self._stash_composition()
        if self.store.get_setting("dub", "export_srt", "0") == "1" and (not wide or owns):
            self._auto_export_srt_on_finish()
        self._store_project_session()
        if output:
            self.log.success(f"Dubbed {count} line(s) → {os.path.basename(output)}")
        else:
            self.log.success(f"{count} voice clip(s) on the Voice track · use Export → Render dub to make the movie")
        self._launch_next_or_finish()

    def _shift_segments(self, segments: list, offset_ms: int) -> list[dict]:
        """Move one movie's cues onto the shared sequence clock."""
        from claynext.models.dubbing_service import timestamp_to_sec

        if offset_ms == 0:
            return [dict(seg) for seg in segments if isinstance(seg, dict)]
        shifted: list[dict] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            row = dict(seg)
            start = timestamp_to_sec(str(row.get("start") or "")) + offset_ms / 1000.0
            end = timestamp_to_sec(str(row.get("end") or "")) + offset_ms / 1000.0
            row["start"] = _format_cue(start)
            row["end"] = _format_cue(end)
            if row.get("start_ms") is not None:
                row["start_ms"] = max(0, int(row["start_ms"]) + offset_ms)
            shifted.append(row)
        return shifted

    def _fold_merge_movie(self, res: dict, segs: list, count: int, output: str) -> None:
        """Dub finished for one movie. Keep the sequence and extend the master."""
        source = os.path.abspath(self.selected_file or "")
        try:
            offset = int(getattr(self, "_merge_offsets", {}).get(source, 0))
            shifted = self._shift_segments(segs, offset)
            for row in shifted:
                row["source"] = source
            if hasattr(self.timeline, "place_source_dialogue"):
                self.timeline.place_source_dialogue(shifted, source)
            duck_val = self.slider_duck.value() / 100.0 if hasattr(self, "slider_duck") else 0.0
            if duck_val <= 0.02:
                duck_val = 0.0
            self.timeline.duck_level = duck_val
            self.timeline.duck_fade_ms = self.slider_fade_ms.value() if hasattr(self, "slider_fade_ms") else 150
            self.timeline.auto_duck(self.timeline.duck_level)
            lang = self.combo_lang.currentText() or "Dub"
            index = int(getattr(self, "_merge_comp_index", -1))
            comp = self._compositions[index] if 0 <= index < len(self._compositions) else None
            if comp is None or not comp.get("merged"):
                self._remember_composition(
                    output,
                    shifted,
                    source,
                    lang,
                    self.combo_voice.currentText(),
                    bed=str(res.get("bed_path") or ""),
                    dialogue=str(res.get("dialogue_path") or ""),
                    effects=str(res.get("effects_path") or ""),
                    music=str(res.get("music_path") or ""),
                    duck=False,
                    apply=False,
                )
                index = self._composition_index
                self._merge_comp_index = index
                comp = self._compositions[index]
                comp["merged"] = True
                comp["name"] = f"Merge · {lang}"
                comp["sources"] = [source]
                comp["segments"] = shifted
                self.timeline.set_compositions(
                    [item["name"] for item in self._compositions],
                    index,
                )
            else:
                comp["segments"] = list(comp.get("segments") or []) + shifted
                sources = [str(item) for item in (comp.get("sources") or [])]
                if source not in sources:
                    sources.append(source)
                comp["sources"] = sources
                self._composition_index = index
                self._link_task(index, source)
            self._segments = list(comp.get("segments") or [])
            if self.chk_auto_captions.isChecked():
                self._ensure_auto_captions(force=True)
            comp["masters"] = self.timeline.export_masters()
            self._stash_composition()
            if self.store.get_setting("dub", "export_srt", "0") == "1":
                self._auto_export_srt_on_finish()
            if output:
                self.log.success(f"Dubbed {count} line(s) → {os.path.basename(output)}")
            else:
                self.log.success(f"{count} voice clip(s) from this movie on the master sequence")
        except Exception as exc:
            task = self._task_by_id(self._active_task) if getattr(self, "_active_task", -1) >= 0 else None
            if task and task.get("status") in {"running", "paused"}:
                self._skip_failed_movie(str(exc))
            else:
                self.log.warn(f"Sequence update failed · {exc}")
        self._launch_next_or_finish()

    def _skip_failed_movie(self, message: str) -> None:
        """Record one failed movie and, on a merge, lift it off the master track."""
        source = os.path.abspath(self.selected_file or "")
        self._fail_source(source, message)
        failed = getattr(self, "_batch_failed", None)
        if not isinstance(failed, list):
            failed = []
            self._batch_failed = failed
        failed.append((source, message))
        name = os.path.basename(source) or "Movie"
        if getattr(self, "_merge_open", False):
            tokens = getattr(self, "_merge_seq_tokens", None)
            if not isinstance(tokens, dict):
                tokens = {}
                self._merge_seq_tokens = tokens
            tokens[source] = int(tokens.get(source) or 0) + 1
            offsets = getattr(self, "_merge_offsets", None)
            if isinstance(offsets, dict):
                offsets.pop(source, None)
            durations = getattr(self, "_merge_durations", None)
            if isinstance(durations, dict):
                durations.pop(source, None)
            waiting = getattr(self, "_merge_layout_wait", None)
            if isinstance(waiting, list):
                self._merge_layout_wait = [item for item in waiting if item != source]
            if source and hasattr(self.timeline, "drop_master"):
                self.timeline.drop_master(source)
            self._flush_merge_wait()
            self.log.warn(f"Skipped · {name} · {message}")
            return
        self.log.error(f"Dubbing failed · {name} · {message}")

    def _launch_next_or_finish(self) -> None:
        """Fill free slots from the queue. Stop, or an empty queue and flight, ends the batch."""
        if getattr(self, "_batch_stopping", False):
            return
        flight = getattr(self, "_flight", None)
        if not isinstance(flight, dict):
            flight = {}
            self._flight = flight
        width = self._batch_width()
        while len(flight) < width and self._dub_queue:
            nxt = self._dub_queue.pop(0)
            if not nxt or not os.path.isfile(nxt):
                self.selected_file = nxt or ""
                self._skip_failed_movie("File missing")
                continue
            self.selected_file = nxt
            left = len(self._dub_queue) + len(flight) + 1
            name = os.path.basename(nxt)
            if getattr(self, "_merge_open", False):
                self.log.info(f"Merge next · {name} · {left} left")
            else:
                self.log.info(f"Auto chain next · {name} · {left} left")
            try:
                self._launch_dub_job()
            except Exception as exc:
                self._skip_failed_movie(str(exc))
        if not self._dub_queue and not flight and not getattr(self, "_batch_stopping", False):
            self._end_batch()

    def _compact_merge(self) -> None:
        """Close gaps from skipped movies and move each movie's lines with its master clip."""
        index = int(getattr(self, "_merge_comp_index", -1))
        if not (0 <= index < len(getattr(self, "_compositions", []) or [])):
            return
        self._composition_index = index
        deltas = self.timeline.repack_masters() if hasattr(self.timeline, "repack_masters") else {}
        comp = self._compositions[index]
        adjusted: list[dict] = []
        for seg in comp.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            source = os.path.abspath(str(seg.get("source") or ""))
            delta = int((deltas or {}).get(source) or 0)
            if delta:
                adjusted.extend(self._shift_segments([seg], delta))
            else:
                adjusted.append(dict(seg))
        comp["segments"] = adjusted
        self._segments = adjusted
        if self.chk_auto_captions.isChecked():
            self._ensure_auto_captions(force=True)
        if hasattr(self.timeline, "export_masters"):
            comp["masters"] = self.timeline.export_masters()
        self._stash_composition()
        self._fill_table(adjusted)

    def _end_batch(self) -> None:
        if getattr(self, "_batch_stopping", False):
            return
        failed = list(getattr(self, "_batch_failed", []) or [])
        merging = bool(getattr(self, "_merge_open", False))
        if merging:
            self._compact_merge()
        self._merge_open = False
        if merging and getattr(self, "_segments", None):
            self._fill_table(self._segments)
            index = int(getattr(self, "_merge_comp_index", -1))
            sources = []
            if 0 <= index < len(self._compositions):
                sources = list(self._compositions[index].get("sources") or [])
            if sources:
                note = f"Merge sequence ready · {len(sources)} movies on the master track"
                if failed:
                    note += f" · {len(failed)} skipped"
                self.log.success(note)
        self._store_project_session()
        self._set_busy(False)
        if not failed:
            return
        preview = failed[:12]
        lines = [
            f"{os.path.basename(path) or 'Movie'} · {msg}"
            for path, msg in preview
        ]
        extra = len(failed) - len(preview)
        if extra > 0:
            lines.append(f"… and {extra} more")
        done = sum(1 for task in getattr(self, "_tasks", []) if task.get("status") == "done")
        title = "Dubbing failed" if done == 0 and len(failed) == 1 else "Batch finished with failures"
        self.log.error(f"{len(failed)} failed · {done} finished")
        self._show_error(title, "\n".join(lines))

    def _auto_export_srt_on_finish(self):
        """Write a sidecar SRT without a save dialog when the Captions option is on."""
        try:
            from datetime import datetime

            from claynext.gui.views.studio.helpers import export_segments
            from claynext.utils.paths import OUTPUTS_DIR

            lines = self._lines_for_export("current") if hasattr(self, "_lines_for_export") else []
            if not lines:
                return
            stem = (
                os.path.splitext(os.path.basename(self.selected_file))[0]
                if self.selected_file
                else f"dubbed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            path = str(OUTPUTS_DIR / f"{stem}_current.srt")
            export_segments(path, "srt", lines)
            self.log.info(f"Exported SRT → {os.path.basename(path)}")
        except Exception as exc:
            self.log.warn(f"SRT export skipped · {exc}")

    def _ensure_auto_captions(self, force: bool = False):
        """One caption clip per dubbed voice line — trim, split, and word-anim independently."""
        canvas = self.timeline.canvas
        managed = [c for c in canvas.clips if is_managed_caption(c)]
        if not force and managed:
            return
        segments = canvas.caption_segments()
        if not segments:
            return
        canvas.clips = [c for c in canvas.clips if not is_managed_caption(c)]
        style = self.caption_style() if hasattr(self, "caption_style") else {
            "kind": "caption", "text": "Caption", "auto_caption": True, "live": False,
        }
        for voice_id, start, end, text in segments:
            dur = max(200, end - start)
            ov = dict(style)
            ov.update({
                "kind": "caption",
                "text": text,
                "live": False,
                "auto_caption": True,
                "voice_id": voice_id,
            })
            label = text if len(text) <= 48 else f"{text[:47]}…"
            canvas.add_clip("caption", label, duration_ms=dur, extra={"overlay": ov}, start_ms=start)
        self._apply_caption_picture()
        self.timeline.rail.rebuild(canvas.tracks)
        self._sync_preview_overlays(force=True)
        look = style.get("name") or "Caption"
        self.log.info(f"Auto captions · {len(segments)} segment(s) on the timeline · {look}")

    def _apply_caption_picture(self) -> None:
        """Place one effect, one filter, and source-cut transitions chosen with captions."""
        if not hasattr(self, "timeline"):
            return
        effect = str(self.store.get_setting("dub", "picture_effect", "none") or "none")
        filt = str(self.store.get_setting("dub", "picture_filter", "clean") or "clean")
        transition = str(self.store.get_setting("dub", "picture_transition", "none") or "none")
        canvas = self.timeline.canvas
        canvas.clips = [
            clip for clip in canvas.clips
            if not (isinstance(clip.extra, dict) and clip.extra.get("auto_picture"))
        ]
        if hasattr(canvas, "fit_source_to_timeline"):
            canvas.fit_source_to_timeline()
        span = canvas.master_span()
        start, dur = span if span else (0, max(int(canvas.duration_ms or 0), 1000))
        from claynext.models.fx import DEFAULT_INTENSITY, EFFECT_LABELS, FILTER_LOOKS
        from claynext.models.transitions import (
            DEFAULT_DURATION_MS, DEFAULT_INTENSITY as TR_INTENSITY, TRANSITION_LABELS,
        )

        placed: list[str] = []
        if effect != "none":
            name = EFFECT_LABELS.get(effect, effect)
            style = {
                "kind": "effect",
                "effect": effect,
                "intensity": DEFAULT_INTENSITY["effect"],
                "name": name,
            }
            canvas.add_clip(
                "effect", name, duration_ms=dur,
                extra={"fx": style, "auto_picture": True}, start_ms=start,
            )
            placed.append(name)
        if filt not in {"", "none", "clean"}:
            label = dict(FILTER_LOOKS).get(filt, filt)
            style = {
                "kind": "filter",
                "filter": filt,
                "look": filt,
                "intensity": DEFAULT_INTENSITY["filter"],
                "name": label,
            }
            canvas.add_clip(
                "filter", label, duration_ms=dur,
                extra={"fx": style, "auto_picture": True}, start_ms=start,
            )
            placed.append(label)
        if transition != "none":
            seams = canvas.find_split_seams()
            if seams:
                name = TRANSITION_LABELS.get(transition, transition)
                tr = {
                    "transition": transition,
                    "intensity": int(TR_INTENSITY),
                    "duration_ms": int(DEFAULT_DURATION_MS),
                    "name": name,
                }
                for seam in seams:
                    seam["left_clip"].extra["transition"] = dict(tr)
                placed.append(name)
            else:
                self.log.info("Transition skipped · source has a single cut")
        canvas.selected_ids.clear()
        if placed:
            self.log.info("Caption picture · " + " · ".join(placed))

    def _remember_composition(
        self, output: str, segments: list, source: str, language: str, voice: str,
        bed: str = "", dialogue: str = "", duck: bool = False, footage: list | None = None,
        clean_audio: str = "", vocals: str = "",
        effects: str = "", music: str = "",
        apply: bool = True,
        stash: bool = True,
        select: bool = True,
    ):
        if stash:
            self._stash_composition()
        previous = int(getattr(self, "_composition_index", -1))
        number = len(self._compositions) + 1
        lang = language or "Dub"
        self._compositions.append({
            "name": f"Dub {number} · {lang}",
            "output": output,
            "source": source,
            "segments": [dict(seg) for seg in segments],
            "language": language,
            "voice": voice,
            "bed": bed,
            "dialogue": dialogue,
            "clean_audio": clean_audio,
            "vocals": vocals,
            "effects": effects,
            "music": music,
            "duck": duck,
            "footage": list(footage or []),
        })
        new_index = len(self._compositions) - 1
        if select:
            self._composition_index = new_index
        shown = self._composition_index if select else previous
        self.timeline.set_compositions(
            [item["name"] for item in self._compositions],
            shown,
        )
        self._link_task(new_index, source)
        if apply:
            self._apply_composition(new_index)

    def _add_composition(self) -> None:
        if getattr(self, "_dub_busy", False):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Sequences", "Wait for the dub to finish before adding a sequence.")
            return
        self._stash_composition()
        number = len(self._compositions) + 1
        self._compositions.append({
            "name": f"Sequence {number}",
            "output": "",
            "source": "",
            "segments": [],
            "language": "",
            "voice": "",
            "bed": "",
            "dialogue": "",
            "clean_audio": "",
            "vocals": "",
            "duck": False,
            "footage": [],
            "takes": [],
            "overlays": [],
            "fx": [],
            "tracks": [],
        })
        index = len(self._compositions) - 1
        self._composition_index = index
        self.timeline.set_compositions(self._sequence_names(), index)
        self._sequence_switching = True
        try:
            self.timeline.begin_sequence()
            try:
                self.timeline.canvas.clips.clear()
                self.timeline.set_media("")
                self._apply_composition(index, preview=False)
            finally:
                self.timeline.end_sequence()
        finally:
            self._sequence_switching = False
        QTimer.singleShot(0, self.show_timeline_player)
        self.log.info(f"Sequence · {self._compositions[index]['name']}")

    def _on_composition_changed(self, index: int):
        if index == int(getattr(self, "_composition_index", -1)):
            return
        self._sequence_loading = index
        self._sync_sequence_activity()
        QTimer.singleShot(0, lambda i=index: self._load_sequence_tab(i))

    def _load_sequence_tab(self, index: int) -> None:
        """Open the tab the user picked. The spinner stays while that sequence is the active job."""
        if getattr(self, "_sequence_loading", -1) != index:
            return
        self._stash_composition()
        self._sequence_switching = True
        try:
            self.timeline.begin_sequence()
            try:
                self._apply_composition(index, preview=False)
            finally:
                self.timeline.end_sequence()
        finally:
            self._sequence_switching = False
            self._sequence_loading = -1
            self._sync_sequence_activity()
        QTimer.singleShot(0, self.show_timeline_player)

    def _sync_sequence_activity(self) -> None:
        """Spinner on the sequence that is working, and in the panel while any job is in flight."""
        bar = getattr(getattr(self, "timeline", None), "sequences", None)
        if bar is None or not hasattr(bar, "set_busy"):
            return
        busy: set[int] = set()
        for task in getattr(self, "_tasks", None) or []:
            if task.get("status") not in {"running", "paused", "queued"}:
                continue
            comp = task.get("comp", -1)
            if isinstance(comp, int) and comp >= 0:
                busy.add(comp)
        if getattr(self, "_dub_busy", False) and not busy:
            active = int(getattr(self, "_active_task", -1))
            for task in getattr(self, "_tasks", None) or []:
                if task.get("id") == active:
                    comp = task.get("comp", -1)
                    if isinstance(comp, int) and comp >= 0:
                        busy.add(comp)
                    break
            else:
                current = int(getattr(self, "_composition_index", -1))
                if current >= 0:
                    busy.add(current)
        loading = getattr(self, "_sequence_loading", -1)
        if isinstance(loading, int) and loading >= 0:
            busy.add(loading)
        bar.set_busy(busy)

    def _sequence_names(self) -> list[str]:
        return [str(comp.get("name") or "") for comp in self._compositions]

    def _map_sequence_index(self, index: int, src: int, dst: int) -> int:
        if index < 0:
            return index
        if index == src:
            return dst
        if src < dst and src < index <= dst:
            return index - 1
        if dst < src and dst <= index < src:
            return index + 1
        return index

    def _remap_task_comps(self, shift) -> None:
        for task in getattr(self, "_tasks", None) or []:
            comp = task.get("comp", -1)
            if isinstance(comp, int):
                task["comp"] = shift(comp)
        if hasattr(self, "_refresh_tasks"):
            self._refresh_tasks()

    def _reorder_composition(self, src: int, dst: int) -> None:
        comps = self._compositions
        if not (0 <= src < len(comps) and 0 <= dst < len(comps)) or src == dst:
            return
        if getattr(self, "_dub_busy", False):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Sequences", "Wait for the dub to finish before reordering.")
            return
        self._stash_composition()
        comps.insert(dst, comps.pop(src))
        self._composition_index = self._map_sequence_index(int(self._composition_index), src, dst)
        self._remap_task_comps(lambda index, a=src, b=dst: self._map_sequence_index(index, a, b))
        self.timeline.set_compositions(self._sequence_names(), self._composition_index)

    def _rename_composition(self, index: int) -> None:
        comps = self._compositions
        if not 0 <= index < len(comps):
            return
        from PySide6.QtWidgets import QInputDialog
        current = str(comps[index].get("name") or "")
        name, ok = QInputDialog.getText(self, "Rename sequence", "Sequence name", text=current)
        if not ok:
            return
        name = name.strip()
        if not name or name == current:
            return
        comps[index]["name"] = name
        self.timeline.set_compositions(self._sequence_names(), self._composition_index)

    def _delete_composition(self, index: int) -> None:
        comps = self._compositions
        if not 0 <= index < len(comps):
            return
        from PySide6.QtWidgets import QMessageBox
        if getattr(self, "_dub_busy", False):
            QMessageBox.information(self, "Sequences", "Wait for the dub to finish before deleting a sequence.")
            return
        name = str(comps[index].get("name") or "this sequence")
        answer = QMessageBox.question(
            self,
            "Delete sequence",
            f"Delete “{name}”?\nThis sequence leaves the list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        current = int(self._composition_index)
        if index != current:
            self._stash_composition()
        del comps[index]

        def _shift(comp: int, removed: int = index) -> int:
            if comp == removed:
                return -1
            if comp > removed:
                return comp - 1
            return comp

        self._remap_task_comps(_shift)
        if not comps:
            self._composition_index = -1
            self.timeline.set_compositions([], -1)
            return
        if index == current:
            self._composition_index = -1
            new_index = min(index, len(comps) - 1)
            self.timeline.set_compositions(self._sequence_names(), new_index)
            self._on_composition_changed(new_index)
            return
        if current > index:
            self._composition_index = current - 1
        self.timeline.set_compositions(self._sequence_names(), self._composition_index)

    def _export_composition(self, index: int) -> None:
        if not 0 <= index < len(self._compositions):
            return
        if index != int(self._composition_index):
            if getattr(self, "_dub_busy", False):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Export", "Wait for the dub to finish, then export.")
                return
            self._on_composition_changed(index)
            self.timeline.set_compositions(self._sequence_names(), self._composition_index)
        if hasattr(self, "open_export_dialog"):
            self.open_export_dialog("movie")

    def _lay_source_stems(self, comp: dict) -> None:
        """Picture stays silent. Cleaned source and isolated beds sit on their own tracks."""
        if not hasattr(self.timeline, "lay_sync_stems"):
            return
        bed = str(comp.get("bed") or "")
        clean = str(comp.get("clean_audio") or "")
        vocals = str(comp.get("vocals") or "")
        effects = str(comp.get("effects") or "")
        music = str(comp.get("music") or "")
        stems: list[dict] = []
        split = False
        if effects and os.path.isfile(effects):
            stems.append({"label": "Effects", "path": effects, "mute": False})
            split = True
        if music and os.path.isfile(music):
            stems.append({"label": "Music", "path": music, "mute": False})
            split = True
        if not split and bed and os.path.isfile(bed):
            stems.append({"label": "Effects", "path": bed, "mute": False})
        if vocals and os.path.isfile(vocals):
            stems.append({"label": "Vocals", "path": vocals, "mute": True})
        isolated = split or bool(bed and os.path.isfile(bed))
        if clean and os.path.isfile(clean):
            stems.append({
                "label": "Source audio",
                "path": clean,
                "mute": isolated,
            })
        if stems:
            self.timeline.lay_sync_stems(stems)

    def _stash_composition(self):
        index = getattr(self, "_composition_index", -1)
        if 0 <= index < len(self._compositions):
            comp = self._compositions[index]
            comp["footage"] = self.timeline.export_footage()
            comp["takes"] = self.timeline.export_takes()
            comp["overlays"] = self.timeline.export_overlays(include_hidden=True)
            comp["fx"] = self.timeline.export_fx(include_hidden=True)
            comp["tracks"] = self.timeline.export_tracks()
            if hasattr(self.timeline, "export_state"):
                comp["timeline"] = self.timeline.export_state()
            if self._segments:
                comp["segments"] = [dict(seg) for seg in self._segments]
            comp["duration_ms"] = int(getattr(self.timeline.canvas, "duration_ms", 0) or 0)
            if hasattr(self.timeline, "export_masters"):
                comp["masters"] = self.timeline.export_masters()

    def _apply_composition(self, index: int, *, legacy_overlays=None, legacy_fx=None, legacy_tracks=None, preview: bool = True):
        if index < 0 or index >= len(self._compositions):
            self._sync_timeline_visibility()
            return
        self._composition_index = index
        self._viewing_task = -1
        self._live_return_index = -1
        self._script_follow_task = -1
        if getattr(self, "_script_loading", False):
            self._script_loading = False
            spinner = getattr(self, "script_load_spinner", None)
            if spinner is not None:
                spinner.stop()
        comp = self._compositions[index]
        self._output_path = comp.get("output") or ""
        if self.act_open_out:
            self.act_open_out.setEnabled(bool(self._output_path and os.path.isfile(self._output_path)))
        saved = comp.get("timeline") if isinstance(comp.get("timeline"), dict) else None
        if saved and saved.get("clips"):
            self._open_saved_timeline(saved, comp.get("segments") or [])
            bed = str(comp.get("bed") or "")
            self.timeline.set_speech_bed(bed if bed and os.path.isfile(bed) else "")
            clean_source = str(comp.get("source") or "") if not comp.get("output") else ""
            self.timeline.speech_source = clean_source if clean_source and os.path.isfile(clean_source) else ""
            self.timeline.set_voice_audio(str(comp.get("dialogue") or ""))
            if preview:
                if self._player_mode == "timeline":
                    self.show_timeline_player()
                else:
                    self._sync_player_header()
            self._sync_timeline_visibility()
            self._refresh_tasks()
            return
        masters = comp.get("masters") if comp.get("merged") else None
        if isinstance(masters, list) and masters and hasattr(self.timeline, "replace_masters"):
            self.timeline.replace_masters(masters)
        else:
            media = self._output_path if self._output_path and os.path.isfile(self._output_path) else comp.get("source") or ""
            if media:
                self.timeline.set_media(media, int(comp.get("duration_ms") or 0))
        self._fill_table(comp.get("segments") or [])
        bed = str(comp.get("bed") or "")
        has_bed = bool(bed and os.path.isfile(bed))
        self.timeline.set_speech_bed(bed if has_bed else "")
        self._lay_source_stems(comp)
        clean_source = str(comp.get("source") or "") if not comp.get("output") else ""
        self.timeline.speech_source = clean_source if clean_source and os.path.isfile(clean_source) else ""
        self.timeline.set_voice_audio(str(comp.get("dialogue") or ""))
        if "takes" in comp:
            self.timeline.apply_takes(comp["takes"])
        if comp.get("footage"):
            self.timeline.apply_footage(comp["footage"])
        elif comp.get("duck"):
            duck_val = self.slider_duck.value() / 100.0 if hasattr(self, "slider_duck") else 0.0
            if duck_val <= 0.02:
                duck_val = 0.0
            self.timeline.duck_level = duck_val
            self.timeline.duck_fade_ms = self.slider_fade_ms.value() if hasattr(self, "slider_fade_ms") else 150
            level = 0.0 if has_bed else self.timeline.duck_level
            spans = self.timeline.auto_duck(level)
            detect = self.chk_auto_mix.isChecked() and bool(self.timeline.speech_source)
            for clip in self.timeline.canvas.footage_clips():
                clip.extra["auto_key"] = {"on": True, "detect": detect, "level": self.slider_duck.value()}
            comp["duck"] = False
            comp["footage"] = self.timeline.export_footage()
            if detect and self.timeline.auto_mix():
                comp["auto_mix"] = True
                self.log.info("Auto mix · detecting the original voices…")
            if has_bed:
                self.log.info(f"Auto key points · original speech removed under {spans} voice span(s), music and effects kept")
            else:
                self.log.info(f"Auto duck · footage at {self.slider_duck.value()}% under {spans} voice span(s)")
        self._restore_composition_graphics(comp, legacy_overlays, legacy_fx, legacy_tracks)
        if comp.pop("pending_captions", False):
            self._ensure_auto_captions(force=True)
            self._stash_composition()
        source = str(comp.get("source") or "")
        if not has_bed and not comp.get("output") and source and os.path.isfile(source):
            self._build_speech_bed(index, source)
        if preview:
            if self._player_mode == "timeline":
                self.show_timeline_player()
            else:
                self._sync_player_header()
        self._sync_timeline_visibility()
        self._refresh_tasks()

    def _open_saved_timeline(self, state: dict, segments: list) -> None:
        """Reopen the stored lanes. Do not rebuild them from the dub recipe."""
        self._skip_dialogue_sync = True
        try:
            self._fill_table(list(segments or []))
        finally:
            self._skip_dialogue_sync = False
        self.timeline.apply_state(state)

    def _restore_composition_graphics(self, comp: dict, legacy_overlays=None, legacy_fx=None, legacy_tracks=None):
        """Tracks, captions/text, and fx for this dub — migrate old top-level session data once."""
        tracks = comp.get("tracks") if isinstance(comp.get("tracks"), list) else None
        if tracks is None and isinstance(legacy_tracks, list):
            tracks = legacy_tracks
            comp["tracks"] = list(tracks)
        if tracks:
            self.timeline.apply_tracks(tracks)

        if "overlays" in comp and isinstance(comp.get("overlays"), list):
            overlays = comp["overlays"]
        elif isinstance(legacy_overlays, list):
            overlays = legacy_overlays
            comp["overlays"] = list(overlays)
        else:
            overlays = None

        if "fx" in comp and isinstance(comp.get("fx"), list):
            fx = comp["fx"]
        elif isinstance(legacy_fx, list):
            fx = legacy_fx
            comp["fx"] = list(fx)
        else:
            fx = None

        if overlays is not None:
            self.timeline.replace_overlay_clips(overlays)
        if fx is not None:
            self.timeline.apply_fx(fx)

        # Legacy sessions stored a Caption track but never the caption clips
        if hasattr(self.timeline, "hold_effects_bed"):
            self.timeline.hold_effects_bed()

        if overlays is None:
            auto = True
            if hasattr(self, "store"):
                auto = self.store.get_setting("dub", "auto_captions", "1") == "1"
            if auto and hasattr(self, "_ensure_auto_captions"):
                self._ensure_auto_captions(force=False)
                comp["overlays"] = self.timeline.export_overlays(include_hidden=True)
                comp["tracks"] = self.timeline.export_tracks()

    def _build_speech_bed(self, index: int, source: str):
        def _job(media: str, progress_callback=None):
            from claynext.models.features import demucs_model_name, prefer_demucs_bed, stem_backend
            from claynext.models.stem_separation import separate_movie_stems
            from claynext.adapters.ffmpeg_service import ensure_speech_bed

            backend = stem_backend()
            if prefer_demucs_bed() and backend:
                split = separate_movie_stems(
                    media,
                    model=demucs_model_name(),
                    progress_callback=progress_callback,
                )
                if split.get("bed"):
                    return {
                        "bed": split.get("bed") or "",
                        "vocals": split.get("vocals") or "",
                        "effects": split.get("effects") or "",
                        "music": split.get("music") or "",
                        "backend": backend,
                    }
            bed = ensure_speech_bed(media, progress_callback=progress_callback, use_demucs=False)
            return {"bed": bed or "", "vocals": "", "backend": None}

        worker = Worker(_job, source)
        worker.signals.result.connect(lambda result, i=index: self._on_speech_bed(i, result))
        self._bed_worker = worker
        self.thread_pool.start(worker)
        self.log.info("Isolating music and effects from dialogue…")

    def _on_speech_bed(self, index: int, result):
        if not result or index >= len(self._compositions):
            return
        if isinstance(result, str):
            path, vocals, backend = result, "", None
        else:
            path = str(result.get("bed") or "")
            vocals = str(result.get("vocals") or "")
            backend = result.get("backend")
        if not path:
            return
        comp = self._compositions[index]
        comp["bed"] = path
        if vocals:
            comp["vocals"] = vocals
            comp["vocals_stem"] = vocals
        if isinstance(result, dict):
            comp["effects"] = str(result.get("effects") or "")
            comp["music"] = str(result.get("music") or "")
        if index == self._composition_index:
            self._lay_source_stems(comp)
            if self._player_mode == "timeline":
                dialogue = str(self._compositions[index].get("dialogue") or vocals or "")
                self.preview.set_stems(path, dialogue)
            self.timeline.set_speech_bed(path)
            if self._compositions[index].get("auto_mix"):
                self.timeline.auto_mix()
            if backend == "mlx":
                self.log.success("Demucs MLX bed ready · music/effects isolated from dialogue")
            elif backend == "torch":
                self.log.success("Demucs bed ready · music/effects isolated from dialogue")
            else:
                self.log.success("Music and effects bed ready · key points now remove only speech")

    def _on_auto_mix_done(self, spans: int, speech_ms: int, has_bed: bool):
        index = self._composition_index
        if 0 <= index < len(self._compositions):
            self._compositions[index]["footage"] = self.timeline.export_footage()
        self._sync_props_audio()
        seconds = speech_ms / 1000.0
        if has_bed:
            self.log.success(
                f"Auto mix · {seconds:.1f}s of original speech swapped to the music bed "
                f"in {spans} span(s) · effects and music kept"
            )
        else:
            self.log.info(f"Auto mix · footage ducked under {spans} voice span(s) · music bed still building")

    def _on_auto_mix_failed(self, message: str):
        self.log.warn(f"Auto mix · voice detection failed · {message}")

    def _sync_timeline_visibility(self):
        # Timeline stays visible by default; View → Timeline can still hide it.
        show = bool(getattr(self, "_timeline_open", True))
        stage = getattr(self, "timeline_stage", None)
        if stage is not None:
            stage.setVisible(show)
        self.timeline.setVisible(show)
        if show:
            self.timeline.setMinimumHeight(160)
            self.timeline.setMaximumHeight(16777215)
        else:
            self.timeline.setMinimumHeight(0)
            self.timeline.setMaximumHeight(0)
        self._sync_timeline_button()

    def _on_error(self, err_msg, stack):
        if str(err_msg) == "Dub stopped" or getattr(self, "_batch_stopping", False):
            self._halt_batch()
            return
        self._skip_failed_movie(str(err_msg))
        if stack:
            self.log.debug(stack.splitlines()[-1])
        self._launch_next_or_finish()

    def _set_busy(self, busy: bool):
        # The script panel spinner is only for transcription (see _launch_dub_job).
        # Later steps keep footer / window progress and leave the transcript table up.
        if not busy:
            self._script_follow_task = -1
            if hasattr(self, "_set_script_loading"):
                self._set_script_loading(False)
        if self.act_dub:
            self.act_dub.setEnabled(not busy)
            self.act_dub.setText("Working…" if busy else "Start &Dubbing")
        self._dub_busy = busy
        if busy:
            self._set_footer_progress(True, 0, "Starting…")
            self._set_window_status("Localizing…", 0)
        else:
            self._set_footer_progress(False)
            self._set_window_status("Ready")
            if hasattr(self, "media_lib"):
                self.media_lib._update_detail_footer()
        for name in (
            "combo_source_lang", "combo_lang", "combo_voice", "combo_voice_sec",
            "combo_model", "slider_duck", "combo_translator",
        ):
            w = getattr(self, name, None)
            if w is not None:
                w.setEnabled(not busy)
        if hasattr(self, "edit_ollama") and hasattr(self, "combo_translator"):
            self.edit_ollama.setEnabled(
                not busy
                and (self.combo_translator.currentData() or "auto") in {"auto", "movie", "ollama"}
            )
        if not busy:
            self._update_script_meta()
        self._sync_sequence_activity()

    def _set_footer_progress(self, busy: bool, pct: int = 0, message: str = ""):
        footer = getattr(getattr(self, "media_lib", None), "footer", None)
        if footer is None or not hasattr(footer, "set_localize_progress"):
            return
        footer.set_localize_progress(busy, pct, message)

    def _set_window_status(self, message: str, progress: int | None = None):
        win = self.window() if hasattr(self, "window") else None
        bar = getattr(win, "status_bar", None) if win is not None else None
        if bar is not None and hasattr(bar, "set_status_message"):
            bar.set_status_message(str(message or "Ready"), progress)

    def open_output(self):
        path = self._output_path
        if not path or not os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(OUTPUTS_DIR)))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

