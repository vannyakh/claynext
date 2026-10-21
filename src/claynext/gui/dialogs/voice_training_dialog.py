"""
Khmer Cinematic Voice Training prototype dialog.

Import authorized audio → review transcripts → annotate speaker/emotion →
dry-run train. Cyber Dark tokens; heavy work via Worker / QThreadPool.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from claynext.constants.theme_constants import COLOR_ACCENT_EMERALD, COLOR_TEXT_MUTED
from claynext.gui.icons import icon
from claynext.gui.worker import Worker
from claynext.voice_training.datasets.dataset_builder import dataset_summary, load_dataset
from claynext.voice_training.datasets.speech_schema import EMOTIONS, PerformerConsent
from claynext.voice_training.paths import DEMO_CONSENTED_DIR, VOICE_DATASETS_DIR, ensure_voice_dirs


class VoiceTrainingDialog(QDialog):
    """Minimal Voice Training workspace for milestone 1."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Khmer Cinematic Voice Training")
        self.setMinimumSize(920, 620)
        self.resize(1040, 700)
        self.setModal(True)
        self.thread_pool = QThreadPool.globalInstance()
        self._worker: Worker | None = None
        ensure_voice_dirs()
        self._dataset_path = self._default_dataset_path()
        self._segments: list[dict] = []
        self._current_row = -1
        self._build_ui()
        self._reload_dataset()

    def _default_dataset_path(self) -> Path:
        demo = DEMO_CONSENTED_DIR / "dataset.json"
        if demo.is_file():
            return demo
        workspace = VOICE_DATASETS_DIR / "workspace" / "dataset.json"
        return workspace

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Khmer Cinematic Voice Training")
        title.setObjectName("settings_feature_title")
        header.addWidget(title)
        badge = QLabel("Prototype")
        badge.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; padding: 2px 8px;")
        header.addWidget(badge)
        header.addStretch()
        self.lbl_dataset = QLabel("")
        self.lbl_dataset.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        header.addWidget(self.lbl_dataset)
        root.addLayout(header)

        notice = QLabel(
            "Buying or streaming a movie does not grant AI training or voice-cloning rights. "
            "Source license + performer consent (voice_model_training / tts_synthesis) are required."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        root.addWidget(notice)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

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
        btn_demo = QPushButton("Load demo consented")
        btn_demo.setObjectName("btn_secondary")
        btn_demo.clicked.connect(self._load_demo)
        footer.addWidget(btn_demo)
        footer.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setObjectName("btn_secondary")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    def _build_left(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        tools = QHBoxLayout()
        btn_import = QPushButton(icon("folder", size=14), "Import authorized audio…")
        btn_import.setObjectName("btn_primary")
        btn_import.clicked.connect(self._import_audio)
        tools.addWidget(btn_import)
        btn_reload = QPushButton("Reload")
        btn_reload.setObjectName("btn_secondary")
        btn_reload.clicked.connect(self._reload_dataset)
        tools.addWidget(btn_reload)
        tools.addStretch()
        lay.addLayout(tools)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Segment", "Speaker", "Emotion", "Style", "Split", "Transcript"]
        )
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        lay.addWidget(self.table, 1)
        return panel

    def _build_right(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Rights / import meta
        rights = QGroupBox("Rights & consent (required for training)")
        form = QFormLayout(rights)
        self.ed_owner = QLineEdit()
        self.ed_owner.setPlaceholderText("Owner / licensor")
        self.ed_license = QLineEdit()
        self.ed_license.setPlaceholderText("e.g. actor_recording_license")
        self.ed_performer = QLineEdit()
        self.ed_performer.setPlaceholderText("Performer name")
        self.ed_consent_id = QLineEdit()
        self.ed_consent_id.setPlaceholderText("consent_id")
        self.chk_train_use = QCheckBox("permitted: voice_model_training")
        self.chk_train_use.setChecked(True)
        self.chk_tts_use = QCheckBox("permitted: tts_synthesis")
        self.chk_tts_use.setChecked(True)
        form.addRow("Owner", self.ed_owner)
        form.addRow("License", self.ed_license)
        form.addRow("Performer", self.ed_performer)
        form.addRow("Consent ID", self.ed_consent_id)
        form.addRow("", self.chk_train_use)
        form.addRow("", self.chk_tts_use)
        lay.addWidget(rights)

        # Transcript
        transcript = QGroupBox("Transcript review")
        t_lay = QVBoxLayout(transcript)
        self.txt_display = QTextEdit()
        self.txt_display.setPlaceholderText("Display transcript (Khmer)")
        self.txt_display.setFixedHeight(56)
        self.txt_spoken = QTextEdit()
        self.txt_spoken.setPlaceholderText("Spoken / colloquial form")
        self.txt_spoken.setFixedHeight(56)
        t_lay.addWidget(QLabel("Display"))
        t_lay.addWidget(self.txt_display)
        t_lay.addWidget(QLabel("Spoken"))
        t_lay.addWidget(self.txt_spoken)
        lay.addWidget(transcript)

        # Speaker / emotion — inspired by Khmer Dialogue Style Editor mockup
        style_box = QGroupBox("Speaker / emotion annotation")
        s_lay = QVBoxLayout(style_box)

        row_spk = QHBoxLayout()
        row_spk.addWidget(QLabel("Speaker"))
        self.ed_speaker = QLineEdit("spk_01")
        row_spk.addWidget(self.ed_speaker)
        s_lay.addLayout(row_spk)

        s_lay.addWidget(QLabel("ស្ទីលនិយាយ (Speech style)"))
        self.style_group = QButtonGroup(self)
        style_row = QHBoxLayout()
        for key, label in (
            ("formal", "ផ្លូវការ"),
            ("normal", "ធម្មតា"),
            ("spoken", "ភាសានិយាយ"),
            ("youth_slang", "ស្លែងយុវវ័យ"),
        ):
            rb = QRadioButton(label)
            rb.setProperty("style_key", key)
            self.style_group.addButton(rb)
            style_row.addWidget(rb)
            if key == "spoken":
                rb.setChecked(True)
        s_lay.addLayout(style_row)

        s_lay.addWidget(QLabel("អារម្មណ៍តួអង្គ (Emotion)"))
        self.emotion_combo = QComboBox()
        for e in EMOTIONS:
            self.emotion_combo.addItem(e, e)
        s_lay.addWidget(self.emotion_combo)

        s_lay.addWidget(QLabel("កម្រិតពាក្យស្លែង (Slang)"))
        self.slider_slang = QSlider(Qt.Orientation.Horizontal)
        self.slider_slang.setRange(0, 100)
        self.slider_slang.setValue(35)
        s_lay.addWidget(self.slider_slang)

        s_lay.addWidget(QLabel("កម្រិតពាក្យជេរ (Rudeness)"))
        self.slider_rude = QSlider(Qt.Orientation.Horizontal)
        self.slider_rude.setRange(0, 100)
        self.slider_rude.setValue(0)
        s_lay.addWidget(self.slider_rude)

        btn_save = QPushButton("Save segment annotation")
        btn_save.setObjectName("btn_primary")
        btn_save.clicked.connect(self._save_annotation)
        s_lay.addWidget(btn_save)
        lay.addWidget(style_box)

        # Training
        train = QGroupBox("Training")
        tr = QVBoxLayout(train)
        self.model_combo = QComboBox()
        self.model_combo.addItem("khmer-tts-baseline (dry-run)", "khmer-tts-baseline")
        self.chk_dry = QCheckBox("Dry-run (recommended on Intel Mac)")
        self.chk_dry.setChecked(True)
        btn_train = QPushButton("Run fine-tune / dry-run")
        btn_train.setObjectName("btn_secondary")
        btn_train.clicked.connect(self._run_train)
        btn_eval = QPushButton("Run evaluation harness")
        btn_eval.setObjectName("btn_secondary")
        btn_eval.clicked.connect(self._run_eval)
        tr.addWidget(self.model_combo)
        tr.addWidget(self.chk_dry)
        tr.addWidget(btn_train)
        tr.addWidget(btn_eval)
        self.lbl_train_result = QLabel("")
        self.lbl_train_result.setWordWrap(True)
        self.lbl_train_result.setStyleSheet(f"color: {COLOR_ACCENT_EMERALD};")
        tr.addWidget(self.lbl_train_result)
        lay.addWidget(train)
        lay.addStretch()
        return panel

    # ── data ──────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self.lbl_status.setText(msg or ("Working…" if busy else "Ready"))
        if not busy:
            self.progress.setValue(0)

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress.setValue(max(0, min(100, int(pct))))
        self.lbl_status.setText(msg)

    def _reload_dataset(self) -> None:
        path = self._dataset_path
        self.lbl_dataset.setText(str(path))
        self.table.setRowCount(0)
        self._segments = []
        if not path.is_file():
            self.lbl_status.setText("No dataset yet — import authorized audio or load demo.")
            return
        try:
            dataset = load_dataset(path)
        except Exception as exc:
            QMessageBox.warning(self, "Voice Training", f"Could not load dataset:\n{exc}")
            return
        summary = dataset_summary(dataset)
        self.lbl_status.setText(
            f"{summary['segments']} segments · {summary['sessions']} sessions · "
            f"splits {summary['splits']}"
        )
        self._segments = [s.to_dict() for s in dataset.segments]
        self.table.setRowCount(len(self._segments))
        for row, seg in enumerate(self._segments):
            values = [
                seg.get("segment_id", ""),
                seg.get("speaker_id", ""),
                seg.get("emotion", ""),
                seg.get("speaking_style", ""),
                seg.get("train_split", ""),
                (seg.get("transcript_display") or seg.get("transcript_spoken") or "")[:80],
            ]
            for col, text in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(text)))

    def _load_demo(self) -> None:
        demo = DEMO_CONSENTED_DIR / "dataset.json"
        if not demo.is_file():
            QMessageBox.information(
                self,
                "Voice Training",
                f"Demo dataset missing at {demo}. Re-run fixture setup or import media.",
            )
            return
        self._dataset_path = demo
        self._reload_dataset()

    def _on_row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._current_row = -1
            return
        row = rows[0].row()
        self._current_row = row
        if row < 0 or row >= len(self._segments):
            return
        seg = self._segments[row]
        self.txt_display.setPlainText(seg.get("transcript_display") or "")
        self.txt_spoken.setPlainText(seg.get("transcript_spoken") or "")
        self.ed_speaker.setText(seg.get("speaker_id") or "spk_01")
        emo = seg.get("emotion") or "neutral"
        idx = self.emotion_combo.findData(emo)
        if idx < 0:
            idx = self.emotion_combo.findText(emo)
        if idx >= 0:
            self.emotion_combo.setCurrentIndex(idx)
        style = seg.get("speaking_style") or "spoken"
        for btn in self.style_group.buttons():
            if btn.property("style_key") == style:
                btn.setChecked(True)
                break
        self.slider_slang.setValue(int(float(seg.get("slang_level") or 0) * 100))
        self.slider_rude.setValue(int(float(seg.get("rudeness_level") or 0) * 100))

    def _selected_style(self) -> str:
        for btn in self.style_group.buttons():
            if btn.isChecked():
                return str(btn.property("style_key") or "spoken")
        return "spoken"

    def _consent_payload(self) -> list[dict]:
        uses: list[str] = []
        if self.chk_train_use.isChecked():
            uses.append("voice_model_training")
        if self.chk_tts_use.isChecked():
            uses.append("tts_synthesis")
        name = self.ed_performer.text().strip() or "Unknown Performer"
        consent_id = self.ed_consent_id.text().strip()
        if not consent_id:
            return []
        return [
            PerformerConsent(
                name=name,
                consent_id=consent_id,
                permitted_uses=uses,
                restrictions=["no_commercial_movie_stems_without_license"],
                revocable=True,
            ).to_dict()
        ]

    def _import_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import authorized audio / video",
            "",
            "Media (*.wav *.mp3 *.mp4 *.m4a *.flac *.mkv *.mov);;All (*)",
        )
        if not path:
            return
        if not self.ed_owner.text().strip() or not self.ed_license.text().strip():
            QMessageBox.warning(
                self,
                "Rights required",
                "Enter Owner and License type before import. "
                "Commercial movie catalogs without rights must not be used for voice cloning.",
            )
            return

        dataset_dir = self._dataset_path.parent if self._dataset_path.name == "dataset.json" else VOICE_DATASETS_DIR / "workspace"
        performers = self._consent_payload()
        owner = self.ed_owner.text().strip()
        license_type = self.ed_license.text().strip()

        def job(progress_callback=None):
            from claynext.voice_training.pipeline import ingest_and_segment

            return ingest_and_segment(
                path,
                dataset_dir=dataset_dir,
                owner=owner,
                license_type=license_type,
                performers=performers,
                progress_callback=progress_callback,
            )

        self._start_worker(job, on_result=self._on_import_done)

    def _on_import_done(self, result: object) -> None:
        data = result if isinstance(result, dict) else {}
        ds = data.get("dataset_path")
        if ds:
            self._dataset_path = Path(str(ds))
        self._reload_dataset()
        rights = data.get("rights") or {}
        if rights and not rights.get("allowed", True):
            QMessageBox.information(
                self,
                "Import complete (rights note)",
                "Media imported for annotation. Training remains blocked until consent is complete.",
            )

    def _save_annotation(self) -> None:
        if self._current_row < 0 or self._current_row >= len(self._segments):
            QMessageBox.information(self, "Voice Training", "Select a segment first.")
            return
        seg = self._segments[self._current_row]
        try:
            from claynext.voice_training.pipeline import update_segment_annotation

            updated = update_segment_annotation(
                self._dataset_path,
                seg["segment_id"],
                transcript_display=self.txt_display.toPlainText().strip(),
                transcript_spoken=self.txt_spoken.toPlainText().strip(),
                speaker_id=self.ed_speaker.text().strip(),
                emotion=str(self.emotion_combo.currentData() or self.emotion_combo.currentText()),
                speaking_style=self._selected_style(),
                slang_level=self.slider_slang.value() / 100.0,
                rudeness_level=self.slider_rude.value() / 100.0,
                verified_by="studio_ui",
            )
            self._segments[self._current_row] = updated
            self._reload_dataset()
            self.table.selectRow(self._current_row)
            self.lbl_status.setText("Annotation saved")
        except Exception as exc:
            QMessageBox.warning(self, "Voice Training", str(exc))

    def _run_train(self) -> None:
        if not self._dataset_path.is_file():
            QMessageBox.information(self, "Voice Training", "Load or import a dataset first.")
            return
        path = self._dataset_path
        dry = self.chk_dry.isChecked()
        model = str(self.model_combo.currentData() or "khmer-tts-baseline")

        def job(progress_callback=None):
            from claynext.voice_training.training.tts_trainer import run_finetune

            return run_finetune(
                path,
                model_name=model,
                dry_run=dry,
                progress_callback=progress_callback,
            )

        self._start_worker(job, on_result=self._on_train_done, on_error=self._on_train_error)

    def _on_train_done(self, result: object) -> None:
        data = result if isinstance(result, dict) else {}
        msg = (
            f"Experiment {data.get('experiment_id')} · "
            f"{'dry-run' if data.get('dry_run') else 'train'} · "
            f"{data.get('manifest_path', '')}"
        )
        self.lbl_train_result.setText(msg)
        self.lbl_status.setText("Training step finished")

    def _on_train_error(self, err: str, _tb: str) -> None:
        self.lbl_train_result.setText("")
        QMessageBox.warning(
            self,
            "Training blocked",
            f"{err}\n\nAdd valid performer consent with voice_model_training "
            "and/or tts_synthesis before training.",
        )

    def _run_eval(self) -> None:
        if not self._dataset_path.is_file():
            QMessageBox.information(self, "Voice Training", "Load or import a dataset first.")
            return
        path = self._dataset_path

        def job(progress_callback=None):
            from claynext.voice_training.evaluation.harness import run_evaluation, write_evaluation_report
            from claynext.voice_training.paths import VOICE_CACHE_DIR

            if progress_callback:
                progress_callback(20, "Running evaluation…")
            summary = run_evaluation(path)
            out = VOICE_CACHE_DIR / "last_eval.json"
            write_evaluation_report(summary, out)
            if progress_callback:
                progress_callback(100, "Evaluation done")
            return {"summary": summary, "path": str(out)}

        self._start_worker(job, on_result=self._on_eval_done)

    def _on_eval_done(self, result: object) -> None:
        data = result if isinstance(result, dict) else {}
        summary = data.get("summary") or {}
        self.lbl_train_result.setText(
            f"Eval · intelligibility={summary.get('intelligibility_mean')} · "
            f"naturalness={summary.get('naturalness_mean')} · "
            f"report={data.get('path')}"
        )

    def _start_worker(self, fn, *, on_result=None, on_error=None) -> None:
        if self._worker is not None:
            QMessageBox.information(self, "Voice Training", "A job is already running.")
            return
        self._set_busy(True, "Starting…")
        worker = Worker(fn)
        self._worker = worker
        worker.signals.progress.connect(self._on_progress)
        if on_result:
            worker.signals.result.connect(on_result)

        def _finished():
            self._worker = None
            self._set_busy(False, "Ready")

        def _error(err: str, tb: str):
            self._worker = None
            self._set_busy(False, "Error")
            if on_error:
                on_error(err, tb)
            else:
                QMessageBox.warning(self, "Voice Training", err)

        worker.signals.finished.connect(_finished)
        worker.signals.error.connect(_error)
        self.thread_pool.start(worker)
