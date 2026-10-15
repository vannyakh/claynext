# Claynext Rust Core Backends

High-performance native multimedia and AI engine written in Rust for **Claynext Studio**.

---

## 1. Directory Structure

```text
backends/
├── Cargo.toml               # Workspace root configuration
├── README.md                # Architecture & integration documentation
├── ffmpeg/                  # Fast FFmpeg/FFprobe demuxing, remuxing & filtering
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── probe.rs         # JSON stream inspection & metadata extraction
│       ├── demux.rs         # Fast PCM WAV extraction & time slicing
│       ├── remux.rs         # Stream-copy audio replacement & remuxing
│       ├── filter.rs        # EBU R128 Loudnorm & sidechain ducking filter graph
│       └── bin/claynext-ffmpeg.rs
├── cpu/                     # Multi-threaded SIMD audio & DSP compute
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── resample.rs      # High-performance linear interpolation resampler
│       ├── mixer.rs         # Multi-track mixing & ducking envelopes
│       ├── simd.rs          # Peak/RMS calculations & waveform visualizer bins
│       ├── threadpool.rs    # Cross-platform worker threadpool
│       └── bin/claynext-cpu.rs
├── wgpu/                    # GPU compute shaders & timeline compositing
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── device.rs        # WGPU device/adapter descriptors & format selection
│       ├── compositor.rs    # Multi-track timeline layers & blend modes
│       ├── shaders.rs       # WGSL shaders for color grade & blur
│       ├── textures.rs      # RGBA8 texture buffers & dimensions
│       └── bin/claynext-wgpu.rs
├── ai-runtime/              # Unified AI inference runtime
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── engine.rs        # DirectML, CUDA, CoreML, CPU execution provider
│       ├── vad.rs           # Voice Activity Detection energy chunking
│       ├── asr.rs           # Whisper model configurations & transcription structures
│       ├── tts.rs           # Neural voice synthesis specifications
│       ├── model_cache.rs   # Model weight path resolution & integrity checks
│       └── bin/claynext-ai.rs
└── hardware-codecs/         # Hardware encoder detection & optimal profile selector
    ├── Cargo.toml
    └── src/
        ├── lib.rs
        ├── detect.rs        # GPU vendor detection (NVIDIA, AMD, Intel, Apple)
        ├── nvenc.rs         # NVIDIA NVENC / NVDEC hardware acceleration
        ├── qsv.rs           # Intel QuickSync Video profiles
        ├── amf.rs           # AMD Advanced Media Framework profiles
        ├── media_foundation.rs # Windows Media Foundation hardware encoders
        ├── profile.rs       # Automatic selection of optimal hardware encoder
        └── bin/claynext-codecs.rs
```

---

## 2. CLI Tool Usage

Each backend crate provides a dedicated binary CLI tool:

### Hardware Codecs
```bash
# Detect system GPUs and hardware encoding capabilities
cargo run -p claynext-hardware-codecs --bin claynext-codecs -- detect

# Get optimal encoder for system (JSON)
cargo run -p claynext-hardware-codecs --bin claynext-codecs -- optimal --hevc

# Output raw FFmpeg command line arguments
cargo run -p claynext-hardware-codecs --bin claynext-codecs -- ffmpeg-args --hevc
```

### FFmpeg Backend
```bash
# Fast JSON probe of any media file
cargo run -p claynext-ffmpeg --bin claynext-ffmpeg -- probe path/to/video.mp4

# Extract 16kHz mono WAV for Whisper
cargo run -p claynext-ffmpeg --bin claynext-ffmpeg -- extract-audio input.mp4 output.wav 16000 1

# Stream-copy replace audio track in video
cargo run -p claynext-ffmpeg --bin claynext-ffmpeg -- remux-audio video.mp4 dubbed.wav final.mp4
```

### CPU Backend
```bash
# Run SIMD audio statistics and resampling benchmark
cargo run -p claynext-cpu --bin claynext-cpu -- benchmark
```

### WGPU Backend
```bash
# Print GPU compute device info and capabilities
cargo run -p claynext-wgpu --bin claynext-wgpu -- info

# View color grading WGSL compute shader
cargo run -p claynext-wgpu --bin claynext-wgpu -- shader
```

### AI Runtime
```bash
# View active execution provider (DirectML / CUDA / CPU)
cargo run -p claynext-ai-runtime --bin claynext-ai -- device

# Run VAD speech chunking simulation
cargo run -p claynext-ai-runtime --bin claynext-ai -- vad-sim
```

---

## 3. Python Integration

Claynext tools connect to these Rust backends via `claynext.core.rust_backends`:

```python
from claynext.core.rust_backends import (
    detect_hardware_gpus,
    get_optimal_encoder_args,
    rust_probe_file,
    run_cpu_benchmark,
    get_ai_device_config,
    get_wgpu_info,
)

# Detect hardware encoders
gpus = detect_hardware_gpus()

# Automatically choose best NVENC/QSV/AMF flags for video export
encoder_args = get_optimal_encoder_args(prefer_hevc=True)
# -> ['-c:v', 'hevc_nvenc', '-preset', 'p4', '-tune', 'hq', ...]
```
