# Claynext Studio — Workspace Rules

Architecture, design standards, and operational guidelines for AI agents working in the **Claynext Studio** repository (studio/dubbing editor).

---

## 1. Project Overview & Tech Stack

Claynext is a high-performance desktop AI media application built with:
- **Language**: Python 3.12+ (strictly with modern typing annotations: `from __future__ import annotations`, `X | None`, `Path`)
- **GUI Framework**: `PySide6` (Qt 6.11+) with custom Cyber Dark QSS styling
- **Environment & Dependency Manager**: `uv` (Hatchling build backend in `pyproject.toml`)
- **Audio & Video Engine**: `ffmpeg-python`, `imageio-ffmpeg` (bundled binaries), `moviepy`
- **AI Processing Engines**:
  - `faster-whisper` (ASR used inside studio pipeline)
  - `edge-tts` (Neural multi-voice speech synthesis)
  - `deep-translator` (NMT caption translation)

---

## 2. Non-Negotiable Core Principles

### Rule 1: Non-Blocking GUI & Thread Safety
> **CRITICAL**: Heavy computation, AI model inference, network requests, and media transcoding MUST NEVER run on Qt's main GUI thread.

- **Background Worker**: Always use `Worker` from `src/claynext/core/worker.py`:
  ```python
  from PySide6.QtCore import QThreadPool
  from claynext.core.worker import Worker

  worker = Worker(my_heavy_function, arg1, kwarg2=val)
  worker.signals.progress.connect(self._on_progress)
  worker.signals.result.connect(self._on_result)
  worker.signals.error.connect(self._on_error)
  worker.signals.finished.connect(self._on_finished)
  QThreadPool.globalInstance().start(worker)
  ```
- **Thread Safety**: Never mutate Qt widgets directly inside the worker target function. All communication from workers to the UI must happen exclusively via Qt Signals.
- **Process Cancellation & Cleanup**: When closing windows or navigating away, always ensure ongoing media players or background workers are stopped cleanly (`_stop_tool_media()`, `closeEvent`).

### Rule 2: Cyber Dark Design System Adherence
> **Do not use hardcoded random colors or ad-hoc QSS stylesheets.**

- Always use tokens from `src/claynext/constants/theme_constants.py`
- High-DPI Scaling is enabled by default in `src/claynext/app.py`. Ensure layouts use scalable layouts (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`) with proper margins and spacing instead of fixed pixel geometries.

### Rule 3: Cross-Platform Window Chrome Conventions
- Windows uses custom frameless chrome (`Qt.FramelessWindowHint` with `src/claynext/gui/components/title_bar.py`).
- macOS / Linux keep native window chrome and system menu bars unless explicitly forced with `CLAYNEXT_CUSTOM_CHROME=1`.
- Always respect `CUSTOM_WINDOW_CHROME` from `src/claynext/constants/ui_constants.py`.

### Rule 4: FFmpeg and Media Compatibility
- Never assume a bare `ffmpeg` is available on the system PATH. Always resolve FFmpeg using `imageio_ffmpeg.get_ffmpeg_exe()` as implemented in `src/claynext/core/ffmpeg_tools.py` and `src/claynext/core/media_compat.py`.
- For media playback in Qt, verify and convert files to safe AAC-LC 44.1kHz stereo or generate 720p lightweight H.264 proxies using `src/claynext/core/media_compat.py`.

### Rule 5: Filesystem & Cache Standards
- Never output temporary or generated files into the project root directory.
- Model weights: `data/models/`
- User exports: `data/outputs/`
- Transcoding / Proxies / Cache: Use `CACHE_DIR` / `PLAYBACK_DIR` from `src/claynext/utils/paths.py` and `src/claynext/core/media_compat.py`.

---

## 3. Development Workflow & Commands

All commands MUST be run with `uv`:

```bash
# Sync dependencies
uv sync

# Launch (loader → Project Home → Studio)
uv run main.py

# Skip loader splash (Fast Dev Mode)
uv run main.py --no-splash

# Open studio editor directly (skip project home)
uv run main.py --studio --no-splash

# Run headless smoke test (Qt offscreen)
QT_QPA_PLATFORM=offscreen uv run python -c "from claynext.app import main; print('Ready')"
```

---

## 4. Key Navigation Items

Index | ID | Label | Accent Color | Description
:--- | :--- | :--- | :--- | :---
0 | `studio` | Claynext Studio | `#a855f7` | AI Movie Dubbing & Timeline Editor
