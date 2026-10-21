"""Line edits, pending versions, cast, and the row menu."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication, QDialog, QMenu

from claynext.gui.worker import Worker
from claynext.gui.views.studio.script_line import LineEditDialog
from claynext.models.dubbing_service import timestamp_to_sec


def _line_snapshot(seg: dict) -> dict:
    original = str(seg.get("original_text") or seg.get("text") or "")
    voice = str(seg.get("voice_id") or seg.get("tts_voice_hint") or "")
    return {
        "speaker": str(seg.get("speaker") or ""),
        "gender": str(seg.get("gender") or "Unknown"),
        "gender_manual": bool(seg.get("gender_manual")),
        "translated_text": str(seg.get("translated_text") or ""),
        "original_text": original,
        "text": str(seg.get("text") or original),
        "tts_voice_hint": str(seg.get("tts_voice_hint") or voice),
        "voice_id": voice,
        "performance": dict(seg.get("performance") or {}) or None,
    }


class ScriptEditTools:
    """Line edits, pending versions, cast, and the row menu."""

    def _visible_rows(self) -> list[int]:
        if not hasattr(self, "table"):
            return list(range(len(self._segments)))
        return [
            row for row in range(min(self.table.rowCount(), len(self._segments)))
            if not self.table.isRowHidden(row)
        ]

    def _selected_rows(self) -> list[int]:
        rows = sorted({item.row() for item in self.table.selectedIndexes()})
        return [row for row in rows if 0 <= row < len(self._segments)]

    def _pending_targets(self, rows: list[int] | None = None) -> list[int]:
        chosen = rows if rows is not None else (self._selected_rows() or self._visible_rows())
        return [row for row in chosen if self._segments[row].get("pending")]

    def _copy_script_lines(self, kind: str = "dub"):
        rows = self._selected_rows() or self._visible_rows()
        lines: list[str] = []
        for row in rows:
            if hasattr(self, "table") and self.table.isRowHidden(row):
                continue
            seg = self._segments[row]
            dub = str(seg.get("translated_text") or "").strip()
            source = str(seg.get("original_text") or seg.get("text") or "").strip()
            start = str(seg.get("start") or "")
            end = str(seg.get("end") or "")
            if kind == "source":
                if source:
                    lines.append(source)
            elif kind == "times":
                text = dub or source
                if text:
                    lines.append(f"{start} → {end}  {text}".strip())
            elif kind == "both":
                if source or dub:
                    lines.append(f"{source}\t{dub}".strip())
            else:
                if dub:
                    lines.append(dub)
                elif source:
                    lines.append(source)
        if not lines:
            self.log.warn("Nothing to copy")
            return
        QApplication.clipboard().setText("\n".join(lines))
        self.log.success(f"Copied {len(lines)} line(s)")

    def _jump_pending(self, direction: int = 1):
        if not self._segments:
            return
        current = self.table.currentRow()
        if current < 0:
            current = 0 if direction > 0 else len(self._segments) - 1
        count = len(self._segments)
        for step in range(1, count + 1):
            row = (current + direction * step) % count
            if self._segments[row].get("pending") and not self.table.isRowHidden(row):
                self.table.selectRow(row)
                item = self.table.item(row, 0)
                if item:
                    self.table.scrollToItem(item)
                return
        self.log.info("No pending versions in the filtered list")

    def _character_names(self) -> list[str]:
        names: list[str] = []
        for seg in self._segments:
            name = str(seg.get("speaker") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def _line_cast_choices(self) -> list[dict]:
        """Created characters first, then TTS voices that are not already names."""
        cast: list[dict] = []
        seen: set[str] = set()
        for row in self._character_rows() if hasattr(self, "_character_rows") else []:
            name = str(row.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            cast.append({
                "label": name,
                "id": str(row.get("voice_id") or ""),
                "gender": str(row.get("gender") or ""),
            })
        for voice in self._cast_voice_choices():
            label = str(voice.get("label") or "")
            if label and label not in seen:
                seen.add(label)
                cast.append(voice)
        return cast

    def _cast_voice_choices(self) -> list[dict]:
        """TTS voices for the target language — used as character cast options."""
        from claynext.models.gender_voices import voices_for_lang

        return voices_for_lang(self._voice_lang())

    def _characters(self) -> list[str]:
        """Character labels: current cast, then TTS voice names for this language."""
        names = self._character_names()
        for voice in self._cast_voice_choices():
            label = str(voice.get("label") or "")
            if label and label not in names:
                names.append(label)
        if not names:
            lead, co = self._primary_voices()
            from claynext.models.gender_voices import voice_display_name
            for vid in (lead, co):
                if vid:
                    label = voice_display_name(vid)
                    if label not in names:
                        names.append(label)
        return names

    def _voice_id_for_label(self, label: str) -> str:
        for voice in self._cast_voice_choices():
            if voice.get("label") == label:
                return str(voice.get("id") or "")
        # Match existing segment by speaker name.
        for seg in self._segments:
            if str(seg.get("speaker") or "") == label:
                return str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
        from claynext.models.gender_voices import voice_display_name
        lead, co = self._primary_voices()
        for vid in (lead, co):
            if vid and voice_display_name(vid) == label:
                return vid
        return ""

    def _voice_lang(self) -> str:
        return str(getattr(self, "combo_lang", None) and self.combo_lang.currentText() or "")

    def _primary_voices(self) -> tuple[str, str]:
        lead = self.combo_voice.currentData() or ""
        co_star = self.combo_voice_sec.currentData() or lead
        return str(lead or ""), str(co_star or lead or "")

    def _voice_for_character(self, name: str, skip: int = -1, gender: str = "") -> str:
        from claynext.models.gender_voices import pick_voice_for_gender

        lead, co_star = self._primary_voices()
        for index, seg in enumerate(self._segments):
            if index == skip:
                continue
            if str(seg.get("speaker") or "") == name:
                voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
                if voice:
                    return voice
        if gender:
            return pick_voice_for_gender(
                gender, primary=lead, secondary=co_star, lang=self._voice_lang(),
            ) or lead
        if name.strip().endswith("2"):
            return co_star
        return lead

    def _reassign_character_voices(self, *, force_redetect: bool = False):
        from claynext.models.gender_voices import assign_gender_and_voices

        lead, co_star = self._primary_voices()
        assign_gender_and_voices(
            self._segments,
            primary_voice=lead,
            secondary_voice=co_star,
            lang=self._voice_lang(),
            force_redetect=force_redetect,
        )

    def _propose_line(self, row: int, changes: dict):
        seg = self._segments[row]
        if not seg.get("pending"):
            seg["committed"] = _line_snapshot(seg)
        seg.update(changes)
        if "gender" in changes:
            seg["gender_manual"] = True
        # If speaker changed without an explicit voice, map TTS name → voice id.
        if changes.get("speaker") and not changes.get("tts_voice_hint") and not changes.get("voice_id"):
            mapped = self._voice_id_for_label(str(changes["speaker"]))
            if mapped:
                seg["tts_voice_hint"] = mapped
                seg["voice_id"] = mapped
        if (changes.get("speaker") or "gender" in changes) and not seg.get("tts_voice_hint"):
            gender = str(seg.get("gender") or "")
            voice = self._voice_for_character(
                str(seg.get("speaker") or ""), skip=row, gender=gender,
            )
            if voice:
                seg["tts_voice_hint"] = voice
                seg["voice_id"] = voice
        seg["pending"] = True

    def _refresh_row(self, row: int):
        self._fill_table(self._segments)
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)

    def _script_menu(self, pos):
        row = self.table.indexAt(pos).row()
        if row < 0 or row >= len(self._segments):
            return
        if row not in self._selected_rows():
            self.table.selectRow(row)
        selected = self._selected_rows() or [row]
        pending = self._pending_targets(selected)
        all_pending = self._pending_targets(self._visible_rows())
        n = len(selected)
        menu = QMenu(self.table)
        menu.setObjectName("media_lib_menu")

        play = menu.addAction("Play from this line")
        play.triggered.connect(lambda: self._play_row(row, 0))
        edit = menu.addAction("Edit line…")
        edit.triggered.connect(lambda: self._edit_line(row))

        characters = menu.addMenu("Change character")
        characters.setObjectName("media_lib_menu")
        # Prefer TTS voice cast list (label + voice id).
        cast = self._cast_voice_choices()
        if cast:
            for voice in cast:
                label = str(voice.get("label") or "")
                vid = str(voice.get("id") or "")
                gender = str(voice.get("gender") or "")
                text = f"{label} · {gender}" if gender and gender != "Unknown" else label
                act = characters.addAction(text)
                act.triggered.connect(
                    lambda _checked=False, speaker=label, voice_id=vid, rows=list(selected):
                    self._change_characters(rows, speaker, voice_id=voice_id)
                )
        else:
            for name in self._characters():
                act = characters.addAction(name)
                act.triggered.connect(
                    lambda _checked=False, speaker=name, rows=list(selected):
                    self._change_characters(rows, speaker)
                )

        gender_menu = menu.addMenu("Set gender")
        gender_menu.setObjectName("media_lib_menu")
        for label in ("Female", "Male", "Unknown"):
            act = gender_menu.addAction(label)
            act.triggered.connect(
                lambda _checked=False, g=label, rows=list(selected):
                self._change_genders(rows, g)
            )
        gender_menu.addSeparator()
        act_auto = gender_menu.addAction("Auto-detect (selected)")
        act_auto.triggered.connect(lambda: self._autodetect_genders(selected))
        act_auto_all = gender_menu.addAction("Auto-detect all · best voices")
        act_auto_all.triggered.connect(lambda: self._autodetect_genders(None, all_lines=True))

        act_ai_cast = menu.addAction("✨ AI Cast & Character Analysis")
        act_ai_cast.triggered.connect(self._run_ai_cast_analysis)

        act_clone = menu.addAction("🎭 Clone Voice from Movie (Actor Tone & Pitch)")
        act_clone.triggered.connect(lambda: self._clone_voices_from_movie(selected))

        regen_label = "Regenerate translation" if n == 1 else f"Regenerate {n} lines"
        regen = menu.addAction(regen_label)
        regen.setEnabled(self._script_worker is None)
        regen.triggered.connect(lambda: self._regenerate_rows(selected))

        menu.addSeparator()
        accept = menu.addAction(
            "Accept version" if len(pending) <= 1 else f"Accept {len(pending)} versions"
        )
        accept.setEnabled(bool(pending))
        accept.triggered.connect(lambda: self._accept_versions(pending))
        reverse = menu.addAction(
            "Reverse version" if len(pending) <= 1 else f"Reverse {len(pending)} versions"
        )
        reverse.setEnabled(bool(pending))
        reverse.triggered.connect(lambda: self._reverse_versions(pending))
        if all_pending and set(all_pending) != set(pending):
            accept_all = menu.addAction(f"Accept all pending ({len(all_pending)})")
            accept_all.triggered.connect(lambda: self._accept_versions(all_pending))
            reverse_all = menu.addAction(f"Reverse all pending ({len(all_pending)})")
            reverse_all.triggered.connect(lambda: self._reverse_versions(all_pending))
        next_pending = menu.addAction("Next pending version")
        next_pending.setEnabled(bool(all_pending))
        next_pending.triggered.connect(lambda: self._jump_pending(1))

        menu.addSeparator()
        copy_menu = menu.addMenu("Copy")
        copy_menu.setObjectName("media_lib_menu")
        copy_menu.addAction("Dub text", lambda: self._copy_script_lines("dub"))
        copy_menu.addAction("Source text", lambda: self._copy_script_lines("source"))
        copy_menu.addAction("Source + dub", lambda: self._copy_script_lines("both"))
        copy_menu.addAction("With times", lambda: self._copy_script_lines("times"))

        menu.addSeparator()
        export_sel = menu.addAction("Export selected as SRT…")
        export_sel.setEnabled(bool(selected))
        export_sel.triggered.connect(lambda: self._export_selected_srt(selected))
        find = menu.addAction("Find in script…")
        find.triggered.connect(self._focus_script_search)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _change_characters(self, rows: list[int], speaker: str, voice_id: str = ""):
        changed = 0
        focus = -1
        vid = voice_id or self._voice_id_for_label(speaker)
        for row in rows:
            if not (0 <= row < len(self._segments)):
                continue
            changes: dict = {"speaker": speaker}
            if vid:
                changes["tts_voice_hint"] = vid
                changes["voice_id"] = vid
                from claynext.models.gender_voices import voice_entry_gender
                g = voice_entry_gender(vid)
                if g != "Unknown":
                    changes["gender"] = g
                    changes["gender_manual"] = True
            self._propose_line(row, changes)
            focus = row if focus < 0 else focus
            changed += 1
        if changed:
            self._refresh_row(focus)
            self.log.info(f"{changed} line(s) · {speaker}" + (f" · {vid}" if vid else "") + " · pending")

    def _change_genders(self, rows: list[int], gender: str):
        from claynext.models.gender_voices import apply_manual_gender

        lead, co_star = self._primary_voices()
        apply_manual_gender(
            self._segments,
            rows,
            gender,
            primary_voice=lead,
            secondary_voice=co_star,
            lang=self._voice_lang(),
            apply_to_character=True,
        )
        for row in rows:
            if 0 <= row < len(self._segments):
                seg = self._segments[row]
                if not seg.get("pending"):
                    seg["committed"] = _line_snapshot({**seg, "gender": gender, "gender_manual": False})
                seg["pending"] = True
        focus = rows[0] if rows else 0
        self._refresh_row(focus)
        self.log.info(f"{len(rows)} line(s) · gender {gender} · voices updated")

    def _autodetect_genders(self, rows: list[int] | None, *, all_lines: bool = False):
        targets = list(range(len(self._segments))) if all_lines else list(rows or [])
        for row in targets:
            if not (0 <= row < len(self._segments)):
                continue
            self._segments[row].pop("gender_manual", None)

        # Prefer Common-Voice wav2vec2 on source audio when torch is installed.
        audio = ""
        for key in ("selected_file", "_media_path"):
            candidate = getattr(self, key, None)
            if candidate and os.path.isfile(str(candidate)):
                audio = str(candidate)
                break
        comps = getattr(self, "_compositions", None) or []
        index = getattr(self, "_composition_index", -1)
        if not audio and 0 <= index < len(comps):
            source = str(comps[index].get("source") or "")
            if source and os.path.isfile(source):
                audio = source

        if getattr(self, "_script_worker", None) is not None:
            return
        control = self._begin_script_job()

        def _job(progress_callback=None):
            from claynext.models.gender_audio import enrich_segments_with_audio_gender, gender_model_available
            from claynext.models.gender_voices import assign_gender_and_voices

            def _ping(pct: int, msg: str):
                control.checkpoint()
                if progress_callback:
                    progress_callback(pct, msg)

            segs = list(self._segments)
            used_audio = False
            control.checkpoint()
            if audio and gender_model_available():
                enrich_segments_with_audio_gender(
                    segs, audio, progress_callback=_ping,
                )
                used_audio = True
            control.checkpoint()
            from claynext.models.gender_voices import apply_character_cast, llm_analyze_cast_and_gender
            llm_analyze_cast_and_gender(segs, progress_callback=_ping)
            apply_character_cast(segs)
            control.checkpoint()
            lead, co_star = self._primary_voices()
            assign_gender_and_voices(
                segs,
                primary_voice=lead,
                secondary_voice=co_star,
                lang=self._voice_lang(),
                force_redetect=True,
            )
            return {"segments": segs, "audio": used_audio}

        self.table_spinner.start()
        worker = Worker(_job)
        worker.signals.result.connect(
            lambda result, focus=(targets[0] if targets else 0): self._on_gender_detect_ready(result, focus)
        )
        worker.signals.error.connect(lambda err, _tb: self._on_gender_detect_error(err))
        worker.signals.finished.connect(self._on_gender_detect_finished)
        self._script_worker = worker
        self.thread_pool.start(worker)
        self.log.info("Detecting gender from dialogue audio… · Esc to stop")

    def _on_gender_detect_ready(self, result, focus: int):
        if not isinstance(result, dict):
            return
        self._segments = list(result.get("segments") or self._segments)
        self._refresh_row(focus)
        if result.get("audio"):
            self.log.success("Common-Voice gender · TTS voices matched per character")
        else:
            self.log.success(
                "Gender auto-detect (text cues) · install uv sync --extra gender for audio model"
            )

    def _on_gender_detect_error(self, err):
        if self._is_script_cancelled(err):
            self.log.info("Gender detect stopped")
            return
        self.log.info(f"Gender detect fallback · {err}")
        self._reassign_character_voices(force_redetect=True)
        self._refresh_row(0)

    def _on_gender_detect_finished(self):
        self._end_script_job()
        self.table_spinner.stop()

    def _edit_line(self, row: int):
        if not (0 <= row < len(self._segments)):
            return
        dialog = LineEditDialog(
            self._segments[row],
            self._line_cast_choices(),
            lang=self._voice_lang(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._propose_line(row, dialog.values())
        self._refresh_row(row)
        self.log.info(f"Line {row + 1} edited · pending version")

    def _accept_versions(self, rows: list[int] | None = None):
        targets = self._pending_targets(rows)
        for row in targets:
            seg = self._segments[row]
            seg["committed"] = _line_snapshot(seg)
            seg["pending"] = False
        if targets:
            self._refresh_row(targets[0])
            self.log.success(f"Accepted {len(targets)} version(s)")

    def _reverse_versions(self, rows: list[int] | None = None):
        targets = self._pending_targets(rows)
        for row in targets:
            seg = self._segments[row]
            previous = seg.get("committed")
            if isinstance(previous, dict):
                seg.update(previous)
            seg["pending"] = False
        if targets:
            self._refresh_row(targets[0])
            self.log.info(f"Reversed {len(targets)} version(s)")

    def _play_row(self, row: int, _col: int):
        if row < 0 or row >= len(self._segments):
            return
        sec = timestamp_to_sec(self._segments[row].get("start", ""))
        self.preview.seek_ms(int(sec * 1000))
        self.preview.player.play()

