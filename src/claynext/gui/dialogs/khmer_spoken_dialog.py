"""
Khmer Spoken Dataset / Gemini Teacher dialog (KSLD milestone 1).

Import dialogue → generate Gemini candidates → human review → export gold →
offline eval → optional Gemini TTS preview. Cyber Dark tokens; heavy work via Worker.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from claynext.constants.theme_constants import COLOR_ACCENT_CYAN, COLOR_TEXT_MUTED
from claynext.gui.worker import Worker
from claynext.models.khmer_spoken.datasets.khmer_human_review import apply_review_decision
from claynext.models.khmer_spoken.paths import (
    DEFAULT_FIXTURE,
    TTS_PREVIEW_DIR,
    ensure_khmer_spoken_dirs,
)
from claynext.models.khmer_spoken.schema import DialogueExample
from claynext.models.khmer_spoken.tts.gemini_voice_registry import list_preview_voices
from claynext.models.khmer_spoken.workflow import (
    load_or_import_workspace,
    save_workspace,
    worker_export_gold,
    worker_generate_candidates,
    worker_run_eval,
    worker_tts_preview,
)


class KhmerSpokenDialog(QDialog):
    """Minimal Gemini Teacher / KSLD workspace for milestone 1."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Khmer Spoken Dataset · Gemini Teacher")
        self.setMinimumSize(960, 640)
        self.resize(1100, 720)
        self.setModal(True)
        self.thread_pool = QThreadPool.globalInstance()
        self._worker: Worker | None = None
        self._examples: list[DialogueExample] = []
        self._player: QMediaPlayer | None = None
        self._audio: QAudioOutput | None = None
        ensure_khmer_spoken_dirs()
        self._build_ui()
        self._reload(DEFAULT_FIXTURE if DEFAULT_FIXTURE.is_file() else None)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Khmer Spoken Dataset · Gemini Teacher")
        title.setObjectName("settings_feature_title")
        header.addWidget(title)
        badge = QLabel("AI Studio · not Vertex SFT")
        badge.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; padding: 2px 8px;")
        header.addWidget(badge)
        header.addStretch()
        self.lbl_counts = QLabel("")
        self.lbl_counts.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        header.addWidget(self.lbl_counts)
        root.addLayout(header)

        notice = QLabel(
            "Synthetic Gemini candidates are not gold. Native Khmer human review "
            "(verified_by + verified_at) is required before export. "
            "Vertex supervised fine-tuning and local LoRA are separate paths. "
            "Speech voice training lives in Tools → Voice Training."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        root.addWidget(notice)

        actions = QHBoxLayout()
        for label, slot, secondary in (
            ("Import JSONL…", self._import_jsonl, True),
            ("Load fixture (100)", self._load_fixture, True),
            ("Generate candidates", self._generate, False),
            ("Export gold version", self._export_gold, False),
            ("Run evaluation", self._run_eval, True),
            ("TTS preview", self._tts_preview, True),
        ):
            btn = QPushButton(label)
            if secondary:
                btn.setObjectName("btn_secondary")
            btn.clicked.connect(slot)
            actions.addWidget(btn)
        actions.addStretch()
        root.addLayout(actions)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Source", "Candidate / stub", "Status", "License", "Notes"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_select)
        root.addWidget(self.table, 1)

        review = QHBoxLayout()
        self.edit_approved = QTextEdit()
        self.edit_approved.setPlaceholderText("Approved Khmer text (edit before approve/gold)…")
        self.edit_approved.setFixedHeight(72)
        review.addWidget(self.edit_approved, 2)

        side = QVBoxLayout()
        self.edit_reviewer = QLineEdit()
        self.edit_reviewer.setPlaceholderText("verified_by (native reviewer id)")
        side.addWidget(self.edit_reviewer)
        self.edit_notes = QLineEdit()
        self.edit_notes.setPlaceholderText("Reviewer notes")
        side.addWidget(self.edit_notes)
        row_btns = QHBoxLayout()
        for label, decision in (
            ("Approve", "approve"),
            ("Reject", "reject"),
            ("Needs changes", "needs_changes"),
            ("Promote gold", "gold"),
        ):
            btn = QPushButton(label)
            btn.setObjectName("btn_secondary")
            btn.clicked.connect(lambda _=False, d=decision: self._apply_decision(d))
            row_btns.addWidget(btn)
        side.addLayout(row_btns)
        review.addLayout(side, 1)
        root.addLayout(review)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(14)
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.lbl_status)
        root.addLayout(progress_row)

        footer = QHBoxLayout()
        voices = ", ".join(v["name"] for v in list_preview_voices()[:3])
        tip = QLabel(f"Gemini TTS voices (unverified): {voices}… · accent {COLOR_ACCENT_CYAN}")
        tip.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        footer.addWidget(tip)
        footer.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setObjectName("btn_secondary")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    def _reload(self, path: Path | None) -> None:
        try:
            self._examples = load_or_import_workspace(path)
            save_workspace(self._examples)
        except Exception as exc:
            QMessageBox.warning(self, "Khmer Spoken", f"Could not load:\n{exc}")
            self._examples = []
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        counts: dict[str, int] = {}
        for ex in self._examples:
            counts[ex.review_status] = counts.get(ex.review_status, 0) + 1
            row = self.table.rowCount()
            self.table.insertRow(row)
            cand = ex.preferred_khmer() or ex.stub_khmer
            values = [
                ex.id,
                ex.source_text[:120],
                cand[:120],
                ex.review_status,
                ex.license_type,
                (ex.reviewer_notes or "")[:80],
            ]
            for col, val in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(val))
        pending = counts.get("pending_native_review", 0)
        gold = counts.get("gold", 0)
        self.lbl_counts.setText(
            f"{len(self._examples)} rows · pending {pending} · gold {gold}"
        )

    def _selected(self) -> DialogueExample | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._examples):
            return self._examples[idx]
        return None

    def _on_select(self) -> None:
        ex = self._selected()
        if ex is None:
            return
        self.edit_approved.setPlainText(ex.approved_text or ex.preferred_khmer())
        self.edit_notes.setText(ex.reviewer_notes)

    def _import_jsonl(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import dialogue JSONL", str(DEFAULT_FIXTURE.parent), "JSONL (*.jsonl)"
        )
        if path:
            self._reload(Path(path))

    def _load_fixture(self) -> None:
        self._reload(DEFAULT_FIXTURE)

    def _apply_decision(self, decision: str) -> None:
        ex = self._selected()
        if ex is None:
            QMessageBox.information(self, "Khmer Spoken", "Select a row first.")
            return
        reviewer = self.edit_reviewer.text().strip()
        try:
            updated, issues = apply_review_decision(
                ex,
                decision=decision,
                verified_by=reviewer,
                approved_text=self.edit_approved.toPlainText(),
                notes=self.edit_notes.text(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Khmer Spoken", str(exc))
            return
        errors = [i for i in issues if i.severity == "error"]
        if errors and decision in {"approve", "gold"}:
            QMessageBox.warning(
                self,
                "Khmer Spoken",
                "Cannot promote:\n" + "\n".join(f"• {i.message}" for i in errors),
            )
        save_workspace(self._examples)
        self._refresh_table()
        self.lbl_status.setText(f"{updated.id} → {updated.review_status}")

    def _busy(self) -> bool:
        if self._worker is not None:
            QMessageBox.information(self, "Khmer Spoken", "A job is already running.")
            return True
        return False

    def _start(self, fn, on_result) -> None:
        if self._busy():
            return
        self.progress.setValue(0)
        self.lbl_status.setText("Working…")
        worker = Worker(fn)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self._worker = worker
        self.thread_pool.start(worker)

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress.setValue(int(pct))
        self.lbl_status.setText(msg)

    def _on_error(self, message: str, _trace: str) -> None:
        QMessageBox.warning(self, "Khmer Spoken", message)
        self.lbl_status.setText("Error")

    def _on_finished(self) -> None:
        self._worker = None
        self.progress.setValue(100)

    def _generate(self) -> None:
        examples = list(self._examples)

        def job(progress_callback=None):
            return worker_generate_candidates(
                examples, limit=20, progress_callback=progress_callback
            )

        def done(report):
            if report.get("skipped"):
                QMessageBox.information(
                    self,
                    "Khmer Spoken",
                    report.get("error") or "Candidate generation skipped (no API key).",
                )
            self._examples = report.get("examples") or self._examples
            save_workspace(self._examples)
            self._refresh_table()
            self.lbl_status.setText(
                f"Updated {report.get('updated', 0)} · skipped {report.get('skipped_rows', 0)}"
            )

        self._start(job, done)

    def _export_gold(self) -> None:
        examples = list(self._examples)

        def job(progress_callback=None):
            return worker_export_gold(examples, progress_callback=progress_callback)

        def done(result):
            msg = (
                f"Exported {result.get('count', 0)} gold rows.\n"
                f"{result.get('path', '')}\n"
                f"Rejected: {len(result.get('rejected') or [])}"
            )
            QMessageBox.information(self, "Khmer Spoken", msg)
            self.lbl_status.setText(f"Export {result.get('version', '')}")

        self._start(job, done)

    def _run_eval(self) -> None:
        examples = list(self._examples)

        def job(progress_callback=None):
            return worker_run_eval(examples, use_gemini_judge=False, progress_callback=progress_callback)

        def done(report):
            summary = report.get("summary") or {}
            lines = [f"{k}: overlap={v.get('mean_overlap')} khmer={v.get('khmer_script_rate')}"
                     for k, v in summary.items()]
            QMessageBox.information(
                self,
                "Khmer Spoken",
                "Offline benchmark written:\n"
                + (report.get("path") or "")
                + "\n\n"
                + "\n".join(lines[:8]),
            )
            self.lbl_status.setText("Evaluation done")

        self._start(job, done)

    def _tts_preview(self) -> None:
        ex = self._selected()
        text = (self.edit_approved.toPlainText() or (ex.preferred_khmer() if ex else "")).strip()
        if not text:
            QMessageBox.information(self, "Khmer Spoken", "Select a row with Khmer text first.")
            return
        out = TTS_PREVIEW_DIR / "preview.wav"

        def job(progress_callback=None):
            return worker_tts_preview(text, out, progress_callback=progress_callback)

        def done(result):
            tts = result.get("tts") or {}
            if tts.get("skipped") or not tts.get("ok"):
                QMessageBox.information(
                    self,
                    "Khmer Spoken",
                    tts.get("error")
                    or f"TTS preview skipped ({tts.get('reason') or 'unavailable'}).",
                )
                self.lbl_status.setText("TTS skipped")
                return
            path = tts.get("path") or ""
            self._play_wav(path)
            self.lbl_status.setText(f"TTS · {tts.get('model', '')}")

        self._start(job, done)

    def _play_wav(self, path: str) -> None:
        if not path or not Path(path).is_file():
            return
        if self._player is None:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def closeEvent(self, event) -> None:
        if self._player is not None:
            self._player.stop()
        super().closeEvent(event)
