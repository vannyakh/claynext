---
name: claynext-ui-component
description: Guide for creating, styling, and refactoring PySide6 widgets, views, and custom panels (timeline, wave visualizer, drop zone, media preview) using Claynext's Cyber Dark design system.
---

# Claynext PySide6 UI Component & View Guide

This skill provides step-by-step instructions for creating, extending, and styling PySide6 UI components in Claynext Studio.

---

## 1. Creating a Standard Claynext Tool View

All main tool views reside in `src/claynext/gui/views/` (e.g. `asr_view.py`, `dubbing_view.py`).

### Standard View Template:
```python
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt, QThreadPool
from claynext.constants.theme_constants import (
    COLOR_BG_CARD, COLOR_BORDER, COLOR_PRIMARY, COLOR_TEXT_MAIN, COLOR_TEXT_MUTED
)
from claynext.gui.components.drop_zone import DropZone
from claynext.core.worker import Worker


class CustomToolView(QWidget):
    """Claynext Tool View implementing Cyber Dark styling and async worker execution."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header card
        header = QLabel("Tool Title")
        header.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLOR_TEXT_MAIN};")
        layout.addWidget(header)

        # Drag and Drop Media Area
        self.drop_zone = DropZone(
            title="Drop video or audio file here",
            subtitle="Supports MP4, MKV, WAV, MP3, FLAC",
            file_types=[".mp4", ".mkv", ".wav", ".mp3", ".flac"],
        )
        self.drop_zone.file_selected.connect(self._on_file_selected)
        layout.addWidget(self.drop_zone)

        layout.addStretch()

    def _on_file_selected(self, file_path: str):
        # Start heavy processing asynchronously
        worker = Worker(self._process_heavy_task, file_path)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _process_heavy_task(self, path: str, progress_callback=None):
        # Core computation runs off-thread
        return {"output": "success"}

    def _on_progress(self, percent: int, msg: str):
        pass

    def _on_result(self, result: dict):
        pass

    def _on_error(self, err_msg: str, tb: str):
        pass

    def stop_playback(self):
        """Called automatically when window closes or user navigates back to launcher."""
        pass
```

---

## 2. Using Built-In Reusable Components

### DropZone ([drop_zone.py](file:///H:/Claynext/src/claynext/gui/components/drop_zone.py))
- Interactive drag-and-drop zone with animated hover border, file browser dialog, and icon preview.
- Emits `file_selected(str)` signal when a file is accepted.

### MediaPreviewWidget ([media_preview.py](file:///H:/Claynext/src/claynext/gui/components/media_preview.py))
- Combines `QMediaPlayer`, `QVideoWidget` / `QAudioOutput`, transport bar (Play, Pause, Scrub, Volume, Timecode), and resolution tags.
- Load media with `widget.load_media(media_path)`.

### TimelinePanel ([timeline_panel.py](file:///H:/Claynext/src/claynext/gui/components/timeline_panel.py))
- Multi-track timeline (Video, Dialogue, Music, Sound Effects).
- Supports draggable clip blocks, playhead scrub, snapping, and zoom.

### WaveVisualizer ([wave_visualizer.py](file:///H:/Claynext/src/claynext/gui/components/wave_visualizer.py))
- Renders audio waveform amplitudes using `QPainter` with gradient fills matching tool accent colors.

---

## 3. Styling Guidelines

1. **Avoid Hardcoded QSS Stylesheets**: Always build dynamic stylesheets using tokens from `theme_constants.py` or extend `src/claynext/gui/styles.py` (`build_stylesheet()`).
2. **Interactive States**: Always include `:hover`, `:pressed`, and `:disabled` pseudo-states for interactive controls.
3. **Margins & Spacing**: Use standard multiples of 4 or 8 (`4px`, `8px`, `12px`, `16px`, `24px`) for visual harmony.
