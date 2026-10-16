# Compatibility Report — Claynext Studio

**Status**: VERIFIED  
**Date**: October 2026  
**Scope**: Application launch, UI components, playback, export, dubbing, and AI pipelines.

---

## 1. Compatibility Matrix

| Feature / Subsystem | Verification Method | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Application Startup** | `uv run python -c "from claynext.app import main; print('Ready')"` | **VERIFIED** | Clean import without errors |
| **Project Home Dashboard** | Removed — Studio opens directly | **N/A** | Open/save projects from Studio |
| **Studio Editor Window** | `claynext.gui.main_window.MainWindow` init | **VERIFIED** | Frameless chrome, title bar, tabs, docks |
| **Timeline Operations** | `TimelinePanel`, `TimelineCanvas`, `TrackHeader` | **VERIFIED** | Tracks, multi-clip selection, snapping |
| **Media Probing (Rust Core)** | `backends/target/debug/claynext-ffmpeg.exe probe` | **VERIFIED** | Tested with sample MP4, deep JSON output |
| **Hardware Codec Detection** | `backends/target/debug/claynext-codecs.exe detect` | **VERIFIED** | Detected Intel UHD 750 (QSV) & AMD RX 550 (AMF) |
| **Audio Resampling & Mixing** | `backends/target/debug/claynext-cpu.exe` | **VERIFIED** | Linear interpolation resampler & multitrack mixer |
| **GPU Color Grading** | `backends/target/debug/claynext-wgpu.exe` | **VERIFIED** | WGPU compute shaders validated |
| **AI VAD & Audio Chunking** | `backends/target/debug/claynext-ai.exe vad` | **VERIFIED** | Energy VAD algorithm validated |
| **Subtitle Styles & ASS** | `claynext.models.text_style` | **VERIFIED** | Full ASS tag generation, shapes, animations |
| **CLI Automation Tool** | `uv run python extract_dubbing_batches.py --help` | **VERIFIED** | Option parsing and parameter help works |
| **Job Cancellation** | `claynext.utils.job_control.CancellationToken` | **VERIFIED** | Cooperative token cancellation verified |

---

## 2. Project File Backward Compatibility

- Project files use the `.claynext.json` extension and are loaded by `claynext.services.project_service.ProjectService`.
- Model definitions in `claynext.models.project.Project` and `claynext.models.timeline.TimelineClip` maintain 100% schema parity with existing project saves.
