"""Start, progress, and finish the dubbing job."""
from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from jela.core.dubbing_engine import DubbingEngine
from jela.core.job_control import JobControl
from jela.core.worker import Worker
from jela.gui.views.studio.captions import is_managed_caption
from jela.utils.config import OUTPUTS_DIR


class PipelineTools:
    """Background dubbing job and the finished file."""

    def _open_api_keys(self):
        from jela.gui.dialogs.api_keys_dialog import ApiKeysDialog
        ApiKeysDialog(self).exec()

    def start_dubbing(self):
        sources = self._dub_sources()
        if not sources:
            self._show_error("No media", "Select one or more movies in the Media library, then start dubbing.")
            self.log.warn("Dubbing blocked — no media selected")
            return

        from PySide6.QtWidgets import QDialog
        from jela.gui.dialogs.start_dub_dialog import StartDubDialog

        dlg = StartDubDialog(self, sources=sources, defaults=self._start_dub_defaults())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.options()
        self._apply_start_dub_options(opts)
        self.store.set_setting("dub", "batch_mode", opts.get("batch_mode") or "separate")

        voice_id = self.combo_voice.currentData()
        if not voice_id:
            self._show_error("No voice", "Choose an Edge neural voice.")
            return

        # Batch: merge episodes into one movie (single process), or dedicated tasks (default).
        if len(sources) >= 2 and opts.get("batch_mode") == "merge":
            self._start_merged_episode_dub(sources)
            return

        self._begin_dub_jobs(sources)
        if len(sources) > 1:
            self.log.info(f"Batch dub · {len(sources)} dedicated episode tasks")

    def _begin_dub_jobs(self, sources: list[str]):
        """Queue sources and launch the first dub job."""
        self._dub_queue = sources[1:]
        self.set_dub_source(sources[0])
        self._queue_tasks(sources)
        self._clear_error()
        self._fill_table([])
        self._set_busy(True)
        if hasattr(self, "workspace"):
            self._focus_script_shelf()
        self._launch_dub_job()

    def _start_merged_episode_dub(self, sources: list[str]):
        """Order → concat episodes → one dub pass / one timeline movie."""
        from PySide6.QtWidgets import QDialog
        import time

        from jela.core.ffmpeg_tools import concat_videos
        from jela.gui.views.studio.merge import MergeOrderDialog

        order = MergeOrderDialog(
            sources,
            self,
            window_title="Merge episodes",
            title_text="Episode order",
            hint_text=(
                "Drag to set order. Episodes merge into one movie, then a single "
                "transcription → translate → speak pass fills the timeline."
            ),
            accept_label="Merge & dub",
        )
        if order.exec() != QDialog.DialogCode.Accepted:
            return
        ordered = order.ordered_paths()
        if len(ordered) < 2:
            self._show_error("Merge", "Need at least two episodes to merge.")
            return

        dest = str(OUTPUTS_DIR / f"merged_episodes_{int(time.time())}.mp4")
        self._clear_error()
        self._set_busy(True)
        self.log.info(f"Merging {len(ordered)} episodes → one movie before dub")
        if hasattr(self, "empty_hint"):
            self.empty_hint.setText("Merging episodes…")
        if hasattr(self, "table_spinner") and not self.table_spinner.is_spinning():
            self.table_spinner.start()

        worker = Worker(concat_videos, ordered, dest)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(self._on_episode_merge_ready)
        worker.signals.error.connect(self._on_episode_merge_error)
        self._worker = worker
        self.thread_pool.start(worker)

    def _on_episode_merge_ready(self, path: str):
        if hasattr(self, "table_spinner") and self.table_spinner.is_spinning():
            self.table_spinner.stop()
        if not path or not os.path.isfile(path):
            self._set_busy(False)
            self._show_error("Merge failed", "Merged movie was not created.")
            return
        self.log.success(f"Merged episodes · {os.path.basename(path)}")
        if hasattr(self, "media_lib"):
            self.media_lib.add_files([path], select_last=True)
        self._begin_dub_jobs([path])

    def _on_episode_merge_error(self, message: str, _tb: str = ""):
        if hasattr(self, "table_spinner") and self.table_spinner.is_spinning():
            self.table_spinner.stop()
        self._set_busy(False)
        self._show_error("Merge failed", message or "Could not merge episodes.")
        self.log.error(f"Episode merge failed · {message}")

    def _start_dub_defaults(self) -> dict:
        return {
            "source_lang": self.combo_source_lang.currentText(),
            "target_lang": self.combo_lang.currentText(),
            "voice": self.combo_voice.currentData() or "",
            "secondary_voice": self.combo_voice_sec.currentData() or "",
            "asr_model": self.combo_model.currentText(),
            "translator": self.combo_translator.currentData() or "auto",
            "ollama_model": self.edit_ollama.text().strip() if hasattr(self, "edit_ollama") else "qwen2.5:7b",
            "sync_mode": self.combo_sync_mode.currentData() or "stretch",
            "background": self.slider_duck.value(),
            "center_attenuation": self.slider_center_att.value(),
            "voiceover_boost": self.slider_vo_boost.value(),
            "fade_ms": self.slider_fade_ms.value(),
            "auto_chain": bool(getattr(self, "chk_auto_chain", None) and self.chk_auto_chain.isChecked()),
            "auto_captions": bool(getattr(self, "chk_auto_captions", None) and self.chk_auto_captions.isChecked()),
            "auto_mix": bool(getattr(self, "chk_auto_mix", None) and self.chk_auto_mix.isChecked()),
            "vocal_master": bool(getattr(self, "chk_vocal_master", None) and self.chk_vocal_master.isChecked()),
            # Default: dedicated tasks — merge is opt-in for episode → one movie.
            "batch_mode": self.store.get_setting("dub", "batch_mode", "separate") or "separate",
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
            ollama = str(opts.get("ollama_model") or "qwen2.5:7b").strip() or "qwen2.5:7b"
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

        self._apply_start_check(getattr(self, "chk_auto_chain", None), opts.get("auto_chain"), "auto_chain")
        self._apply_start_check(getattr(self, "chk_auto_captions", None), opts.get("auto_captions"), "auto_captions")
        self._apply_start_check(getattr(self, "chk_auto_mix", None), opts.get("auto_mix"), "auto_mix")
        self._apply_start_check(getattr(self, "chk_vocal_master", None), opts.get("vocal_master"), "vocal_master")
    def _apply_start_check(self, box, value, setting: str):
        if box is None or value is None:
            return
        checked = bool(value)
        box.blockSignals(True)
        box.setChecked(checked)
        box.blockSignals(False)
        self.store.set_setting("dub", setting, "1" if checked else "0")

    def _launch_dub_job(self):
        from jela.gui.views.studio.tasks import LiveBridge

        task = self._start_next_task(self.selected_file)
        control = JobControl()
        task["control"] = control
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
        ollama_model = self.edit_ollama.text().strip() or "qwen2.5:7b"
        self.store.set_setting("dub", "translator", translator)
        self.store.set_setting("dub", "ollama_model", ollama_model)
        self.log.info(f"Starting dub · {source_lang} → {lang} · {voice_id} & {sec_voice_id} · {model} · {translator}")

        vocal_master = self.chk_vocal_master.isChecked()
        center_att = self.slider_center_att.value() / 100.0
        vo_boost = self.slider_vo_boost.value() / 100.0
        fade_ms = self.slider_fade_ms.value()
        sync_mode = self.combo_sync_mode.currentData() or "stretch"
        auto_chain = bool(getattr(self, "chk_auto_chain", None) and self.chk_auto_chain.isChecked())

        worker = Worker(
            DubbingEngine.process_dubbing,
            video_path=self.selected_file,
            source_lang=source_lang,
            target_lang=lang,
            voice_id=voice_id,
            secondary_voice_id=sec_voice_id,
            background_vol=bg,
            asr_model=model,
            asr_language=source_lang,
            translator=translator,
            ollama_model=ollama_model,
            overlays=self.timeline.export_overlays(),
            vocal_master=vocal_master,
            center_attenuation=center_att,
            voiceover_boost=vo_boost,
            fade_ms=fade_ms,
            sync_mode=sync_mode,
            auto_chain=auto_chain,
            render=False,
            control=control,
            live=bridge.send,
        )
        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(self._on_complete)
        worker.signals.error.connect(self._on_error)
        self._worker = worker
        self.thread_pool.start(worker)

    def _on_progress(self, val: int, msg: str):
        self.log.debug(f"{val}% · {msg}")
        self._task_progress(val, msg)
        if hasattr(self, "empty_hint") and self.table_spinner.is_spinning():
            self.empty_hint.setText(msg)

    def _on_complete(self, res: dict):
        if not res:
            self._dub_queue = []
            self._set_busy(False)
            self._fail_tasks("No result returned.")
            self._show_error("Dubbing failed", "No result returned.")
            return
        segs = res.get("segments") or []
        if not segs:
            self._dub_queue = []
            self._set_busy(False)
            self._fail_tasks("No dubbed lines were produced.")
            self._show_error("Dubbing failed", "No dubbed lines were produced.")
            return
        self._error = ""
        if hasattr(self, "workspace"):
            self._focus_script_shelf()
        output = res.get("output_path") or ""
        count = res.get("segments_dubbed", len(segs))
        self._remember_composition(
            output,
            segs,
            self.selected_file,
            self.combo_lang.currentText(),
            self.combo_voice.currentText(),
            bed=str(res.get("bed_path") or ""),
            dialogue=str(res.get("dialogue_path") or ""),
            duck=True,
        )
        if self.chk_auto_captions.isChecked():
            self._ensure_auto_captions(force=True)
        self._stash_composition()
        self._store_project_session()
        if output:
            self.log.success(f"Dubbed {count} line(s) → {os.path.basename(output)}")
        else:
            self.log.success(f"{count} voice clip(s) on the Voice track · use Export → Render dub to make the movie")
        if self._dub_queue:
            self.selected_file = self._dub_queue.pop(0)
            self.log.info(f"Auto chain next · {os.path.basename(self.selected_file)}")
            self._launch_dub_job()
            return
        self._set_busy(False)

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
        self.timeline.rail.rebuild(canvas.tracks)
        self._sync_preview_overlays(force=True)
        look = style.get("name") or "Caption"
        self.log.info(f"Auto captions · {len(segments)} segment(s) · {look}")

    def _remember_composition(
        self, output: str, segments: list, source: str, language: str, voice: str,
        bed: str = "", dialogue: str = "", duck: bool = False, footage: list | None = None,
    ):
        self._stash_composition()
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
            "duck": duck,
            "footage": list(footage or []),
        })
        self._composition_index = len(self._compositions) - 1
        self.timeline.set_compositions(
            [item["name"] for item in self._compositions],
            self._composition_index,
        )
        self._link_task(self._composition_index, source)
        self._apply_composition(self._composition_index)

    def _on_composition_changed(self, index: int):
        self._stash_composition()
        self._apply_composition(index)
        self.show_timeline_player()

    def _stash_composition(self):
        index = getattr(self, "_composition_index", -1)
        if 0 <= index < len(self._compositions):
            comp = self._compositions[index]
            comp["footage"] = self.timeline.export_footage()
            comp["takes"] = self.timeline.export_takes()
            comp["overlays"] = self.timeline.export_overlays(include_hidden=True)
            comp["fx"] = self.timeline.export_fx(include_hidden=True)
            comp["tracks"] = self.timeline.export_tracks()
            if self._segments:
                comp["segments"] = [dict(seg) for seg in self._segments]

    def _apply_composition(self, index: int, *, legacy_overlays=None, legacy_fx=None, legacy_tracks=None):
        if index < 0 or index >= len(self._compositions):
            self._sync_timeline_visibility()
            return
        self._composition_index = index
        self._viewing_task = -1
        self._live_return_index = -1
        comp = self._compositions[index]
        self._output_path = comp.get("output") or ""
        if self.act_open_out:
            self.act_open_out.setEnabled(bool(self._output_path and os.path.isfile(self._output_path)))
        media = self._output_path if self._output_path and os.path.isfile(self._output_path) else comp.get("source") or ""
        if media:
            self.timeline.set_media(media)
        self._fill_table(comp.get("segments") or [])
        bed = str(comp.get("bed") or "")
        has_bed = bool(bed and os.path.isfile(bed))
        self.timeline.set_speech_bed(bed if has_bed else "")
        clean_source = str(comp.get("source") or "") if not comp.get("output") else ""
        self.timeline.speech_source = clean_source if clean_source and os.path.isfile(clean_source) else ""
        self.timeline.set_voice_audio(str(comp.get("dialogue") or ""))
        if "takes" in comp:
            self.timeline.apply_takes(comp["takes"])
        if comp.get("footage"):
            self.timeline.apply_footage(comp["footage"])
        elif comp.get("duck"):
            self.timeline.duck_level = self.slider_duck.value() / 100.0
            self.timeline.duck_fade_ms = self.slider_fade_ms.value()
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
        source = str(comp.get("source") or "")
        if not has_bed and not comp.get("output") and source and os.path.isfile(source):
            self._build_speech_bed(index, source)
        if self._player_mode == "timeline":
            self.show_timeline_player()
        else:
            self._sync_player_header()
        self._sync_timeline_visibility()
        self._refresh_tasks()

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
            from jela.core.features import prefer_demucs_bed, stem_backend
            from jela.core.stem_separation import ensure_demucs_speech_bed
            from jela.core.ffmpeg_tools import ensure_speech_bed

            backend = stem_backend()
            if prefer_demucs_bed() and backend:
                bed, vocals = ensure_demucs_speech_bed(media, progress_callback=progress_callback)
                if bed:
                    return {"bed": bed, "vocals": vocals or "", "backend": backend}
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
        self._compositions[index]["bed"] = path
        if vocals:
            self._compositions[index]["vocals_stem"] = vocals
        if index == self._composition_index:
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
        self.timeline.setVisible(show)
        if show:
            self.timeline.setMinimumHeight(160)
            self.timeline.setMaximumHeight(16777215)
        else:
            self.timeline.setMinimumHeight(0)
            self.timeline.setMaximumHeight(0)
        self._sync_timeline_button()

    def _on_error(self, err_msg, stack):
        self._dub_queue = []
        self._set_busy(False)
        if str(err_msg) == "Dub stopped":
            self._fail_tasks("Stopped", status="cancelled")
            self.log.info("Dub stopped")
            return
        self._fail_tasks(str(err_msg))
        self._store_project_session()
        self._show_error("Dubbing failed", str(err_msg))
        self.log.error(f"Dubbing failed · {err_msg}")
        if stack:
            self.log.debug(stack.splitlines()[-1])

    def _set_busy(self, busy: bool):
        if busy:
            self.table_spinner.start()
            self.empty_title.setText("Dubbing…")
            if getattr(self, "chk_auto_chain", None) and self.chk_auto_chain.isChecked():
                self.empty_hint.setText("Character → translate → TTS → voice")
            else:
                self.empty_hint.setText("Transcribe → lead voice → mix")
            self.script_stack.setCurrentIndex(0)
            if hasattr(self, "workspace"):
                self._focus_script_shelf()
        else:
            self.table_spinner.stop()
        if self.act_dub:
            self.act_dub.setEnabled(not busy)
            self.act_dub.setText("Working…" if busy else "Start &Dubbing")
        self._dub_busy = busy
        if hasattr(self, "media_lib") and getattr(self.media_lib, "footer", None):
            btn = getattr(self.media_lib.footer, "btn_dub", None)
            if btn is not None:
                if busy:
                    btn.setEnabled(False)
                    btn.setText("Dubbing…")
                else:
                    self.media_lib._update_detail_footer()
        self.combo_source_lang.setEnabled(not busy)
        self.combo_lang.setEnabled(not busy)
        self.combo_voice.setEnabled(not busy)
        self.combo_voice_sec.setEnabled(not busy)
        self.combo_model.setEnabled(not busy)
        self.slider_duck.setEnabled(not busy)
        self.combo_translator.setEnabled(not busy)
        self.edit_ollama.setEnabled(not busy and (self.combo_translator.currentData() or "auto") in {"auto", "ollama"})
        self._update_script_meta()

    def open_output(self):
        path = self._output_path
        if not path or not os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(OUTPUTS_DIR)))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
