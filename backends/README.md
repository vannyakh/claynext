# Claynext Rust Core Backends

High-performance native multimedia and hardware acceleration backends for **Claynext Studio**.

These backend crates are unified members of the root **Claynext Workspace** (`/Cargo.toml`). All binaries compile directly into the root `target/` directory.

---

## 1. Directory Structure

```text
backends/
├── ffmpeg/                  # Fast FFmpeg/FFprobe demuxing, remuxing & filtering
│   ├── Cargo.toml
│   ├── src/
│   │   ├── lib.rs
│   │   ├── probe.rs         # JSON stream inspection & metadata extraction
│   │   ├── transcode.rs     # Video/audio transcode with atomic cancel token
│   │   ├── extract.rs       # Raw frame & PCM stream decoders
│   │   ├── stream.rs        # Stream-copy demuxing & container muxing
│   │   ├── process.rs       # Async child process execution & progress parser
│   │   └── error.rs         # Structured FfmpegError enum
│   ├── src/bin/claynext-ffmpeg.rs
│   └── tests/integration_tests.rs
├── cpu/                     # Multi-threaded SIMD audio & DSP compute
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── resample.rs      # High-performance linear interpolation resampler
│       ├── mix.rs           # Multi-track mixing & ducking envelopes
│       ├── stats.rs         # Peak/RMS calculations & waveform visualizer bins
│       ├── threadpool.rs    # Cross-platform worker threadpool
│       └── bin/claynext-cpu.rs
├── wgpu/                    # GPU compute shaders & timeline compositing
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── device.rs        # WGPU device/adapter descriptors & format selection
│       ├── pipeline.rs      # Pipeline state & bind groups
│       ├── shaders.rs       # WGSL shaders for color grade & blur
│       └── bin/claynext-wgpu.rs
├── ai-runtime/              # Unified AI inference runtime
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── vad.rs           # Energy-based voice activity detection
│       ├── providers.rs     # DirectML, CUDA, and CPU execution provider selection
│       └── bin/claynext-ai.rs
└── hardware-codecs/         # Hardware encoder auto-selection
    ├── Cargo.toml
    └── src/
        ├── lib.rs
        ├── detect.rs        # GPU discovery (Intel QSV, AMD AMF, NVIDIA NVENC)
        ├── profiles.rs      # Optimal FFmpeg encoder arguments
        └── bin/claynext-codecs.rs
```

---

## 2. Compiling and Testing

From the project root:

```bash
# Build all backends and engine crates
cargo build --workspace

# Run all backend unit and integration tests
cargo test --workspace

# Run strict clippy linting
cargo clippy --workspace --all-targets -- -D warnings
```
