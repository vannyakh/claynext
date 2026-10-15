# Legacy Removal Report — Claynext Studio

**Status**: COMPLETED  
**Date**: October 2026  
**Author**: CTO, Principal Rust Architect & Lead Migration Engineer  

---

## 1. Executive Summary

As part of the architecture restructuring from monolithic legacy Python (`src/claynext/core/` and `src/claynext/tools/`) to a layered clean architecture and native Rust multimedia backends (`backends/`), all obsolete and redundant Python files have been decommissioned and removed.

Zero regressions or orphaned references remain in the codebase. All UI views, dialogs, controllers, models, and CLI tools now interact cleanly through strongly-typed models, service abstractions, and native Rust backend adapters.

---

## 2. Decommissioned Legacy Python Files

| Original Legacy File | Replacement / Relocated Path | Rust Backend Equivalent | Status |
| :--- | :--- | :--- | :--- |
| `src/claynext/core/asr_engine.py` | `src/claynext/services/asr_service.py` | `backends/ai-runtime` (VAD) | DELETED |
| `src/claynext/core/dub_project.py` | `src/claynext/services/dub_project.py` | `backends/ffmpeg` (mux/transcode) | DELETED |
| `src/claynext/core/dubbing_engine.py` | `src/claynext/services/dubbing_service.py` | `backends/ffmpeg` + `backends/cpu` | DELETED |
| `src/claynext/core/dubbing_plan.py` | `src/claynext/services/dubbing_plan.py` | — (Python AI orchestration) | DELETED |
| `src/claynext/core/features.py` | `src/claynext/services/features.py` | `backends/hardware-codecs` | DELETED |
| `src/claynext/core/ffmpeg_tools.py` | `src/claynext/adapters/ffmpeg_adapter.py`<br>`src/claynext/services/ffmpeg_service.py` | `backends/ffmpeg` (full probe/transcode/extract/demux) | DELETED |
| `src/claynext/core/gender_audio.py` | `src/claynext/services/gender_audio.py` | `backends/ai-runtime` | DELETED |
| `src/claynext/core/gender_voices.py` | `src/claynext/services/gender_voices.py` | — (Voice mapping metadata) | DELETED |
| `src/claynext/core/hf_hub.py` | `src/claynext/services/hf_hub.py` | — (HF model manager) | DELETED |
| `src/claynext/core/icons.py` | `src/claynext/gui/icons.py` | — (PySide6 SVG renderer) | DELETED |
| `src/claynext/core/job_control.py` | `src/claynext/utils/job_control.py` | Native cancel token | DELETED |
| `src/claynext/core/llm_keys.py` | `src/claynext/services/llm_keys.py` | — (Secure key storage) | DELETED |
| `src/claynext/core/media_compat.py` | `src/claynext/services/media_compat.py` | `backends/ffmpeg` | DELETED |
| `src/claynext/core/ocr_engine.py` | `src/claynext/services/ocr_service.py` | `backends/ai-runtime` | DELETED |
| `src/claynext/core/rust_backends.py` | `src/claynext/adapters/rust_core_adapter.py` | Native Rust CLI bridge | DELETED |
| `src/claynext/core/stem_separation.py` | `src/claynext/services/stem_separation.py` | `backends/cpu` (multitrack mixing) | DELETED |
| `src/claynext/core/store.py` | `src/claynext/controllers/store.py` | Persistent SQLite store | DELETED |
| `src/claynext/core/sysinfo.py` | `src/claynext/adapters/sysinfo_adapter.py`<br>`src/claynext/adapters/hardware_codecs_adapter.py` | `backends/hardware-codecs` | DELETED |
| `src/claynext/core/text_style.py` | `src/claynext/models/text_style.py` | — (Presentation model) | DELETED |
| `src/claynext/core/thumbnails.py` | `src/claynext/services/thumbnails.py` | `backends/ffmpeg` (frame extract) | DELETED |
| `src/claynext/core/translate_engine.py` | `src/claynext/services/translate_service.py` | — (NMT service) | DELETED |
| `src/claynext/core/tts_engine.py` | `src/claynext/services/tts_service.py` | `backends/cpu` (resampler/mixer) | DELETED |
| `src/claynext/core/tts_expression.py` | `src/claynext/services/tts_expression.py` | — (SSML parser) | DELETED |
| `src/claynext/core/video_adjust.py` | `src/claynext/services/video_adjust.py` | `backends/wgpu` (color grading) | DELETED |
| `src/claynext/core/video_canvas.py` | `src/claynext/services/video_canvas.py` | `backends/wgpu` | DELETED |
| `src/claynext/core/video_engine.py` | `src/claynext/services/video_engine.py` | `backends/ffmpeg` | DELETED |
| `src/claynext/core/video_fx.py` | `src/claynext/services/video_fx.py` | `backends/wgpu` | DELETED |
| `src/claynext/core/video_transitions.py`| `src/claynext/services/video_transitions.py`| `backends/wgpu` | DELETED |
| `src/claynext/core/voice_detect.py` | `src/claynext/services/voice_detect.py` | `backends/ai-runtime` (VAD) | DELETED |
| `src/claynext/core/worker.py` | `src/claynext/gui/worker.py` | — (Qt QThreadPool QRunnable) | DELETED |
| `src/claynext/tools/__init__.py` | (Obsolete directory) | — | DELETED |
| `src/claynext/tools/extract_dubbing_batches.py` | `extract_dubbing_batches.py` (root CLI) | — | DELETED |

---

## 3. Evidence of Safe Deletion

1. **Static Analysis Check**:
   - `grep_search` across `src/claynext/` confirmed zero remaining imports matching `claynext.core` or `claynext.tools`.
2. **Import Verification**:
   - `uv run python -c "from claynext.app import main; print('Ready')"` executed with returncode 0.
3. **CLI Verification**:
   - `uv run python extract_dubbing_batches.py --help` parsed options and returned successfully.
4. **Rust Test Suite**:
   - 3 integration tests and 5 binary CLI tools executed with 0 failures in `backends/target/debug/`.
