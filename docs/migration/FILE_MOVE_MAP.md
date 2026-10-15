# File Move and Relocation Map

This document defines the destination package for every legacy module in `src/claynext/core/` and `src/claynext/tools/`.

## 1. Relocation Mapping Table

| Source Path | Target Path | Primary Responsibility |
| :--- | :--- | :--- |
| `src/claynext/core/icons.py` | `src/claynext/gui/icons.py` | PySide6 QIcon loading & SVG rasterization |
| `src/claynext/core/worker.py` | `src/claynext/gui/worker.py` | PySide6 QThreadPool Worker & WorkerSignals |
| `src/claynext/core/store.py` | `src/claynext/controllers/store.py` | Reactive central store for studio workspace |
| `src/claynext/core/job_control.py` | `src/claynext/utils/job_control.py` | Job cancellation and pause tokens |
| `src/claynext/core/sysinfo.py` | `src/claynext/adapters/sysinfo_adapter.py`| GPU capability detection via Rust backend |
| `src/claynext/core/dub_project.py` | `src/claynext/services/dub_project.py` | Project loading, saving, and template presets |
| `src/claynext/core/ffmpeg_tools.py`| `src/claynext/services/ffmpeg_service.py`| Media FFmpeg operations via Rust core adapter |
| `src/claynext/core/media_compat.py`| `src/claynext/services/media_compat.py` | Proxy creation & audio compatibility |
| `src/claynext/core/thumbnails.py`  | `src/claynext/services/thumbnails.py` | Frame thumbnail extraction via Rust decoder |
| `src/claynext/core/asr_engine.py`  | `src/claynext/services/asr_service.py` | Faster-Whisper ASR inference engine |
| `src/claynext/core/tts_engine.py`  | `src/claynext/services/tts_service.py` | Edge-TTS & KittenTTS speech synthesis |
| `src/claynext/core/tts_expression.py`| `src/claynext/services/tts_expression.py`| Emotion and pitch SSML tags |
| `src/claynext/core/translate_engine.py`| `src/claynext/services/translate_service.py`| Deep-Translator caption NMT |
| `src/claynext/core/dubbing_engine.py`| `src/claynext/services/dubbing_service.py`| Dubbing pipeline & audio mixer runner |
| `src/claynext/core/dubbing_plan.py`| `src/claynext/services/dubbing_plan.py` | Speech diarization and batch planning |
| `src/claynext/core/stem_separation.py`| `src/claynext/services/stem_separation.py`| Demucs vocal/music separation |
| `src/claynext/core/gender_audio.py`| `src/claynext/services/gender_audio.py` | Gender classification from audio |
| `src/claynext/core/gender_voices.py`| `src/claynext/services/gender_voices.py` | Gender-to-voice mapping table |
| `src/claynext/core/ocr_engine.py`  | `src/claynext/services/ocr_service.py` | EasyOCR video frame text extraction |
| `src/claynext/core/hf_hub.py`      | `src/claynext/services/hf_hub.py` | Hugging Face model weight downloader |
| `src/claynext/core/llm_keys.py`    | `src/claynext/services/llm_keys.py` | API keys management |
| `src/claynext/core/features.py`    | `src/claynext/services/features.py` | Dynamic feature configuration flags |
| `src/claynext/core/voice_detect.py`| `src/claynext/services/voice_detect.py` | Voice activity detection |
| `src/claynext/core/text_style.py`  | `src/claynext/models/text_style.py` | Subtitle styling and visual models |
| `src/claynext/core/video_adjust.py`| `src/claynext/services/video_engine.py` | Video adjustments and effects |
| `src/claynext/core/video_canvas.py`| `src/claynext/services/video_engine.py` | Video layout mathematics |
| `src/claynext/core/video_engine.py`| `src/claynext/services/video_engine.py` | Video composition engine |
| `src/claynext/core/video_fx.py`    | `src/claynext/services/video_engine.py` | Video FX and filter graphs |
| `src/claynext/core/video_transitions.py`| `src/claynext/services/video_engine.py`| Transition shaders |
| `src/claynext/tools/extract_dubbing_batches.py`| `extract_dubbing_batches.py` | Root CLI execution wrapper |
| `src/claynext/core/rust_backends.py`| `src/claynext/adapters/rust_core_adapter.py`| Native Rust core adapter |
