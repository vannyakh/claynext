---
name: claynext-studio
description: Comprehensive workspace skill for Claynext Studio. Use to launch, debug, and develop ASR transcription, TTS synthesis, subtitle translation, OCR, video tools, and AI dubbing pipelines.
---

# Claynext Studio Master Skill

This skill guides you through developing, testing, and debugging the **Claynext Studio** desktop application.

---

## 1. Quick Navigation & Dev Commands

Claynext provides command-line flags to bypass the splash screen and launch directly into specific tool views:

Command | Purpose | View Loaded
:--- | :--- | :---
`uv run main.py` | Full flow: Splash Screen → Launcher Hub | Launcher Window
`uv run main.py --no-splash` | Skip splash, open launcher directly | Launcher Window
`uv run main.py --tool asr --no-splash` | Launch Transcript & ASR Studio | [asr_view.py](file:///H:/Claynext/src/claynext/gui/views/asr_view.py)
`uv run main.py --tool dubbing --no-splash` | Launch AI Movie Dubbing Studio | [dubbing_view.py](file:///H:/Claynext/src/claynext/gui/views/dubbing_view.py)
`uv run main.py --tool tts --no-splash` | Launch Neural TTS Studio | [tts_view.py](file:///H:/Claynext/src/claynext/gui/views/tts_view.py)
`uv run main.py --tool translate --no-splash` | Launch Caption Translator | [translate_view.py](file:///H:/Claynext/src/claynext/gui/views/translate_view.py)
`uv run main.py --tool ocr --no-splash` | Launch Video/Image Text OCR | [ocr_view.py](file:///H:/Claynext/src/claynext/gui/views/ocr_view.py)
`uv run main.py --tool video --no-splash` | Launch FFmpeg Video Tools | [video_view.py](file:///H:/Claynext/src/claynext/gui/views/video_view.py)

---

## 2. Core Architecture Reference

**Hybrid stack:** Python GUI/models + Rust core tools via Adapters.  
See skill **`claynext-rust-core`** and `AGENTS.md` §1 for the full migration rules.

```text
Claynext/
├── main.py / pyproject.toml
├── backends/                   # Rust CLI tools (performance core)
│   ├── ai-runtime/             # claynext-ai
│   ├── ffmpeg/                 # claynext-ffmpeg
│   ├── cpu/ · hardware-codecs/ · wgpu/
├── crates/editor-*/            # Shared Rust domain (dubbing, speech, types…)
├── data/                       # cache, models, outputs
└── src/claynext/
    ├── gui/                    # PySide6 Studio (Cyber Dark)
    ├── models/                 # Orchestration + ML SDKs (call adapters)
    ├── adapters/               # Domain facades → Rust
    │   ├── ai.py · dubbing.py · ffmpeg_adapter.py · media.py …
    │   └── rust_bridge/        # Binary IPC (adapters only)
    ├── cli/                    # claynext CLI
    └── core/worker.py          # QThreadPool workers (never block UI)
```

**Call path:** `GUI → models → adapters → rust_bridge → backends/crates`  
Do **not** import `rust_bridge` from `gui/` or `models/`.

---

## 3. Essential Development Workflows

### A. Testing Headlessly
Always test modules and GUI imports headlessly before reporting completion:
```bash
QT_QPA_PLATFORM=offscreen uv run python -c "
from claynext.gui.styles import build_stylesheet
from claynext.constants import NAV_ITEMS
print(f'Styles loaded ({len(build_stylesheet())} bytes), {len(NAV_ITEMS)} tools ready.')
"
```

### B. Executing Async Tasks with `Worker`
Never execute long operations synchronously on the UI thread:
```python
from PySide6.QtCore import QThreadPool
from claynext.core.worker import Worker

worker = Worker(self.engine.process_media, media_path)
worker.signals.progress.connect(self._update_progress)
worker.signals.result.connect(self._handle_result)
worker.signals.error.connect(self._handle_error)
QThreadPool.globalInstance().start(worker)
```

### C. Color Token Rule
Always use `src/claynext/constants/theme_constants.py`:
- `COLOR_BG_DARK`: `#080c12`
- `COLOR_BG_CARD`: `#121a26`
- `COLOR_PRIMARY`: `#6366f1`
- `COLOR_BORDER`: `#233348`
- `COLOR_TEXT_MAIN`: `#e7ecf3`
