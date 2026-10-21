"""Import a script and export subtitles or the dubbed movie."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialog

from claynext.adapters.ffmpeg_service import (
    concat_videos, encode_source_movie, mix_timeline_audio, render_timeline,
)
from claynext.gui.worker import Worker
from claynext.gui.views.studio.helpers import export_segments, import_segments
from claynext.gui.views.studio.merge import MergeOrderDialog
from claynext.models.thumbnails import VIDEO_EXTS
from claynext.utils.config import OUTPUTS_DIR


class ScriptExportTools:
    """Import a script and export subtitles or the dubbed movie."""

    def _lines_for_export(self, mode: str) -> list[dict]:
        rows = []
        for seg in self._segments:
            if mode == "current":
                rows.append(seg)
                continue
            if seg.get("pending") and isinstance(seg.get("committed"), dict):
                merged = dict(seg)
                merged.update(seg["committed"])
                rows.append(merged)
                continue
            merged = dict(seg)
            source = str(seg.get("original_text") or seg.get("text") or "")
            merged["translated_text"] = source
            rows.append(merged)
        return rows

    def _export_subtitles(self, fmt: str, mode: str = "current"):
        lines = self._lines_for_export(mode)
        if not lines:
            QMessageBox.information(self, "Export", "No dubbed script lines to export.")
            return
        label = "back" if mode == "back" else "current"
        default_name = f"dubbed_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
        if self.selected_file:
            stem = os.path.splitext(os.path.basename(self.selected_file))[0]
            default_name = f"{stem}_{label}.{fmt}"
        path = str(OUTPUTS_DIR / default_name)
        filter_str = (
            "SubRip Subtitles (*.srt)"
            if fmt == "srt"
            else "WebVTT Subtitles (*.vtt)"
            if fmt == "vtt"
            else "JSON Files (*.json)"
        )
        file_path, _ = QFileDialog.getSaveFileName(self, f"Export {label} {fmt.upper()}", path, filter_str)
        if not file_path:
            return
        try:
            export_segments(file_path, fmt, lines)
            self.log.success(f"Exported {label} {fmt.upper()} → {os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export {fmt.upper()}: {e}")

    def _import_script(self, fmt: str | None = None):
        """Load script lines from SRT / VTT / JSON into the table."""
        if fmt == "srt":
            filter_str = "SubRip Subtitles (*.srt)"
        elif fmt == "vtt":
            filter_str = "WebVTT Subtitles (*.vtt)"
        elif fmt == "json":
            filter_str = "JSON Files (*.json)"
        else:
            filter_str = (
                "Script files (*.srt *.vtt *.json);;"
                "SubRip Subtitles (*.srt);;"
                "WebVTT Subtitles (*.vtt);;"
                "JSON Files (*.json)"
            )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import script", str(OUTPUTS_DIR), filter_str,
        )
        if not file_path:
            return
        if self._segments:
            answer = QMessageBox.question(
                self,
                "Import script",
                f"Replace the current {len(self._segments)} line(s) with this file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            kind = fmt or os.path.splitext(file_path)[1].lstrip(".").lower()
            lines = import_segments(file_path, kind)
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not load script:\n{exc}")
            return
        if not lines:
            QMessageBox.information(self, "Import", "No script lines found in that file.")
            return
        self._fill_table(lines)
        self._update_script_meta()
        if hasattr(self, "_store_project_session"):
            self._store_project_session()
        self.log.success(
            f"Imported {len(lines)} line{'s' if len(lines) != 1 else ''} ← {os.path.basename(file_path)}"
        )

    def _episode_paths(self) -> list[str]:
        ordered: list[str] = []
        pool: list[str] = []
        if hasattr(self, "media_lib"):
            pool.extend(self.media_lib.selected_paths())
            pool.extend(self.media_lib.paths())
        if self.selected_file:
            pool.insert(0, self.selected_file)
        for path in pool:
            if not path or path in ordered or not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() not in VIDEO_EXTS:
                continue
            ordered.append(path)
        return ordered

    def _render_copy(self, source: str, title: str, default_name: str):
        if not source or not os.path.isfile(source):
            QMessageBox.information(self, title, "That file is not ready to render.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, title, str(OUTPUTS_DIR / default_name), "Movie (*.mp4)",
        )
        if not dest:
            return
        if not dest.lower().endswith(".mp4"):
            dest += ".mp4"
        self.table_spinner.start()
        worker = Worker(lambda src, out, progress_callback=None: shutil.copy2(src, out), source, dest)
        worker.signals.result.connect(lambda _path, out=dest: self._on_render_ready(out, title))
        worker.signals.error.connect(self._on_render_error)
        worker.signals.finished.connect(self.table_spinner.stop)
        self.thread_pool.start(worker)

    def _on_render_ready(self, path: str, title: str):
        self.log.success(f"{title} → {os.path.basename(path)}")

    def _on_render_error(self, message: str, _stack: str):
        self.table_spinner.stop()
        self.log.error(f"Render failed · {message}")
        QMessageBox.warning(self, "Render", message)

    def _render_current(self):
        self.open_export_dialog("movie")

    def open_export_dialog(self, kind: str = "", *, script_only: bool = False):
        from claynext.gui.dialogs.export_dialog import ExportDialog, unused_export_path

        source = self.timeline.canvas.media_path or self.selected_file
        stem = os.path.splitext(os.path.basename(source))[0] if source else "dub"
        saved = {}
        key = "dubbing/script_export_options" if script_only else "dubbing/export_options"
        raw = QSettings("Claynext", "ClaynextStudio").value(key, "")
        if raw:
            try:
                saved = json.loads(raw)
            except (TypeError, ValueError):
                saved = {}
        if kind:
            saved["kind"] = kind
        preview = None
        if not script_only:
            host = getattr(self, "stage_host", None)
            if host is not None and host.width() > 8 and host.height() > 8:
                preview = host.grab()
            if (preview is None or preview.isNull()) and hasattr(self, "preview"):
                frame = self.preview.current_frame_image()
                if frame is not None and not frame.isNull():
                    from PySide6.QtGui import QPixmap
                    preview = QPixmap.fromImage(frame)
        dialog = ExportDialog(
            self, folder=str(OUTPUTS_DIR), stem=stem, saved=saved,
            script_only=script_only, source=source or "", preview=preview,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dialog.options()
        opts["path"] = unused_export_path(opts["path"])
        QSettings("Claynext", "ClaynextStudio").setValue(
            key, json.dumps({k: v for k, v in opts.items() if k != "path"}),
        )
        self._run_export(opts)

    def _run_export(self, opts: dict):
        kind = opts["kind"]
        dest = opts["path"]
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        if kind in {"srt", "vtt", "json"}:
            lines = self._lines_for_export(opts["version"])
            if not lines:
                QMessageBox.information(self, "Export", "No script lines to export yet.")
                return
            try:
                export_segments(dest, kind, lines)
                self.log.success(f"Exported {opts['version']} {kind.upper()} → {os.path.basename(dest)}")
            except Exception as exc:
                QMessageBox.critical(self, "Export failed", str(exc))
            return
        source = self.timeline.canvas.media_path or self.selected_file
        if not source or not os.path.isfile(source):
            QMessageBox.information(self, "Export", "Put footage on the timeline first.")
            return
        if kind == "source":
            self._export_source(source, dest, opts["video"] == "h264")
            return
        plan = self.timeline.render_plan()
        work_dir = str(OUTPUTS_DIR / ".render" / datetime.now().strftime("%Y%m%d_%H%M%S"))
        common = dict(
            footage_gain=plan["footage_gain"],
            bed_path=plan["bed_path"],
            bed_keys=plan["bed_keys"],
            work_dir=work_dir,
        )
        if kind == "movie":
            worker = Worker(
                render_timeline, source, dest, plan["voice"], plan["footage_keys"],
                overlays=self.timeline.export_overlays(aspect=self._stage_aspect()) if opts["overlays"] else None,
                segments=list(self._segments),
                audio_bitrate=opts["audio"],
                reencode=opts["video"] == "h264",
                video_filter=plan["video_filter"],
                window=self.timeline.canvas.master_window(),
                **common,
            )
            title = "Render dub"
        else:
            worker = Worker(
                mix_timeline_audio, source, dest, plan["voice"], plan["footage_keys"],
                include_footage=kind == "mix_wav",
                window=self.timeline.canvas.master_window(),
                **common,
            )
            title = "Export mix" if kind == "mix_wav" else "Export voice-over"
        worker.signals.result.connect(
            lambda path, d=work_dir, t=title, k=kind: self._on_timeline_rendered(path, d, t, k)
        )
        self.log.info(f"{title} · {len(plan['voice'])} voice clips · {len(plan['footage_keys'])} key points")
        self._start_export_job(worker, title, source, dest)

    def _export_source(self, source: str, dest: str, reencode: bool):
        def job(src: str, out: str, progress_callback=None) -> str:
            if not reencode:
                if progress_callback:
                    progress_callback(30, "Copying source…")
                shutil.copy2(src, out)
                if progress_callback:
                    progress_callback(100, "Export complete")
                return out
            return encode_source_movie(src, out, progress_callback=progress_callback)

        worker = Worker(job, source, dest)
        worker.signals.result.connect(lambda path: self._on_source_exported(str(path)))
        self._start_export_job(worker, "Export source", source, dest)

    def _start_export_job(self, worker, title: str, source: str, dest: str) -> None:
        from claynext.gui.dialogs.export_progress_dialog import ExportProgressDialog

        previous = getattr(self, "_export_dialog", None)
        if previous is not None:
            previous.close()
        dialog = ExportProgressDialog(self.window() or self, title=title, source=source, dest=dest)
        self._export_dialog = dialog
        worker.signals.progress_fine.connect(dialog.set_progress)
        worker.signals.error.connect(self._on_export_failed)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self.thread_pool.start(worker)

    def _finish_export(self, name: str) -> None:
        dialog = getattr(self, "_export_dialog", None)
        if dialog is not None:
            dialog.succeed(name)

    def _on_export_failed(self, message: str, _stack: str) -> None:
        self.log.error(f"Export failed · {message}")
        dialog = getattr(self, "_export_dialog", None)
        if dialog is not None:
            dialog.fail(message)
            return
        QMessageBox.warning(self, "Export", message)

    def _on_source_exported(self, path: str) -> None:
        self._finish_export(os.path.basename(path))
        self._on_render_ready(path, "Export source")

    def _on_timeline_rendered(self, path: str, work_dir: str, title: str = "Render dub", kind: str = "movie"):
        shutil.rmtree(work_dir, ignore_errors=True)
        if kind == "movie":
            self._output_path = str(path)
            if self.act_open_out:
                self.act_open_out.setEnabled(os.path.isfile(self._output_path))
        self._finish_export(os.path.basename(str(path)))
        self._on_render_ready(str(path), title)

    def _render_source(self):
        source = self.selected_file
        stem = "source"
        if source:
            stem = os.path.splitext(os.path.basename(source))[0] + "_source"
        self._render_copy(source, "Render source", f"{stem}.mp4")

    def _hot_merge(self):
        paths = self._episode_paths()
        if len(paths) < 2:
            QMessageBox.information(self, "Hot merge", "Add at least two source episodes to merge.")
            return
        dialog = MergeOrderDialog(paths, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        ordered = dialog.ordered_paths()
        if len(ordered) < 2:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Hot merge", str(OUTPUTS_DIR / "full_movie.mp4"), "Movie (*.mp4)",
        )
        if not dest:
            return
        if not dest.lower().endswith(".mp4"):
            dest += ".mp4"
        self.table_spinner.start()
        worker = Worker(concat_videos, ordered, dest)
        worker.signals.result.connect(lambda path: self._on_render_ready(path, "Hot merge"))
        worker.signals.error.connect(self._on_render_error)
        worker.signals.finished.connect(self.table_spinner.stop)
        self.thread_pool.start(worker)
        self.log.info(f"Merging {len(ordered)} episodes")

    def _export_selected_srt(self, rows: list[int]):
        lines = []
        for row in rows:
            if 0 <= row < len(self._segments):
                lines.append(self._segments[row])
        if not lines:
            QMessageBox.information(self, "Export", "No lines selected.")
            return
        default_name = f"dubbed_selection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.srt"
        if self.selected_file:
            stem = os.path.splitext(os.path.basename(self.selected_file))[0]
            default_name = f"{stem}_selection.srt"
        path = str(OUTPUTS_DIR / default_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export selected SRT", path, "SubRip Subtitles (*.srt)"
        )
        if not file_path:
            return
        try:
            export_segments(file_path, "srt", lines)
            self.log.success(f"Exported {len(lines)} line(s) → {os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export SRT: {e}")

