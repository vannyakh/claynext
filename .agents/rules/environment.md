# Rule: Environment, Dependency & Execution Standards

## 1. UV Package Management
This project exclusively uses `uv` for virtual environments, package management, and script execution.

- Always run scripts using `uv run`:
  ```bash
  uv run main.py
  uv run python <script.py>
  ```
- To update or add dependencies, modify `pyproject.toml` and run:
  ```bash
  uv sync
  ```
- Do not use raw `pip install` or create ad-hoc virtual environments.

## 2. Fast Development Launch Flags
When testing UI changes or debugging a specific feature, avoid launching the splash screen and clicking through the launcher menu:

```bash
# Direct launch into a specific tool view:
uv run main.py --tool asr --no-splash
uv run main.py --tool dubbing --no-splash
uv run main.py --tool tts --no-splash
uv run main.py --tool translate --no-splash
uv run main.py --tool ocr --no-splash
uv run main.py --tool video --no-splash
```

## 3. Headless Verification Protocol
Before finalizing any GUI code change, verify that Qt and modules initialize without errors headlessly:

```bash
QT_QPA_PLATFORM=offscreen uv run python -c "
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from jela.app import main
print('Imports and GUI init verified headlessly!')
"
```

## 4. Directory Layout Standards
- `assets/`: Static SVGs, PNG banners, and tool logos.
- `data/models/`: Local cache of downloaded AI model weights.
- `data/outputs/`: Default destination for user-exported media, subtitles, and audio.
- `data/cache/`: Transcoded proxies, waveforms, and temporary audio files.
- `src/jela/`: All application source code.
