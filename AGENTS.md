# Claynext Studio — Workspace Rules

Architecture, design standards, and operational guidelines for AI agents working in the **Claynext Studio** repository (studio/dubbing editor).

---

## 1. Project Overview & Tech Stack

Claynext is a high-performance desktop AI media application. The project is **migrating from all-Python core logic to a hybrid stack**:

| Layer | Location | Responsibility |
|:---|:---|:---|
| GUI + CLI | `src/claynext/gui`, `cli` | PySide6 Studio, Cyber Dark UI, CLI entrypoints |
| Models / orchestration | `src/claynext/models` | Pipelines, ML SDKs, JobControl |
| Domain Adapters | `src/claynext/adapters` | Tool APIs → Rust; Python fallbacks |
| Rust bridge | `src/claynext/adapters/rust_bridge` | Binary discovery + UTF-8 IPC |
| Rust backends | `backends/*` | Fast CLI tools (`claynext-ai`, `claynext-ffmpeg`, …) |
| Editor crates | `crates/editor-*` | Shared domain (dubbing plan, alignment, types) |

- **Language (app shell)**: Python 3.12+ (`from __future__ import annotations`, `X | None`, `Path`)
- **Language (core tools)**: Rust (Cargo workspace)
- **GUI Framework**: `PySide6` (Qt 6.11+) with Cyber Dark QSS
- **Environment**: `uv` (Hatchling in `pyproject.toml`)
- **Media**: Rust `claynext-ffmpeg` preferred; `imageio-ffmpeg` fallback
- **AI SDKs (still Python)**: `faster-whisper`, `edge-tts`, Gemini/Ollama HTTP, optional Demucs/WhisperX

**Agent skill for this architecture:** `.agents/skills/claynext-rust-core/SKILL.md`  
**Cursor rules:** `.cursor/rules/rust-python-architecture.mdc` (+ backends / adapters rules)

### Canonical call path

```text
GUI/CLI → models → adapters (Ai / Dubbing / FFmpeg / …)
                 → rust_bridge → backends/* or crates/*
```

Models and GUI **must not** import `rust_bridge` directly. Put new core algorithms in Rust; expose via Adapter.

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
- Prefer `get_ffmpeg_adapter()` / Rust `claynext-ffmpeg` for probe, stills, and PCM decode.
- Never assume a bare `ffmpeg` is on PATH. Fall back to `imageio_ffmpeg.get_ffmpeg_exe()` via adapters / `ffmpeg_service`.
- For Qt playback, use safe AAC-LC / H.264 proxies through media adapters (`ensure_playback_file`, `ensure_proxy_render`).

### Rule 5: Rust Core Before Python Hot Paths
- Timing, speech quota, dub/translate prompts, VAD, OCR filter, burned-in caption scan (`scan-captions`, `extract-crop`), tempo align, ducking math, media probe/decode belong in **Rust** (`backends/` / `crates/`). The Zone Tracker inspector is GUI only.
- Wire tools through **domain Adapters** (`get_ai_adapter`, `get_dubbing_adapter`, `get_ffmpeg_adapter`, …).
- Keep Python fallbacks so Studio runs without built binaries; do not crash the GUI.

### Rule 6: Filesystem & Cache Standards
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

# Launch (loader → Studio)
uv run main.py

# Open a project file in Studio
uv run main.py --project path/to/file.claynext.json

# CLI tools
uv run claynext --help
uv run claynext gui --project path/to/file.claynext.json

# Run headless smoke test (Qt offscreen)
QT_QPA_PLATFORM=offscreen uv run python -c "from claynext.app import main; print('Ready')"
```

---

## 4. Key Navigation Items

Index | ID | Label | Accent Color | Description
:--- | :--- | :--- | :--- | :---
0 | `studio` | Claynext Studio | `#a855f7` | AI Movie Dubbing & Timeline Editor
