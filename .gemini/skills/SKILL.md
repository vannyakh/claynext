---
name: claynext-studio
description: Comprehensive workspace skill for Claynext Studio. Use to launch, debug, and develop ASR transcription, TTS synthesis, subtitle translation, OCR, video tools, and AI dubbing pipelines.
---

# Claynext Studio — Agent Workspace Skill & Guide

Welcome to the **Claynext Studio** agent guide. This file equips AI agents and developers with the workflows, commands, and architectural patterns needed to work productively on claynext.

---

## 🚀 Fast Launch Commands

Run any view directly using `uv` (bypassing the splash screen):

```bash
# Launch directly to a specific tool view:
uv run main.py --tool asr --no-splash        # 0: Whisper ASR & Subtitle Editor
uv run main.py --tool dubbing --no-splash    # 1: AI Movie Dubbing Pipeline
uv run main.py --tool tts --no-splash        # 2: Edge-TTS Studio
uv run main.py --tool translate --no-splash  # 3: Caption Translator
uv run main.py --tool ocr --no-splash        # 4: Video Frame OCR
uv run main.py --tool video --no-splash      # 5: FFmpeg Video Tools

# Full standard launch:
uv run main.py
```

---

## 🛠️ Specialized Project Skills

This workspace provides dedicated skills tailored for Claynext:

Skill | Location | Purpose
:--- | :--- | :---
`claynext-studio` | [.agents/skills/claynext-studio/SKILL.md](file:///H:/Claynext/.agents/skills/claynext-studio/SKILL.md) | Workspace overview, launch flags, and architecture
`claynext-dev-workflow` | [.agents/skills/claynext-dev-workflow/SKILL.md](file:///H:/Claynext/.agents/skills/claynext-dev-workflow/SKILL.md) | Smoke testing, headless Qt diagnostics, and dependency management
`claynext-media-pipeline` | [.agents/skills/claynext-media-pipeline/SKILL.md](file:///H:/Claynext/.agents/skills/claynext-media-pipeline/SKILL.md) | FFmpeg, Faster-Whisper, Edge-TTS, and dubbing sync workflows
`claynext-ui-component` | [.agents/skills/claynext-ui-component/SKILL.md](file:///H:/Claynext/.agents/skills/claynext-ui-component/SKILL.md) | PySide6 custom widgets, timeline tracks, and Cyber Dark design system

---

## 📋 Core Architectural Rules

1. **Non-Blocking GUI**: Heavy tasks must execute on `Worker` ([worker.py](file:///H:/Claynext/src/claynext/core/worker.py)) via `QThreadPool.globalInstance().start(worker)`. Never freeze the UI.
2. **Design System**: Use tokens from [theme_constants.py](file:///H:/Claynext/src/claynext/constants/theme_constants.py) (`COLOR_BG_DARK`, `COLOR_BG_CARD`, `COLOR_PRIMARY`, etc.) and `build_stylesheet()` in [styles.py](file:///H:/Claynext/src/claynext/gui/styles.py).
3. **FFmpeg Resolution**: Resolve FFmpeg via `imageio_ffmpeg.get_ffmpeg_exe()`. Never assume a bare `ffmpeg` on PATH.
4. **Media Compatibility**: Use [media_compat.py](file:///H:/Claynext/src/claynext/core/media_compat.py) for Qt-safe audio (AAC-LC 44.1kHz) and 720p H.264 proxy rendering.
5. **Headless Verification**: Test UI code with `QT_QPA_PLATFORM=offscreen uv run python ...`.

---

## 📁 Key Directories

- `src/claynext/core/`: Headless engine logic (ASR, Dubbing, TTS, OCR, FFmpeg).
- `src/claynext/gui/`: PySide6 views, components (timeline, media preview, drop zone), and launcher.
- `src/claynext/constants/`: Layout dimensions, navigation items, and Cyber Dark theme tokens.
- `data/models/`: Cached AI weights.
- `data/outputs/`: Rendered and exported media files.
- `data/cache/`: Playback proxies and temporary audio chunks.
