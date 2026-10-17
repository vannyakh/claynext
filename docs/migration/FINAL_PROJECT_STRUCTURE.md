# Final Project Structure — Claynext Studio

**Status**: PRODUCTION RESTRUCTURED  
**Architecture Standard**: Clean Layered Architecture + Native Rust Backends  

---

## 1. High-Level Workspace Architecture

```text
Claynext/
├── backends/                  # Native Rust multimedia backends (Cargo workspace)
│   ├── Cargo.toml             # Multi-crate workspace declaration
│   ├── Cargo.lock
│   ├── README.md              # Technical specification & benchmark report
│   ├── ffmpeg/                # Probe, transcode, demux, mux, raw frame & PCM extraction
│   │   ├── Cargo.toml
│   │   ├── src/lib.rs, probe.rs, transcode.rs, extract.rs, stream.rs, process.rs, error.rs
│   │   ├── src/bin/claynext-ffmpeg.rs
│   │   └── tests/integration_tests.rs
│   ├── cpu/                   # Audio resampler, multi-track mixer, peak/RMS stats, waveform binning
│   │   ├── Cargo.toml
│   │   ├── src/lib.rs, resample.rs, mix.rs, stats.rs, threadpool.rs
│   │   └── src/bin/claynext-cpu.rs
│   ├── wgpu/                  # WGPU compute shaders (color grading, gaussian blur, transitions)
│   │   ├── Cargo.toml
│   │   ├── src/lib.rs, device.rs, pipeline.rs, shaders.rs
│   │   └── src/bin/claynext-wgpu.rs
│   ├── ai-runtime/            # DirectML / CUDA / CPU inference configuration, energy VAD chunker
│   │   ├── Cargo.toml
│   │   ├── src/lib.rs, vad.rs, providers.rs
│   │   └── src/bin/claynext-ai.rs
│   └── hardware-codecs/       # Dual GPU discovery (Intel QSV, AMD AMF, NVIDIA NVENC)
│       ├── Cargo.toml
│       ├── src/lib.rs, detect.rs, profiles.rs
│       └── src/bin/claynext-codecs.rs
│
├── src/claynext/              # Python application package (Clean Architecture)
│   ├── __init__.py            # Package root & metadata
│   ├── app.py                 # Application lifecycle, splash, offscreen checks, arguments
│   │
│   ├── models/                # Strongly-typed immutable domain & presentation models
│   │   ├── __init__.py
│   │   ├── media.py           # MediaMetadata, StreamInfo, CodecInfo, Rational
│   │   ├── hardware.py        # GpuVendor, GpuDevice, EncoderProfile, CodecCapability
│   │   ├── project.py         # Project, ProjectSettings, ProjectManifest
│   │   ├── timeline.py        # TimelineClip, TimelineTrack, TimelineState
│   │   ├── dubbing.py         # DialogueSegment, DubbingBatch, SpeakerProfile
│   │   └── text_style.py      # CaptionStyle, AssStyle, typography & animations
│   │
│   ├── adapters/              # Infrastructure bridges to Rust binaries & OS
│   │   ├── __init__.py
│   │   ├── rust_bridge/         # Native Rust CLI bridges (ffmpeg, codecs, cpu, ai, wgpu)
│   │   ├── ffmpeg_adapter.py  # FFmpeg orchestration adapter
│   │   ├── hardware_codecs_adapter.py # GPU hardware capability discovery adapter
│   │   └── sysinfo_adapter.py # System hardware, RAM, CPU & device query adapter
│   │
│   ├── controllers/           # UI coordination, state machines & SQLite store
│   │   ├── __init__.py
│   │   ├── store.py           # SQLite database persistence for settings, models & cache
│   │   ├── studio_controller.py # Multi-track editing, playback sync & scrubbing
│   │   ├── export_controller.py # Render pipeline coordination & progress monitoring
│   │   └── project_controller.py # Project creation, opening, saving, bundle export
│   │
│   ├── services/              # Domain business logic & Python AI model integrations
│   │   ├── __init__.py
│   │   ├── media_service.py   # High-level media probing, audio extracting & transcoding
│   │   ├── export_service.py  # Composition rendering & hardware encoder delegation
│   │   ├── project_service.py # Project file serialization & asset packing
│   │   ├── dub_project.py     # Multi-track audio ducking, alignment & batch synthesis
│   │   ├── ffmpeg_service.py  # FFmpeg process spawning, filter graphs & progress hooks
│   │   ├── media_compat.py    # Playback proxy generation & audio format normalization
│   │   ├── thumbnails.py      # Rapid timeline video scrubbing thumbnail generator
│   │   ├── asr_service.py     # Faster-Whisper automatic speech recognition
│   │   ├── tts_service.py     # Neural multi-voice TTS (Edge-TTS & KittenTTS)
│   │   ├── tts_expression.py  # SSML emotion/style expression tag parser
│   │   ├── translate_service.py # Subtitle translation via Deep-Translator
│   │   ├── dubbing_service.py # Automated dubbing pipeline controller
│   │   ├── dubbing_plan.py    # WhisperX diarization & dialogue chunking
│   │   ├── stem_separation.py # Demucs / Demucs-MLX vocal stem isolation
│   │   ├── gender_audio.py    # Acoustic speaker gender classifier
│   │   ├── gender_voices.py   # Gender-appropriate TTS voice selector
│   │   ├── ocr_service.py     # EasyOCR frame text detection
│   │   ├── hf_hub.py          # Hugging Face model downloader & cache manager
│   │   ├── llm_keys.py        # Secure API key storage & provider rotation
│   │   ├── features.py        # Optional AI engine feature detection
│   │   ├── voice_detect.py    # Voice activity detection & silence trimmer
│   │   ├── video_adjust.py    # Color correction, brightness, contrast, hue & saturation
│   │   ├── video_canvas.py    # Canvas aspect ratios, letterboxing & viewport scaling
│   │   ├── video_engine.py    # Video composition renderer
│   │   ├── video_fx.py        # Visual filters, LUTs & motion effects
│   │   └── video_transitions.py # Transitions (cross dissolve, wipe, slide, fade)
│   │
│   ├── constants/             # Application constants and tokens
│   │   ├── __init__.py
│   │   ├── app_constants.py   # App ID, versions, fallback defaults
│   │   ├── theme_constants.py # Cyber Dark theme palette, spacing, typography tokens
│   │   └── ui_constants.py    # Window sizes, frameless chrome policies
│   │
│   ├── utils/                 # Low-level helpers
│   │   ├── __init__.py
│   │   ├── config.py          # App configuration loader
│   │   ├── logging.py         # Structured logging setup
│   │   ├── paths.py           # Cross-platform paths, cache & models directory resolver
│   │   └── job_control.py     # Cooperative cancellation token for workers
│   │
│   └── gui/                   # PySide6 desktop user interface
│       ├── __init__.py
│       ├── icons.py           # Crisp SVG icon rasterizer (High-DPI 2x)
│       ├── worker.py          # PySide6 QRunnable/QThreadPool background worker
│       ├── splash_screen.py   # Cyber Dark animated splash loader
│       ├── main_window.py     # Root Studio window with custom title bar & docking
│       ├── components/        # Reusable UI widgets
│       │   ├── title_bar.py   # Frameless window chrome
│       │   ├── sidebar.py     # Left navigation rail
│       │   ├── header.py      # Top action bar
│       │   ├── status_bar.py  # Bottom status & hardware monitor
│       │   ├── media_preview.py # Hardware-accelerated video/audio player
│       │   ├── media_library.py # Media asset browser & drop zone
│       │   ├── properties_panel.py # Clip properties & transform controls
│       │   ├── text_styles_panel.py # Subtitle styling & preset gallery
│       │   ├── text_render.py # Canvas text overlay painter
│       │   ├── shape_render.py # Vector shape overlay painter
│       │   ├── fx_shelf.py    # Effects & transition picker
│       │   ├── log_panel.py   # Real-time process logging dock
│       │   ├── wave_visualizer.py # Audio waveform canvas
│       │   └── timeline/      # Multi-track non-linear video/audio timeline
│       │       ├── panel.py, canvas.py, ruler.py, lane_rail.py, track_header.py, models.py
│       ├── dialogs/           # Modal dialogs
│       │   ├── new_project_dialog.py
│       │   ├── project_settings_dialog.py
│       │   ├── export_dialog.py
│       │   ├── settings_dialog.py
│       │   ├── api_keys_dialog.py
│       │   └── start_dub_dialog.py
│       ├── styles/            # Modular Cyber Dark QSS stylesheets
│       │   ├── shell.py, studio.py, home.py, widgets.py, controls.py, media.py
│       ├── theme/             # Theme color definitions & icon maps
│       └── views/             # Major tool views
│           ├── studio/        # Full timeline dubbing & editing studio
│           └── settings/      # Application preferences & AI engine status
│
├── docs/                      # Architectural & migration documentation
│   ├── backends/              # Rust backend architecture & ffmpeg specifications
│   └── migration/             # Cleanup inventory, move maps & audit reports
│
├── assets/                    # Icons, branding, SVG artwork & themes
├── data/                      # Local user projects, models & outputs (git-ignored)
├── extract_dubbing_batches.py # Standalone CLI automation script
├── main.py                    # Application launch entry point
├── pyproject.toml             # Python package config (uv / hatchling)
└── README.md                  # Project overview & quick start
```
