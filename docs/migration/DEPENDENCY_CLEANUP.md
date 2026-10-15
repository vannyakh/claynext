# Dependency Cleanup Report — Claynext Studio

**Status**: COMPLETED  
**Scope**: Python dependencies, Rust workspace dependencies, build configurations.

---

## 1. Python Dependency Audit

### Tracked in `pyproject.toml`

| Dependency | Purpose | Status | Notes |
| :--- | :--- | :--- | :--- |
| `pyside6>=6.11.2` | Primary GUI framework | KEPT | Core desktop interface |
| `imageio-ffmpeg>=0.6.0` | Fallback bundled FFmpeg binary resolver | KEPT | Used if system FFmpeg is absent |
| `ffmpeg-python>=0.2.0` | Python FFmpeg pipeline wrapper | KEPT | Coexists with Rust CLI adapter |
| `faster-whisper>=1.2.1` | Local neural ASR model | KEPT | Fast CPU/CUDA transcription |
| `edge-tts>=7.2.8` | High-quality neural speech synthesis | KEPT | Free multi-speaker TTS |
| `deep-translator>=1.11.4` | Subtitle translation (Google/DeepL/MyMemory) | KEPT | Required for NMT pipeline |
| `moviepy>=2.2.1` | Auxiliary video/audio transformations | KEPT | Used in specialized workflows |
| `onnxruntime==1.19.2` | CPU/GPU ONNX model inference | KEPT | Required by KittenTTS & EasyOCR |
| `transformers>=4.57.6` | Hugging Face tokenizer & acoustic models | KEPT | Used by optional pipelines |
| `sentencepiece>=0.2.2` | Tokenizer dependency | KEPT | Model dependency |
| `av==14.1.0` | PyAV direct container/frame access | KEPT | Fast frame decoding fallback |
| `kittentts` | Ultra-fast lightweight CPU TTS | KEPT | Optional on-device TTS engine |

### Optional Groups Preserved
- `whisperx`: Word-level alignment and speaker diarization.
- `demucs`: Meta's Hybrid Demucs vocal and music stem separator.
- `demucs-mlx`: Apple Silicon accelerated Demucs stem separator.
- `voxcpm`: Voice cloning and cross-lingual TTS.
- `gender`: Voice acoustic classification model.

---

## 2. Rust Workspace Dependencies (`backends/Cargo.toml`)

All 5 crates share common, audited dependencies:

| Crate Name | Purpose | Crates Using |
| :--- | :--- | :--- |
| `serde` & `serde_json` | Strongly typed JSON IPC serialization | `ffmpeg`, `cpu`, `hardware-codecs`, `wgpu`, `ai-runtime` |
| `thiserror` | Custom structured error enum derive | `ffmpeg`, `cpu`, `hardware-codecs`, `wgpu`, `ai-runtime` |
| `tempfile` | Isolated temp file creation in tests | `ffmpeg` |
| `wgpu` | Cross-platform GPU compute pipeline | `wgpu` |

---

## 3. Scripts and CLI Entry Points Cleaned

1. **`claynext-dub-plan` & `jela-dub-plan`**:
   - Updated from obsolete `claynext.core.dubbing_plan:main` to `claynext.services.dubbing_plan:main`.
2. **`extract_dubbing_batches.py`**:
   - Updated from legacy `claynext.core.dubbing_plan` to `claynext.services.dubbing_plan`.
   - Removed obsolete copy inside `src/claynext/tools/`.
3. **`uv.lock`**:
   - Re-synced and locked to `claynext 0.1.0`.
