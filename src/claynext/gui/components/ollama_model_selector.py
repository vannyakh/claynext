"""
Ollama Model Selector Widget.
Provides an editable dropdown populated with installed Ollama models,
live server availability check, and recommended translation models.
"""
from __future__ import annotations

import re
import threading
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QToolButton,
    QLabel,
    QSizePolicy,
)

from claynext.constants.theme_constants import (
    COLOR_BG_DARK,
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_ACCENT_EMERALD,
    COLOR_ACCENT_CYAN,
)
from claynext.models.translate_service import TranslateEngine


RECOMMENDED_MODELS = [
    ("qwen3:8b", "qwen3:8b · Best local rewrite (Apple Silicon)"),
    ("aya-expanse:8b", "aya-expanse:8b · Best multilingual / Khmer"),
    ("qwen2.5:7b", "qwen2.5:7b · Solid default dub rewrite"),
    ("qwen2.5:14b", "qwen2.5:14b · Higher quality (needs ≥24 GB RAM)"),
    ("llama3.2:3b", "llama3.2:3b · Fast & lightweight"),
    ("mistral:7b", "mistral:7b · Balanced multilingual"),
]


class OllamaModelSelector(QWidget):
    """
    Drop-in replacement for QLineEdit for selecting or typing an Ollama model tag.
    Automatically checks if the Ollama daemon is reachable on http://127.0.0.1:11434
    and populates downloaded models.
    """

    modelChanged = Signal(str)
    editingFinished = Signal()

    def __init__(self, parent: QWidget | None = None, default_model: str = "qwen3:8b"):
        super().__init__(parent)
        self._current_model = default_model or "qwen3:8b"
        self._is_checking = False
        self._available = False
        self._installed_models: list[str] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Top row: ComboBox + Refresh Button
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.combo = QComboBox(self)
        self.combo.setObjectName("start_localize_combo")
        self.combo.setEditable(True)
        self.combo.setFixedHeight(28)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if self.combo.lineEdit():
            self.combo.lineEdit().setPlaceholderText("qwen3:8b")
            self.combo.lineEdit().editingFinished.connect(self._on_text_edited)
        self.combo.currentIndexChanged.connect(self._on_combo_index_changed)

        self.btn_refresh = QToolButton(self)
        self.btn_refresh.setText("⟳")
        self.btn_refresh.setToolTip("Check Ollama status and refresh downloaded models")
        self.btn_refresh.setFixedSize(28, 28)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet(f"""
            QToolButton {{
                background-color: {COLOR_BG_DARK};
                color: {COLOR_TEXT_MAIN};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                border-color: {COLOR_PRIMARY};
                color: #ffffff;
            }}
            QToolButton:disabled {{
                color: {COLOR_TEXT_MUTED};
                border-color: {COLOR_BORDER};
            }}
        """)
        self.btn_refresh.clicked.connect(lambda: self.check_and_refresh(force=True))

        row.addWidget(self.combo, 1)
        row.addWidget(self.btn_refresh, 0)
        lay.addLayout(row)

        # Bottom row: Connection & installed count status
        self.lbl_status = QLabel(self)
        self.lbl_status.setFixedHeight(14)
        self.lbl_status.setStyleSheet("font-size: 10px; margin: 0; padding: 0;")
        lay.addWidget(self.lbl_status)

        self._populate_fallback()
        self.setText(self._current_model)

        # Trigger initial check in background
        self.check_and_refresh()

    def _clean_model_tag(self, text: str) -> str:
        """Strip formatting, suffixes like (installed), (recommended), etc."""
        raw = text.strip()
        if not raw:
            return ""
        # Remove prefix symbols like ✓ or ⬇
        raw = re.sub(r"^[✓⬇●○\s]+", "", raw).strip()
        # Take the first token before whitespace or parenthesis
        parts = raw.split(" ")
        tag = parts[0].strip() if parts else raw
        return tag or raw

    def text(self) -> str:
        """Returns the clean model identifier (compatible with QLineEdit.text())."""
        data = self.combo.currentData()
        if data and isinstance(data, str) and data.strip():
            return data.strip()
        txt = self.combo.currentText().strip()
        return self._clean_model_tag(txt) or self._current_model

    def currentText(self) -> str:
        return self.text()

    def setText(self, model: str) -> None:
        """Sets the active model tag (compatible with QLineEdit.setText())."""
        clean = self._clean_model_tag(str(model or "")).strip() or "qwen3:8b"
        self._current_model = clean

        # Look for matching item by data or text
        found_idx = -1
        for i in range(self.combo.count()):
            d = str(self.combo.itemData(i) or "")
            t = self._clean_model_tag(self.combo.itemText(i))
            if d == clean or t == clean:
                found_idx = i
                break

        if found_idx >= 0:
            self.combo.setCurrentIndex(found_idx)
        else:
            self.combo.setEditText(clean)

    def setPlaceholderText(self, text: str) -> None:
        if self.combo.lineEdit():
            self.combo.lineEdit().setPlaceholderText(text)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.combo.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)
        self.lbl_status.setEnabled(enabled)

    def _on_combo_index_changed(self, idx: int) -> None:
        if idx < 0:
            return
        tag = self.text()
        if tag:
            self._current_model = tag
            self.modelChanged.emit(tag)
            self.editingFinished.emit()

    def _on_text_edited(self) -> None:
        tag = self.text()
        if tag:
            self._current_model = tag
            self.modelChanged.emit(tag)
            self.editingFinished.emit()

    def _populate_fallback(self) -> None:
        """Populate initial recommended models."""
        self.combo.blockSignals(True)
        self.combo.clear()
        for tag, label in RECOMMENDED_MODELS:
            self.combo.addItem(f"{tag}  ·  Recommended", tag)
        self.combo.blockSignals(False)
        self._update_status_ui(False, [])

    def check_and_refresh(self, force: bool = False) -> None:
        """Query Ollama daemon in background thread."""
        if self._is_checking:
            return
        self._is_checking = True
        self.lbl_status.setText(f'<span style="color:{COLOR_TEXT_MUTED}">Checking Ollama (port 11434)…</span>')

        def _bg_check():
            try:
                avail, models = TranslateEngine.list_ollama_models()
                # Run UI update on main thread
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._apply_results(avail, models))
            except Exception:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._apply_results(False, []))

        threading.Thread(target=_bg_check, daemon=True).start()

    def _apply_results(self, available: bool, models: list[dict[str, Any]]) -> None:
        self._is_checking = False
        self._available = available

        installed_tags = []
        for m in models:
            if isinstance(m, dict):
                n = str(m.get("name") or m.get("model") or "").strip()
                if n and n not in installed_tags:
                    installed_tags.append(n)

        self._installed_models = installed_tags
        current = self.text() or self._current_model

        self.combo.blockSignals(True)
        self.combo.clear()

        # 1. Add downloaded models first
        if installed_tags:
            for tag in installed_tags:
                self.combo.addItem(f"✓ {tag}  (installed)", tag)

        # 2. Add recommended models not already in downloaded list
        for tag, desc in RECOMMENDED_MODELS:
            if tag not in installed_tags:
                self.combo.addItem(f"{tag}  (available to pull)", tag)

        self.combo.blockSignals(False)
        self.setText(current)
        self._update_status_ui(available, installed_tags)

    def _update_status_ui(self, available: bool, installed_tags: list[str]) -> None:
        if available:
            count = len(installed_tags)
            if count > 0:
                self.lbl_status.setText(
                    f'<span style="color:{COLOR_ACCENT_EMERALD}; font-weight:bold;">● Ollama online</span> '
                    f'<span style="color:{COLOR_TEXT_MUTED}">· {count} model(s) downloaded</span>'
                )
            else:
                self.lbl_status.setText(
                    f'<span style="color:{COLOR_ACCENT_CYAN}; font-weight:bold;">● Ollama online</span> '
                    f'<span style="color:{COLOR_TEXT_MUTED}">· ready (0 downloaded models)</span>'
                )
        else:
            self.lbl_status.setText(
                f'<span style="color:{COLOR_TEXT_MUTED};">○ Ollama offline</span> '
                f'<span style="color:#f59e0b">(Start Ollama daemon to use local LLM)</span>'
            )
