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

        act_tr = self._script_menu_action(
            menu, "globe", "Retry translate (all)",
            lambda: self._regenerate_rows(all_rows),
            tip="Re-translate every line from the source text",
        )
        act_tr.setEnabled(n > 0 and not busy)

        if selected:
            act_tr_sel = self._script_menu_action(
                menu, "globe", f"Retry translate ({len(selected)} selected)",
                lambda rows=list(selected): self._regenerate_rows(rows),
                tip="Re-translate only the selected lines",
            )
            act_tr_sel.setEnabled(not busy)

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
        act_all = self._script_menu_action(
            menu, "refresh", "Retry full dub",
            self._retry_script_all,
            tip="Full redub · transcript → translate → TTS → mix",
        )
        act_all.setEnabled(can_retry and not busy)

    def _fill_script_actions_menu(self):
        menu = getattr(self, "_script_actions_menu", None)
        if menu is None:
            return
        menu.clear()
        n = len(self._segments)
        busy = self._script_worker is not None or bool(getattr(self, "_dub_busy", False))
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
            menu, "sparkles", "Auto-detect gender · best voices",
            lambda: self._autodetect_genders(None, all_lines=True),
            tip="Match character gender and assign TTS voices",
        )
        act_gender.setEnabled(n > 0 and not busy)

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
        if bool(getattr(self, "_dub_busy", False)):
            self.log.warn("Dub already running")
            return
        from claynext.gui.dialogs.env_alert import ensure_job_environment

        lead, co = self._primary_voices()
        asr_model = (
            self.combo_model.currentText()
            if hasattr(self, "combo_model")
            else "whisper-small"
        )
        if not ensure_job_environment(
            self,
            voice_id=str(lead or ""),
            secondary_voice_id=str(co or ""),
            asr_model=str(asr_model or ""),
            title="Download environment",
        ):
            self.log.warn("Retry all blocked — missing environment")
            return
        tid = self._current_script_task_id()
        if tid >= 0 and hasattr(self, "_retry_task"):
            self._retry_task(tid)
            self.log.info("Retry all · queued full dub pass")
            return
        source = str(getattr(self, "selected_file", "") or "")
        if source and os.path.isfile(source) and hasattr(self, "_begin_dub_jobs"):
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
            work.append({
                "row": row,
                "text": text,
                "voice": voice,
                "start": seg.get("start", ""),
                "end": seg.get("end", ""),
                "start_sec": seg.get("start_sec"),
                "end_sec": seg.get("end_sec"),
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
                min_t, max_t = 1.0, 1.0
            elif mode == "subtle":
                min_t, max_t = 0.85, 1.25
            else:
                min_t, max_t = 0.65, 1.85
            out = []
            total = len(items)
            for i, item in enumerate(items):
                control.checkpoint()
                if progress_callback:
                    progress_callback(int((i / max(1, total)) * 100), f"TTS {i + 1}/{total}")
                digest = hashlib.sha1(
                    f"{item['voice']}\n{item['text']}".encode("utf-8")
                ).hexdigest()[:10]
                raw = str(folder / f"row_{item['row']}_{digest}.mp3")
                fitted = str(folder / f"row_{item['row']}_{digest}_fit.wav")
                TTSEngine.synthesize(item["text"], item["voice"], raw)
                control.checkpoint()
                start = float(item.get("start_sec") or timestamp_to_sec(item.get("start", "")))
                end = float(item.get("end_sec") or timestamp_to_sec(item.get("end", "")))
                slot = max(0.15, end - start) if end > start else 2.0
                fit_duration(raw, fitted, slot, min_tempo=min_t, max_tempo=max_t, pad_or_trim=True)
                control.checkpoint()
                out.append({
                    "row": item["row"],
                    "audio_path": fitted,
                    "start_ms": int(start * 1000),
                    "duration_sec": round(slot, 2),
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

    def _regenerate_rows(self, rows: list[int]):
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
        ollama_model = self.edit_ollama.text().strip() or "qwen2.5:7b"
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
                fit_duration=_flag("translate_fit_duration"),
                use_slang=_flag("translate_slang"),
                use_expression=_flag("translate_expression"),
                progress_callback=_ping,
            )

        worker = Worker(_job)
        worker.signals.result.connect(self._on_regen_ready)
        worker.signals.error.connect(self._on_regen_error)
        worker.signals.finished.connect(self._on_regen_finished)
        self._script_worker = worker
        self.thread_pool.start(worker)
        self.log.info(f"Regenerating {len(rows)} line(s) · Esc to stop")

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

