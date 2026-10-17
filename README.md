# Claynext Studio

Desktop AI movie dubbing & timeline editor (Python 3.12+, PySide6, `uv`).

## Quick Start

```bash
uv sync
uv run main.py                              # loader → Studio
uv run main.py --project file.claynext.json
uv run claynext --help                      # headless tools + gui
```

## Layout

```
Claynext/
├── main.py
├── pyproject.toml
├── assets/
├── data/                 # models, cache, outputs, projects
└── src/claynext/
    ├── app.py
    ├── constants/
    ├── core/             # engines (ASR/TTS/ffmpeg/dubbing pipeline)
    ├── gui/
    │   ├── components/   # timeline, preview, shelves…
    │   └── views/studio/ # editor workspace (was dubbing)
    ├── tools/
    └── utils/
```

## Notes

- Package import root is `claynext`.
- Tool id is `studio` (legacy `--tool dubbing` still accepted).
- Core pipeline modules may still use `dubbing_*` names internally.

## Data layout

```
data/
├── cache/studio/     # pipeline job cache
├── cache/playback/   # playback-safe media
├── models/           # HF / TTS model weights (kept across cleans)
├── outputs/          # exports
├── presets/studio/   # overlay presets
└── projects/         # saved projects + voiceover takes
```
