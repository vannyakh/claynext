# Cleanup Inventory — Core Python to Rust Migration

## 1. Inventory Summary

This audit classifies all files in `src/claynext/core/` and `src/claynext/tools/` for migration into the target architecture:
- **Rust Core (`backends/`)**: Media probing, frame decoding, transcoding, muxing, demuxing, SIMD audio DSP, hardware codec selection, compute shaders.
- **Python Adapters (`adapters/`)**: Native Rust core wrappers.
- **Python Services (`services/`)**: AI model inference (Whisper ASR, Edge-TTS, Demucs stem separation) and domain services.
- **Python Controllers (`controllers/`)**: Studio UI state, store, and export controllers.
- **Python Models (`models/`)**: Strongly-typed dataclasses for media, projects, timelines.
- **Python GUI (`gui/`)**: PySide6 widgets, icons, workers, and styling.

---

## 2. Classification Matrix

| File Path | Current Responsibility | Classification | Target Location / Rust Replacement |
| :--- | :--- | :--- | :--- |
| `core/ffmpeg_tools.py` | Subprocess FFmpeg probing, frame grabbing, muxing, mixing | **REPLACE & MOVE** | `backends/ffmpeg` (Rust) + `adapters/rust_bridge/` + `adapters/ffmpeg_service.py` |
| `core/media_compat.py` | AAC conversion & proxy generation | **REPLACE & MOVE** | `backends/ffmpeg` (Rust) + `services/media_service.py` |
| `core/thumbnails.py` | Video frame thumbnails | **REPLACE & MOVE** | `backends/ffmpeg/decoder.rs` (Rust) + `services/media_service.py` |
| `core/sysinfo.py` | GPU detection & VRAM querying | **REPLACE & MOVE** | `backends/hardware-codecs/detect.rs` (Rust) + `adapters/sysinfo_adapter.py` |
| `core/rust_backends.py` | Early bridge script | **REPLACE & DELETE** | Consolidated into `adapters/rust_bridge/` |
| `core/icons.py` | PySide6 QIcon loading & SVG rasterization | **MOVE** | `gui/icons.py` (UI-specific) |
| `core/worker.py` | PySide6 QThreadPool worker | **MOVE** | `gui/worker.py` (UI-specific) |
| `core/store.py` | Reactive central application store | **MOVE** | `controllers/store.py` |
| `core/job_control.py` | Pipeline pause/cancel state token | **MOVE** | `utils/job_control.py` |
| `core/dub_project.py` | Project saving/loading/presets | **MOVE** | `services/dub_project.py` & `models/project.py` |
| `core/asr_engine.py` | Faster-Whisper ASR inference | **MOVE** | `services/asr_service.py` |
| `core/tts_engine.py` | Edge-TTS & KittenTTS synthesis | **MOVE** | `services/tts_service.py` |
| `core/tts_expression.py`| Emotion/pitch chips | **MOVE** | `services/tts_expression.py` |
| `core/translate_engine.py` | Deep-Translator caption NMT | **MOVE** | `services/translate_service.py` |
| `core/dubbing_engine.py` | Dubbing timeline mixer & runner | **MOVE** | `services/dubbing_service.py` |
| `core/dubbing_plan.py` | Dubbing batch plan extractor | **MOVE** | `services/dubbing_plan.py` |
| `core/stem_separation.py` | Demucs music/vocal separation | **MOVE** | `services/stem_separation.py` |
| `core/gender_audio.py` | Audio gender classification | **MOVE** | `services/gender_service.py` |
| `core/gender_voices.py` | Voice selection per gender | **MOVE** | `services/gender_service.py` |
| `core/ocr_engine.py` | EasyOCR video frame recognition | **MOVE** | `services/ocr_service.py` |
| `core/hf_hub.py` | Hugging Face model downloader | **MOVE** | `services/hf_hub_service.py` |
| `core/llm_keys.py` | API keys management | **MOVE** | `services/llm_keys_service.py` |
| `core/features.py` | Store & demux feature flags | **MOVE** | `services/features.py` |
| `core/voice_detect.py` | Voice activity detection | **MOVE** | `services/voice_detect.py` (and `backends/ai-runtime`) |
| `core/text_style.py` | Subtitle font & visual styles | **MOVE** | `models/text_style.py` & `gui/components/` |
| `core/video_adjust.py` | Video adjustment filters | **MOVE** | `services/video_engine.py` (and `backends/wgpu`) |
| `core/video_canvas.py` | Video preview layout math | **MOVE** | `services/video_engine.py` |
| `core/video_engine.py` | Video engine coordination | **MOVE** | `services/video_engine.py` |
| `core/video_fx.py` | Visual FX and filter graphs | **MOVE** | `services/video_engine.py` |
| `core/video_transitions.py` | Transition shader parameters | **MOVE** | `services/video_engine.py` |
| `tools/extract_dubbing_batches.py` | CLI batch extraction tool | **MOVE** | `extract_dubbing_batches.py` (root CLI) |
