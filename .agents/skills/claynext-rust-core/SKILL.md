---
name: claynext-rust-core
description: >-
  Hybrid architecture skill for Claynext Studio. Use when implementing or
  migrating tools to Rust backends/crates, wiring Python Adapters, or changing
  GUI/models that call core media/AI logic. Covers the migration from
  all-Python to Rust core + Python GUI for performance.
---

# Claynext Rust Core + Python GUI

Claynext Studio is transforming from an all-Python codebase to a hybrid stack:
**PySide6 GUI and orchestration stay in Python; performance-critical core logic
moves to Rust** (`backends/`, `crates/`), invoked through **Adapters**.

---

## 1. Architecture map

```text
┌─────────────────────────────────────────────────────────────┐
│  Python GUI / CLI  (src/claynext/gui, cli)                  │
│  Workers (QThreadPool) — never block Qt main thread         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Models  (src/claynext/models)                              │
│  TranslateEngine, DubbingEngine, TTS, ASR, LLM keys, …      │
└───────────────────────────┬─────────────────────────────────┘
                            │  domain APIs only
┌───────────────────────────▼─────────────────────────────────┐
│  Adapters  (src/claynext/adapters)                          │
│  AiAdapter · DubbingAdapter · FFmpegAdapter · Media · …     │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  rust_bridge  (adapters/rust_bridge/*)                      │
│  find binary · UTF-8 subprocess · JSON IPC                  │
└───────────────────────────┬─────────────────────────────────┘
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
   backends/* CLI      crates/editor-*    (Python fallback)
   claynext-ai         editor-dubbing
   claynext-ffmpeg     editor-speech
   claynext-cpu        …
```

---

## 2. Backend API surface (Rust CLI tools)

### `claynext-ai` (`backends/ai-runtime`)

| Command | Use |
|:---|:---|
| `speech-quota` | Line duration → min/target/max speaking units |
| `build-dub-prompt` | Cinematic LLM prompt (fit / slang / expression) |
| `build-translate-prompt` | Simple subtitle prompt |
| `align-speed` | Tempo to fit TTS into slot |
| `ducked-volume` | Linear vol from dB attenuation |
| `energy-vad` / `vad-sim` | Voice activity spans |
| `parse-expression-tags` | TTS cue parsing |
| `chunk-subtitles` | Batch packing |
| `filter-ocr` | Confidence filter |
| `llm-parse-retry` / `llm-acquire` / `llm-soonest-cooldown` | Key pool |

### `claynext-ffmpeg` (`backends/ffmpeg`)

| Command | Use |
|:---|:---|
| `probe` | Media metadata |
| `extract-still` | Thumbnails / posters |
| `decode-audio` | PCM f32 (+ optional `.f32` out path) |
| `demux-audio` | Extract PCM WAV (sample rate / channels) |
| `export` / `mux` | Transcode / mux |

### Also

- `claynext-cpu` — waveform bins  
- `claynext-codecs` — GPU / encoder args  
- `claynext-wgpu` — device info  

Build example:

```bash
cargo build -p claynext-ai-runtime --bin claynext-ai
cargo build -p claynext-ffmpeg --bin claynext-ffmpeg
```

Binaries land in `target/debug` or `target/release` (honour `CARGO_TARGET_DIR`).

---

## 3. Adapter checklist (how agents should wire tools)

1. **Implement** logic in Rust (`backends/` lib + bin command, or `crates/`).
2. **Expose** CLI args → JSON/text stdout.
3. **Bridge** method on `rust_bridge` (e.g. `RustAiAdapter.estimate_speech_quota`).
4. **Facade** on domain adapter (`get_dubbing_adapter().estimate_speech_quota`).
5. **Call from models/GUI** only via the domain adapter.
6. **Fallback** in adapter or model if binary missing.
7. **Worker** for anything heavy before touching the UI.

### Correct

```python
from claynext.adapters.dubbing import get_dubbing_adapter

quota = get_dubbing_adapter().estimate_speech_quota(2.0, "Khmer")
```

### Incorrect

```python
from claynext.adapters.rust_bridge import RustAiAdapter  # not from models/gui
RustAiAdapter.estimate_speech_quota(...)
```

---

## 4. What stays in Python (for now)

- PySide6 UI, Cyber Dark QSS, project/settings store  
- Edge-TTS / Kitten / VoxCPM synthesis network & ONNX hosts  
- faster-whisper / WhisperX / Gemini HTTP  
- Demucs stem separation Python packages  
- High-level pipeline orchestration and JobControl  

Move **formulas, filters, packing, timing, probe/decode** to Rust as you touch them.

---

## 5. Related skills & rules

- Workspace: `AGENTS.md`, `.cursor/rules/rust-python-architecture.mdc`  
- UI: `claynext-ui-component`  
- Pipelines: `claynext-media-pipeline`  
- Dev smoke: `claynext-dev-workflow`  
