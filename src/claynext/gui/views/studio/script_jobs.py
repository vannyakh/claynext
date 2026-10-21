"""Retry transcript, translate, and TTS for script lines."""
from __future__ import annotations

import hashlib
import os

from PySide6.QtWidgets import QMenu, QMessageBox

from claynext.gui.icons import icon
from claynext.models.dubbing_service import timestamp_to_sec
from claynext.models.translate_service import TranslateEngine
from claynext.models.tts_service import TTSEngine
from claynext.gui.worker import Worker
from claynext.utils.config import CACHE_DIR
from claynext.utils.job_control import JobCancelled, JobControl


class ScriptJobTools:
    """Retry transcript, translate, and TTS for script lines."""

    def _script_menu_action(self, menu: QMenu, icon_name: str, text: str, slot, *, tip: str = ""):
        act = menu.addAction(icon(icon_name, size=14), text)
        act.setIconVisibleInMenu(True)
        if tip:
            act.setToolTip(tip)
        act.triggered.connect(slot)
        return act

    def _fill_script_regen_menu(self):
        """Header sparkles menu — regenerate / retry pipeline features."""
        menu = getattr(self, "_script_regen_menu", None)
        if menu is None:
            return
        menu.clear()
        n = len(self._segments)
        busy = self._script_worker is not None or bool(getattr(self, "_dub_busy", False))
        has_source = bool(
            str(getattr(self, "selected_file", "") or "")
            and os.path.isfile(str(self.selected_file))
        )
        can_retry = has_source or self._current_script_task_id() >= 0
        all_rows = list(range(n))
        selected = self._selected_rows() if n else []

        act_asr = self._script_menu_action(
            menu, "mic", "Retry transcript",
            self._retry_script_transcript,
            tip="Re-run ASR on the movie (starts a new dub pass)",
        )
        act_asr.setEnabled(can_retry and not busy)

        act_ocr = self._script_menu_action(
            menu, "video", "Scan subtitles from video frames (OCR)…",
            self._open_frame_ocr_scanner,
            tip="Capture burned-in subtitles frame-by-frame with custom capture zone tracker",
        )
        act_ocr.setEnabled(has_source and not busy)

        act_tr = self._script_menu_action(
            menu, "globe", "✨ Translate transcript (direct AI)",
            lambda: self._translate_transcript_direct(all_rows),
            tip="Directly translate transcript lines with AI (fast, no heavy jobs)",
        )
        act_tr.setEnabled(n > 0 and not busy)

        if selected:
            act_tr_sel = self._script_menu_action(
                menu, "globe", f"✨ Translate ({len(selected)} selected)",
                lambda rows=list(selected): self._translate_transcript_direct(rows),
                tip="Directly translate only the selected lines",
            )
            act_tr_sel.setEnabled(not busy)

        act_fit = self._script_menu_action(
            menu, "sparkles", f"Fit to slot timing with AI ({len(selected) if selected else 'all'})",
            lambda rows=list(selected if selected else all_rows): self._regenerate_rows(rows, force_fit=True),
            tip="Re-phrase dialogue with AI so speaking pace fits each video scene exactly",
        )
        act_fit.setEnabled(n > 0 and not busy)

        act_cast = self._script_menu_action(
            menu, "sparkles", "AI Cast & Gender Analysis (LLM / High Quality)",
            self._run_ai_cast_analysis if hasattr(self, "_run_ai_cast_analysis") else lambda: self._autodetect_genders(None, all_lines=True),
            tip="Identify character names, true genders, and assign complementary neural voices using AI",
        )
        act_cast.setEnabled(n > 0 and not busy)

        act_clone = self._script_menu_action(
            menu, "sparkles", "🎭 Clone voices from movie (Actor Tone & Pitch)",
            self._clone_voices_from_movie,
            tip="Detect character voices in the movie, copy their pitch & tone, and generate reference voice clones",
        )
        act_clone.setEnabled(n > 0 and has_source and not busy)

        act_tts = self._script_menu_action(
            menu, "volume", "Retry TTS (all)",
            lambda: self._resynthesize_rows(all_rows),
            tip="Re-synthesize voice audio for every line",
        )
        act_tts.setEnabled(n > 0 and not busy)

        if selected:
            act_tts_sel = self._script_menu_action(
                menu, "volume", f"Retry TTS ({len(selected)} selected)",
                lambda rows=list(selected): self._resynthesize_rows(rows),
                tip="Re-speak only the selected lines",
            )
            act_tts_sel.setEnabled(not busy)

        menu.addSeparator()
        current = self._task_by_id(self._current_script_task_id()) if hasattr(self, "_task_by_id") else None
        current_status = str(current.get("status") or "") if current else ""
        dubbing_this = current_status in {"running", "paused"}
        batch_busy = bool(getattr(self, "_dub_busy", False) or getattr(self, "_flight", None))
        allow_full = can_retry and self._script_worker is None and not dubbing_this
        if batch_busy and current_status not in {"failed", "cancelled"}:
            allow_full = False
        act_all = self._script_menu_action(
            menu, "refresh", "Retry full dub",
            self._retry_script_all,
            tip="Full redub · transcript → translate → TTS → mix",
        )
        act_all.setEnabled(allow_full)

    def _fill_script_actions_menu(self):
        menu = getattr(self, "_script_actions_menu", None)
        if menu is None:
            return
        menu.clear()
        n = len(self._segments)
        busy = self._script_worker is not None or bool(getattr(self, "_dub_busy", False))
        has_source = bool(
            str(getattr(self, "selected_file", "") or "")
            and os.path.isfile(str(self.selected_file))
        )
        all_rows = list(range(n))
        pending_n = sum(1 for seg in self._segments if seg.get("pending"))

        act_accept = self._script_menu_action(
            menu, "check_on", "Accept all pending",
            lambda: self._accept_versions(all_rows),
            tip="Keep every pending edit",
        )
        act_accept.setEnabled(pending_n > 0 and not busy)
        act_rev = self._script_menu_action(
            menu, "undo", "Reverse all pending",
            lambda: self._reverse_versions(all_rows),
            tip="Restore the last accepted version",
        )
        act_rev.setEnabled(pending_n > 0 and not busy)
        act_jump = self._script_menu_action(
            menu, "chevron-right", "Next pending edit",
            lambda: self._jump_pending(1),
            tip="Jump to the next line with a pending version",
        )
        act_jump.setEnabled(pending_n > 0)

        menu.addSeparator()
        act_gender = self._script_menu_action(
            menu, "sparkles", "✨ AI Cast & Gender Analysis (High Quality LLM)",
            self._run_ai_cast_analysis if hasattr(self, "_run_ai_cast_analysis") else lambda: self._autodetect_genders(None, all_lines=True),
            tip="Identify character names, true genders, and assign complementary neural voices using AI",
        )
        act_gender.setEnabled(n > 0 and not busy)

        act_clone_act = self._script_menu_action(
            menu, "sparkles", "🎭 Clone Movie Voices & Match Actor Tone",
            self._clone_voices_from_movie,
            tip="Extract character voice samples from movie audio and copy pitch/timbre",
        )
        act_clone_act.setEnabled(n > 0 and has_source and not busy)

        menu.addSeparator()
        copy_menu = menu.addMenu(icon("copy", size=14), "Copy visible…")
        copy_menu.setObjectName("media_lib_menu")
        copy_menu.addAction("Dub text", lambda: self._copy_script_lines("dub"))
        copy_menu.addAction("Source text", lambda: self._copy_script_lines("source"))
        copy_menu.addAction("Source + dub", lambda: self._copy_script_lines("both"))
        copy_menu.addAction("With times", lambda: self._copy_script_lines("times"))
        copy_menu.setEnabled(n > 0)

        menu.addSeparator()
        self._script_menu_action(
            menu, "folder", "Import script…",
            lambda: self._import_script(),
            tip="Load lines from SRT, VTT, or JSON",
        )
        self._script_menu_action(
            menu, "video", "Frame OCR Subtitle Scanner…",
            self._open_frame_ocr_scanner,
            tip="Auto-detect burned-in subtitles from video frames with custom capture zone",
        )
        act_exp = self._script_menu_action(
            menu, "download", "Export script…",
            lambda: self.open_export_dialog(script_only=True),
        )
        act_exp.setEnabled(n > 0)

    def _current_script_task_id(self) -> int:
        viewing = int(getattr(self, "_viewing_task", -1) or -1)
        if viewing >= 0 and hasattr(self, "_task_by_id") and self._task_by_id(viewing):
            return viewing
        source = str(getattr(self, "selected_file", "") or "")
        if not source:
            return -1
        for task in getattr(self, "_tasks", []) or []:
            if str(task.get("source") or "") == source:
                return int(task.get("id") or -1)
        return -1

    def _retry_script_transcript(self):
        """Re-run ASR by restarting the dub job for the current movie."""
        self._retry_script_all()

    def _retry_script_all(self):
        """Full pipeline retry for the movie tied to this script."""
        tid = self._current_script_task_id()
        task = self._task_by_id(tid) if tid >= 0 and hasattr(self, "_task_by_id") else None
        if task and task.get("status") in {"running", "paused"}:
            self.log.warn("That movie is already dubbing")
            return
        if tid >= 0 and hasattr(self, "_push_retries"):
            self._push_retries([tid])
            return
        if bool(getattr(self, "_dub_busy", False) or getattr(self, "_flight", None)):
            self.log.warn("Dub already running")
            return
        source = str(getattr(self, "selected_file", "") or "")
        if source and os.path.isfile(source) and hasattr(self, "_begin_dub_jobs"):
            if hasattr(self, "_retry_environment_ready") and not self._retry_environment_ready():
                return
            self._begin_dub_jobs([source])
            self.log.info("Retry all · starting dub")
            return
        self.log.warn("Retry all · no movie source for this script")

    def _begin_script_job(self) -> JobControl:
        """Start a cancellable script worker (TTS retry / regenerate / gender)."""
        self._cancel_script_job()
        control = JobControl()
        self._script_control = control
        return control

    def _cancel_script_job(self):
        """Soft-cancel the active script worker (Escape or new dub job)."""
        control = getattr(self, "_script_control", None)
        if control is None or control.cancelled:
            return
        control.cancel()
        self.log.info("Stopping script job…")

    def _end_script_job(self):
        self._script_worker = None
        self._script_control = None

    @staticmethod
    def _is_script_cancelled(message: object) -> bool:
        text = str(message or "")
        return text == "Dub stopped" or isinstance(message, JobCancelled)

    def _resynthesize_rows(self, rows: list[int]):
        """Re-speak selected lines with their TTS voices and refresh the timeline."""
        rows = [row for row in rows if 0 <= row < len(self._segments)]
        if not rows or self._script_worker is not None:
            return
        lead, co_star = self._primary_voices()
        sync_mode = (
            self.combo_sync_mode.currentData()
            if hasattr(self, "combo_sync_mode")
            else "stretch"
        ) or "stretch"
        work = []
        for row in rows:
            seg = self._segments[row]
            text = str(seg.get("translated_text") or seg.get("text") or "").strip()
            voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or lead or co_star or "")
            if not text or not voice:
                continue
            ref_wav = str(seg.get("reference_wav") or (seg.get("clone_voice") or {}).get("reference_wav") or "")
            pitch_val = float(seg.get("pitch_offset") or (seg.get("clone_voice") or {}).get("pitch_offset_hz") or 0.0)
            work.append({
                "row": row,
                "text": text,
                "voice": voice,
                "start": seg.get("start", ""),
                "end": seg.get("end", ""),
                "start_sec": seg.get("start_sec"),
                "end_sec": seg.get("end_sec"),
                "reference_wav": ref_wav,
                "pitch": pitch_val,
                "performance": seg.get("performance") if isinstance(seg.get("performance"), dict) else None,
            })
        if not work:
            self.log.warn("Retry TTS · no speakable lines")
            return

        from claynext.gui.dialogs.env_alert import ensure_job_environment

        sample_voice = str(work[0].get("voice") or lead or "")
        if not ensure_job_environment(
            self,
            voice_id=sample_voice,
            secondary_voice_id=str(co_star or ""),
            asr_model=None,
            check_stems=False,
            title="Download TTS environment",
        ):
            self.log.warn("Retry TTS blocked — missing environment")
            return

        control = self._begin_script_job()
        self.table_spinner.start()
        self.log.info(f"Retry TTS · {len(work)} line(s) · Esc to stop")

        def _job(items=work, mode=sync_mode, progress_callback=None):
            from claynext.adapters.ffmpeg_service import fit_duration

            folder = CACHE_DIR / "script_tts"
            folder.mkdir(parents=True, exist_ok=True)
            if mode == "natural":
                min_t, max_t = 0.95, 1.60
            elif mode == "subtle":
                min_t, max_t = 0.85, 2.00
            else:
                min_t, max_t = 0.65, 2.80
            out = []
            total = len(items)
            for i, item in enumerate(items):
                control.checkpoint()
                if progress_callback:
                    progress_callback(int((i / max(1, total)) * 100), f"TTS {i + 1}/{total}")
                perf = item.get("performance") or None
                delivery = f"{perf.get('style')}:{perf.get('intensity')}" if perf else ""
                digest = hashlib.sha1(
                    f"{item['voice']}\n{item['text']}\n{item.get('pitch', 0.0)}\n{delivery}".encode("utf-8")
                ).hexdigest()[:10]
                raw = str(folder / f"row_{item['row']}_{digest}.mp3")
                fitted = str(folder / f"row_{item['row']}_{digest}_fit.wav")
                TTSEngine.synthesize(
                    item["text"],
                    item["voice"],
                    raw,
                    pitch=float(item.get("pitch") or 0.0),
                    reference_wav=str(item.get("reference_wav") or ""),
                    performance=perf,
                )
                control.checkpoint()
                start = float(item.get("start_sec") or timestamp_to_sec(item.get("start", "")))
                end = float(item.get("end_sec") or timestamp_to_sec(item.get("end", "")))
                slot = max(0.15, end - start) if end > start else 2.0
                fit_duration(raw, fitted, slot, min_tempo=min_t, max_tempo=max_t, pad_or_trim=False, never_trim=True)
                from claynext.adapters.ffmpeg_service import probe_duration
                actual_dur = probe_duration(fitted) if os.path.isfile(fitted) else slot
                control.checkpoint()
                out.append({
                    "row": item["row"],
                    "audio_path": fitted,
                    "start_ms": int(start * 1000),
                    "duration_sec": round(actual_dur, 2),
                    "voice_id": item["voice"],
                })
            if progress_callback:
                progress_callback(100, "TTS ready")
            return out

        worker = Worker(_job)
        worker.signals.result.connect(self._on_resynth_ready)
        worker.signals.error.connect(self._on_resynth_error)
        worker.signals.finished.connect(self._on_resynth_finished)
        self._script_worker = worker
        self.thread_pool.start(worker)

    def _on_resynth_ready(self, result):
        rows_updated: list[int] = []
        for item in result if isinstance(result, list) else []:
            if not isinstance(item, dict):
                continue
            row = int(item.get("row", -1))
            if not (0 <= row < len(self._segments)):
                continue
            seg = self._segments[row]
            path = str(item.get("audio_path") or "")
            if path and os.path.isfile(path):
                seg["audio_path"] = path
            if item.get("start_ms") is not None:
                seg["start_ms"] = int(item["start_ms"])
            if item.get("duration_sec") is not None:
                seg["duration_sec"] = float(item["duration_sec"])
                seg["duration"] = f"{float(item['duration_sec']):.1f}s"
            voice = str(item.get("voice_id") or "")
            if voice:
                seg["voice_id"] = voice
                seg["tts_voice_hint"] = voice
            rows_updated.append(row)
        if rows_updated:
            self._refresh_row(rows_updated[0])
            self.log.success(f"Retry TTS · {len(rows_updated)} line(s) updated")
        else:
            self.log.warn("Retry TTS · no audio written")

    def _on_resynth_error(self, message: str, _stack: str):
        if self._is_script_cancelled(message):
            self.log.info("Retry TTS stopped")
            return
        self.log.error(f"Retry TTS failed · {message}")
        QMessageBox.warning(self, "Retry TTS", message)

    def _on_resynth_finished(self):
        self._end_script_job()
        self.table_spinner.stop()

    def _regenerate_rows(self, rows: list[int], *, force_fit: bool = False):
        rows = [row for row in rows if 0 <= row < len(self._segments)]
        if not rows or self._script_worker is not None:
            return
        lines = []
        for row in rows:
            seg = self._segments[row]
            lines.append({
                "id": seg.get("id", row + 1),
                "text": seg.get("original_text") or seg.get("text") or "",
                "original_text": seg.get("original_text") or seg.get("text") or "",
                "start": seg.get("start", ""),
                "end": seg.get("end", ""),
                "start_sec": seg.get("start_sec"),
                "end_sec": seg.get("end_sec"),
                "duration_sec": seg.get("duration_sec"),
                "recommended_syllables": seg.get("recommended_syllables") or {},
                "speed_tolerance": seg.get("speed_tolerance") or {},
                "speaker": seg.get("speaker") or "",
            })
        self._regen_rows = rows
        control = self._begin_script_job()
        target_lang = self.combo_lang.currentText()
        source_lang = self.combo_source_lang.currentText()
        translator = self.combo_translator.currentData() or "auto"
        ollama_model = self.edit_ollama.text().strip() or "qwen3:8b"
        self.table_spinner.start()

        def _job(progress_callback=None):
            def _ping(pct: int, msg: str):
                control.checkpoint()
                if progress_callback:
                    progress_callback(pct, msg)

            control.checkpoint()
            store = getattr(self, "store", None)
            def _flag(key: str, default: str = "1") -> bool:
                if store is None:
                    return default == "1"
                return store.get_setting("dub", key, default) == "1"

            return TranslateEngine.translate_subtitles(
                lines,
                target_lang,
                source_lang=source_lang,
                translator=translator,
                ollama_model=ollama_model,
                fit_duration=True if force_fit else _flag("translate_fit_duration"),
                use_slang=True if force_fit else _flag("translate_slang"),
                use_expression=True if force_fit else _flag("translate_expression"),
                progress_callback=_ping,
            )

        worker = Worker(_job)
        worker.signals.result.connect(self._on_regen_ready)
        worker.signals.error.connect(self._on_regen_error)
        worker.signals.finished.connect(self._on_regen_finished)
        self._script_worker = worker
        self.thread_pool.start(worker)
        action_name = "Fitting" if force_fit else "Regenerating"
        self.log.info(f"{action_name} {len(rows)} line(s) to slot timing · Esc to stop")

    def _on_regen_ready(self, result):
        rows = list(self._regen_rows)
        lines = result if isinstance(result, list) else []
        changed = 0
        for row, line in zip(rows, lines):
            if not isinstance(line, dict) or not (0 <= row < len(self._segments)):
                continue
            text = str(line.get("translated_text") or "").strip()
            if not text or text == str(self._segments[row].get("translated_text") or "").strip():
                continue
            self._propose_line(row, {"translated_text": text})
            changed += 1
        focus = rows[0] if rows else -1
        self._refresh_row(focus)
        if changed:
            self.log.success(f"{changed} pending version(s) · right-click to Accept or Reverse")
        else:
            self.log.info("Regenerate kept the current line")

    def _on_regen_error(self, message: str, _stack: str):
        if self._is_script_cancelled(message):
            self.log.info("Regenerate stopped")
            return
        self.log.error(f"Regenerate failed · {message}")
        QMessageBox.warning(self, "Regenerate", message)

    def _on_regen_finished(self):
        self._end_script_job()
        self._regen_rows = []
        self.table_spinner.stop()

    def _translate_transcript_direct(self, rows: list[int] | None = None):
        """Translate script lines directly with AI, updating the Dub track instantly without full dub jobs."""
        segs = getattr(self, "_segments", None) or []
        if not segs:
            if hasattr(self, "log"):
                self.log.warn("No transcript lines to translate")
            return
        if getattr(self, "_script_worker", None) is not None:
            if hasattr(self, "log"):
                self.log.warn("Another script job is already running")
            return

        if rows is None:
            selected = self._selected_rows() if hasattr(self, "_selected_rows") else []
            rows = list(selected) if selected else list(range(len(segs)))

        valid_rows = [
            r for r in rows
            if 0 <= r < len(segs) and str(segs[r].get("text") or segs[r].get("original_text") or "").strip()
        ]
        if not valid_rows:
            if hasattr(self, "log"):
                self.log.warn("No text found in selected transcript lines")
            return

        lines = []
        for r in valid_rows:
            seg = segs[r]
            orig = str(seg.get("original_text") or seg.get("text") or "").strip()
            lines.append({
                "id": seg.get("id", r + 1),
                "text": orig,
                "original_text": orig,
                "start": seg.get("start", ""),
                "end": seg.get("end", ""),
                "start_sec": seg.get("start_sec"),
                "end_sec": seg.get("end_sec"),
                "duration_sec": seg.get("duration_sec"),
                "recommended_syllables": seg.get("recommended_syllables") or {},
                "speed_tolerance": seg.get("speed_tolerance") or {},
                "speaker": seg.get("speaker") or "",
            })

        self._direct_translate_rows = valid_rows
        control = self._begin_script_job()
        target_lang = self.combo_lang.currentText() if hasattr(self, "combo_lang") else "Khmer"
        source_lang = self.combo_source_lang.currentText() if hasattr(self, "combo_source_lang") else "auto"
        translator = (self.combo_translator.currentData() or "auto") if hasattr(self, "combo_translator") else "auto"
        ollama_model = (self.edit_ollama.text().strip() or "qwen3:8b") if hasattr(self, "edit_ollama") else "qwen3:8b"

        if hasattr(self, "table_spinner"):
            self.table_spinner.start()
        if hasattr(self, "log"):
            self.log.info(f"✨ Translating {len(valid_rows)} transcript line(s) → {target_lang} ({translator})… · Esc to stop")

        def _job(progress_callback=None):
            def _ping(pct: int, msg: str):
                control.checkpoint()
                if progress_callback:
                    progress_callback(pct, msg)

            control.checkpoint()
            store = getattr(self, "store", None)
            def _flag(key: str, default: str = "1") -> bool:
                if store is None:
                    return default == "1"
                return store.get_setting("dub", key, default) == "1"

            return TranslateEngine.translate_subtitles(
                lines,
                target_lang,
                source_lang=source_lang,
                translator=translator,
                ollama_model=ollama_model,
                fit_duration=_flag("translate_fit_duration"),
                use_slang=_flag("translate_slang"),
                use_expression=_flag("translate_expression"),
                progress_callback=_ping,
            )

        worker = Worker(_job)
        worker.signals.result.connect(self._on_direct_translate_ready)
        worker.signals.error.connect(self._on_direct_translate_error)
        worker.signals.finished.connect(self._on_direct_translate_finished)
        self._script_worker = worker
        self.thread_pool.start(worker)

    def _on_direct_translate_ready(self, result):
        rows = getattr(self, "_direct_translate_rows", []) or []
        lines = result if isinstance(result, list) else []
        by_id = {str(item.get("id")): item for item in lines if isinstance(item, dict)}

        updated = 0
        for r, line_item in zip(rows, lines):
            if 0 <= r < len(self._segments):
                seg = self._segments[r]
                res_line = by_id.get(str(seg.get("id", r + 1))) or line_item
                fresh = str(res_line.get("translated_text") or res_line.get("khmer_text") or "").strip()
                if fresh:
                    seg["translated_text"] = fresh
                    seg["text"] = fresh
                    updated += 1

        # Refresh cast & voices so characters match the translated dialogue
        try:
            from claynext.models.gender_voices import apply_character_cast, assign_gender_and_voices
            lead, co_star = self._primary_voices() if hasattr(self, "_primary_voices") else ("", "")
            apply_character_cast(self._segments)
            assign_gender_and_voices(
                self._segments,
                primary_voice=lead,
                secondary_voice=co_star,
                lang=self._voice_lang() if hasattr(self, "_voice_lang") else "",
                force_redetect=False,
            )
        except Exception:
            pass

        if hasattr(self, "_fill_table"):
            self._fill_table(self._segments)
        if hasattr(self, "_ensure_auto_captions"):
            self._ensure_auto_captions(force=True)
        if hasattr(self, "_stash_composition"):
            self._stash_composition()
        if hasattr(self, "log"):
            self.log.success(f"✨ Translation complete: {updated} line(s) translated & updated directly!")

    def _on_direct_translate_error(self, message: str, _stack: str):
        if self._is_script_cancelled(message):
            if hasattr(self, "log"):
                self.log.info("Translation stopped")
            return
        if hasattr(self, "log"):
            self.log.error(f"Translation failed · {message}")
        QMessageBox.warning(self, "Translate Transcript", str(message))

    def _on_direct_translate_finished(self):
        self._end_script_job()
        self._direct_translate_rows = []
        if hasattr(self, "table_spinner"):
            self.table_spinner.stop()

    def _clone_voices_from_movie(self, rows: list[int] | None = None):
        """Extract character speech turns from movie audio, detect tone & pitch, and clone voices."""
        if not self._segments:
            if hasattr(self, "log"):
                self.log.warn("Clone voices · no script lines yet")
            return
        if self._script_worker is not None:
            if hasattr(self, "log"):
                self.log.warn("Another script job is already running")
            return

        media_source = str(getattr(self, "selected_file", "") or "")
        if not media_source or not os.path.isfile(media_source):
            tid = self._current_script_task_id()
            task = self._task_by_id(tid) if tid >= 0 and hasattr(self, "_task_by_id") else None
            if task and task.get("source") and os.path.isfile(str(task.get("source"))):
                media_source = str(task.get("source"))

        if not media_source or not os.path.isfile(media_source):
            if hasattr(self, "log"):
                self.log.warn("Clone voices · original movie file not found")
            return

        from claynext.models.voice_clone import clone_character_voices_from_movie

        control = self._begin_script_job()
        if hasattr(self, "table_spinner"):
            self.table_spinner.start()
        if hasattr(self, "log"):
            self.log.info("🎭 Analyzing movie audio & cloning character voices… · Esc to stop")

        def _job(progress_callback=None):
            def _ping(pct: int, msg: str):
                control.checkpoint()
                if progress_callback:
                    progress_callback(pct, msg)

            return clone_character_voices_from_movie(
                media_source,
                self._segments,
                progress_callback=_ping,
            )

        worker = Worker(_job)
        worker.signals.result.connect(self._on_clone_ready)
        worker.signals.error.connect(self._on_clone_error)
        worker.signals.finished.connect(self._on_clone_finished)
        self._script_worker = worker
        self.thread_pool.start(worker)

    def _on_clone_ready(self, profiles: dict):
        if hasattr(self, "_fill_table"):
            self._fill_table(self._segments)
        if hasattr(self, "_stash_composition"):
            self._stash_composition()
        count = len(profiles) if isinstance(profiles, dict) else 0
        if hasattr(self, "log"):
            self.log.success(f"🎭 Voice clone ready: {count} character voice(s) extracted with movie tone & pitch!")
        QMessageBox.information(
            self,
            "Voice Clone Ready",
            f"Successfully cloned {count} character voice(s) directly from the movie audio!\n\n"
            f"The actor's tone, pitch frequency, and vocal timbre will be copied automatically when synthesizing dialogue.",
        )

    def _on_clone_error(self, message: str, _stack: str):
        if self._is_script_cancelled(message):
            if hasattr(self, "log"):
                self.log.info("Voice clone stopped")
            return
        if hasattr(self, "log"):
            self.log.error(f"Voice clone failed · {message}")
        QMessageBox.warning(self, "Voice Clone", str(message))

    def _on_clone_finished(self):
        self._end_script_job()
        if hasattr(self, "table_spinner"):
            self.table_spinner.stop()


