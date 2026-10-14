# Rule: GUI Styling & Component System

## 1. Cyber Dark Design System
MinJ uses a refined Cyber Dark aesthetic with custom QSS styling and glassmorphism elements.

### Color Tokens
Import tokens directly from [theme_constants.py](file:///Users/vannya/Desktop/MinJ/src/jela/constants/theme_constants.py):
- Backgrounds:
  - `COLOR_BG_DARK` (`#080c12`) - Main window canvas
  - `COLOR_BG_SIDEBAR` (`#0b1017`) - Nav shelf & sidebar
  - `COLOR_BG_CARD` (`#121a26`) - Card containers & panel bodies
  - `COLOR_BG_CARD_HOVER` (`#182333`) - Hover state for clickable cards
  - `COLOR_BG_INPUT` (`#0a0e16`) - Text fields, dropdowns, spinboxes
- Accents:
  - `COLOR_PRIMARY` (`#6366f1` Indigo) - Primary action accent
  - `COLOR_ACCENT_PURPLE` (`#8b5cf6`) - Dubbing accent
  - `COLOR_ACCENT_EMERALD` (`#10b981`) - Translation accent
  - `COLOR_ACCENT_CYAN` (`#06b6d4`) - Highlights & timeline playhead
- Borders:
  - `COLOR_BORDER` (`#233348`) - Default panel borders (1px solid)
  - `COLOR_BORDER_FOCUS` - Focused inputs & active selections
- Typography:
  - `COLOR_TEXT_MAIN` (`#e7ecf3`) - Primary titles and headings
  - `COLOR_TEXT_SUB` (`#9fb0c3`) - Secondary body text
  - `COLOR_TEXT_MUTED` (`#6b7785`) - Placeholders, disabled states, captions

## 2. Reusable Custom Components
When constructing or modifying UI views, reuse standard components from `src/jela/gui/components/`:
- **Drop Zone**: [drop_zone.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/components/drop_zone.py) for drag-and-drop file inputs with hover animations and file validation.
- **Media Preview**: [media_preview.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/components/media_preview.py) with `MediaPreviewWidget` (QMediaPlayer + video output) and `MediaPlaybackWidget` (transport controls, timecode display, scrubbing slider).
- **Wave Visualizer**: [wave_visualizer.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/components/wave_visualizer.py) for rendering real-time waveform bars via `QPainter`.
- **Timeline**: [timeline_panel.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/components/timeline_panel.py) for multi-track audio/video editing with time rulers and draggable clips.
- **Dock Workspace**: [dock_workspace.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/components/dock_workspace.py) for modular, dockable panels.
- **Log Panel**: [log_panel.py](file:///Users/vannya/Desktop/MinJ/src/jela/gui/components/log_panel.py) for streaming execution logs.

## 3. High-DPI & Responsiveness
- High-DPI pass-through rounding is enabled at startup.
- Never use fixed hardcoded window pixel sizes for dynamic layouts; use `min_width`, `max_width`, stretch factors, and responsive layout managers (`QVBoxLayout`, `QHBoxLayout`, `QSplitter`).
