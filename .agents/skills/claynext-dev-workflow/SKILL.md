---
name: claynext-dev-workflow
description: Development, testing, and diagnostic workflows for claynext. Use when running smoke tests, verifying headless Qt environments, debugging imports, and testing PySide6 components.
---

# Claynext Development & Diagnostic Workflow

This skill provides step-by-step procedures for testing, diagnosing, and maintaining the **Claynext Studio** codebase.

---

## 1. Running the Automated Smoke Test

Claynext includes a dedicated headless smoke test script that verifies the Python version, FFmpeg binaries, all core AI engines, headless Qt initialization, and theme compilation.

To execute the smoke test:
```bash
uv run python .agents/skills/claynext-dev-workflow/scripts/smoke_test.py
```

### What It Verifies:
1. Python runtime is `>= 3.12`.
2. Bundled FFmpeg binary from `imageio_ffmpeg` is present and functional.
3. All core engine modules (`asr_engine`, `dubbing_engine`, `tts_engine`, `translate_engine`, `ocr_engine`, `media_compat`, `worker`) import cleanly.
4. Headless `PySide6` initialization (`QT_QPA_PLATFORM=offscreen`) succeeds.
5. QSS stylesheet compiles completely without syntax errors.
6. `LauncherWindow` can instantiate without exceptions.

---

## 2. Headless Component Testing Protocol

When developing or refactoring UI components or views, always verify that the widget can be instantiated headlessly without crash:

```bash
QT_QPA_PLATFORM=offscreen uv run python -c "
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from claynext.gui.views.asr_view import ASRView
app = QApplication.instance() or QApplication(['test', '-platform', 'offscreen'])
view = ASRView()
assert view is not None
print('ASRView instantiated successfully!')
"
```

Replace `ASRView` with the target view or widget:
- `StudioView` (`claynext.gui.views.studio_view`)
- `TTSView` (`claynext.gui.views.tts_view`)
- `TranslateView` (`claynext.gui.views.translate_view`)
- `OCRView` (`claynext.gui.views.ocr_view`)
- `VideoView` (`claynext.gui.views.video_view`)
- `TimelinePanel` (`claynext.gui.components.timeline_panel`)
- `MediaPreviewWidget` (`claynext.gui.components.media_preview`)

---

## 3. Dependency Management with `uv`

- **Adding a new dependency**:
  Edit `pyproject.toml` under `dependencies` and run:
  ```bash
  uv sync
  ```
- **Checking lockfile consistency**:
  ```bash
  uv lock --check
  ```
- **Activating environment or running interactive python**:
  ```bash
  uv run python
  ```

---

## 4. Common Diagnostic Checks

### Check CUDA / Hardware Device Acceleration
```bash
uv run python -c "
from claynext.core.sysinfo import get_system_info
info = get_system_info()
print('System Devices:', info)
"
```

### Verify Audio/Video FFmpeg Probing
```bash
uv run python -c "
from claynext.core.ffmpeg_tools import probe_duration, ffmpeg_exe
print('FFmpeg binary:', ffmpeg_exe())
"
```
