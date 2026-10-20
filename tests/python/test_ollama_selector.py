from __future__ import annotations

import os
from claynext.models.translate_service import TranslateEngine
from claynext.gui.components.ollama_model_selector import OllamaModelSelector


def test_ollama_api_helpers():
    avail, models = TranslateEngine.list_ollama_models()
    assert isinstance(avail, bool)
    assert isinstance(models, list)

    avail_n, names = TranslateEngine.get_ollama_model_names()
    assert isinstance(avail_n, bool)
    assert isinstance(names, list)


def test_ollama_model_selector_widget(qtbot=None):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    selector = OllamaModelSelector(default_model="qwen2.5:7b")

    # Compatibility methods
    assert selector.text() == "qwen2.5:7b"
    selector.setText("llama3.2:3b")
    assert selector.text() == "llama3.2:3b"

    # Strips tags
    selector.setText("✓ mistral:7b (installed)")
    assert selector.text() == "mistral:7b"

    # Enables / disables
    selector.setEnabled(False)
    assert not selector.combo.isEnabled()
    assert not selector.btn_refresh.isEnabled()

    selector.setEnabled(True)
    assert selector.combo.isEnabled()
    assert selector.btn_refresh.isEnabled()
