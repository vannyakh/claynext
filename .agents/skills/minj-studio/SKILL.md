---
name: minj-studio
description: Comprehensive workspace skill for MinJ AI Media Studio. Use to launch, debug, and develop ASR transcription, TTS synthesis, subtitle translation, OCR, video tools, and AI dubbing pipelines.
---

# MinJ AI Media Studio Master Skill

This skill guides you through developing, testing, and debugging the **MinJ AI Media Studio** desktop application.

---

## 1. Quick Navigation & Dev Commands

MinJ provides command-line flags to bypass the splash screen and launch directly into specific tool views:

Command | Purpose | View Loaded
:--- | :--- | :---
`uv run main.py` | Full flow: Splash Screen → Launcher Hub | Launcher Window
`uv run main.py --no-splash` | Skip splash, open launcher directly | Launcher Window
`uv run main.py --tool asr --no-splash` | Launch Transcript & ASR Studio | [asr_view.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/views/asr_view.py)
`uv run main.py --tool dubbing --no-splash` | Launch AI Movie Dubbing Studio | [dubbing_view.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/views/dubbing_view.py)
`uv run main.py --tool tts --no-splash` | Launch Neural TTS Studio | [tts_view.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/views/tts_view.py)
`uv run main.py --tool translate --no-splash` | Launch Caption Translator | [translate_view.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/views/translate_view.py)
`uv run main.py --tool ocr --no-splash` | Launch Video/Image Text OCR | [ocr_view.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/views/ocr_view.py)
`uv run main.py --tool video --no-splash` | Launch FFmpeg Video Tools | [video_view.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/views/video_view.py)

---

## 2. Core Architecture Reference

```text
MinJ/
├── main.py                     # Entrypoint (CLI flags: --tool, --no-splash)
├── pyproject.toml              # UV / Hatchling packaging config
├── assets/                     # Icons (aspect.svg, tools) & banners
├── data/
│   ├── cache/                  # Playback audio & 720p H.264 proxy renders
│   ├── models/                 # Cached AI models (Whisper, EasyOCR)
│   └── outputs/                # User exports (.srt, .vtt, .wav, .mp4)
└── src/jela/
    ├── app.py                  # High-DPI setup, splash screen orchestration
    ├── constants/              # UI layout constants & Cyber Dark theme tokens
    ├── core/                   # Headless engines & background workers
    │   ├── asr_engine.py       # Faster-Whisper transcription
    │   ├── dubbing_engine.py   # Full dubbing pipeline orchestrator
    │   ├── ffmpeg_tools.py     # Demux, probe, stretch, timeline mix
    │   ├── media_compat.py     # AAC-LC conversion & proxy rendering
    │   ├── ocr_engine.py       # OCR recognition
    │   ├── tts_engine.py       # Edge-TTS neural speech synthesis
    │   └── worker.py           # QRunnable / QThreadPool async worker
    └── gui/                    # PySide6 User Interface
        ├── launcher_window.py  # Primary launcher & tool cards
        ├── main_window.py      # Dedicated tool window with custom chrome
        ├── styles.py           # Cyber Dark QSS compilation
        ├── components/         # Timeline, media preview, drop zone, etc.
        └── views/              # View implementations for each tool
```

---

## 3. Essential Development Workflows

### A. Testing Headlessly
Always test modules and GUI imports headlessly before reporting completion:
```bash
QT_QPA_PLATFORM=offscreen uv run python -c "
from jela.gui.styles import build_stylesheet
from jela.constants import NAV_ITEMS
print(f'Styles loaded ({len(build_stylesheet())} bytes), {len(NAV_ITEMS)} tools ready.')
"
```

### B. Executing Async Tasks with `Worker`
Never execute long operations synchronously on the UI thread:
```python
from PySide6.QtCore import QThreadPool
from jela.core.worker import Worker

worker = Worker(self.engine.process_media, media_path)
worker.signals.progress.connect(self._update_progress)
worker.signals.result.connect(self._handle_result)
worker.signals.error.connect(self._handle_error)
QThreadPool.globalInstance().start(worker)
```

### C. Color Token Rule
Always use `src/jela/constants/theme_constants.py`:
- `COLOR_BG_DARK`: `#080c12`
- `COLOR_BG_CARD`: `#121a26`
- `COLOR_PRIMARY`: `#6366f1`
- `COLOR_BORDER`: `#233348`
- `COLOR_TEXT_MAIN`: `#e7ecf3`
