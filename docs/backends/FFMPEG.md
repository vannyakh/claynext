# FFmpeg Backend Specification & Implementation

## 1. Overview

The `claynext-ffmpeg` backend provides an industrial-grade, secure, non-blocking media engine interface over system-resolved FFmpeg/FFprobe binaries.

### Key Capabilities
- **Probing (`probe.rs`)**: Deep JSON inspection of containers, rational timestamps/fps, audio channel layouts, video color science metadata, and VFR detection.
- **Decoding (`decoder.rs`)**: Sub-second accurate seek and fast keyframe seek; direct extraction of raw RGBA8 video frame buffers; audio PCM 32-bit floating point stream decoding via pipes.
- **Encoding (`encoder.rs`)**: High-throughput video (H.264, H.265, NVENC, QSV, AMF) and audio (AAC, Opus, PCM) encoding with real-time progress callbacks and cancel tokens.
- **Demuxing & Muxing (`demuxer.rs`, `muxer.rs`)**: Zero-reencode stream-copy extraction and audio/video muxing with delay compensation and container alignment.
- **Process Management (`process.rs`, `error.rs`)**: Shell-injection-safe parameter passing, timeout enforcement, graceful cancellation, and structured `FfmpegError` categorization.

---

## 2. API Contract

### Media Inspection
```rust
use claynext_ffmpeg::probe_media_file;
use std::path::Path;

let info = probe_media_file(Path::new("movie.mp4"))?;
println!("Format: {}, Duration: {:.2}s", info.format_name, info.duration_seconds);

if let Some((stream, v_meta)) = info.video_stream() {
    println!("Resolution: {}x{}, Pixel Format: {}", v_meta.width, v_meta.height, v_meta.pixel_format);
}
```

### Video Frame Extraction
```rust
use claynext_ffmpeg::{extract_frame_rgba, SeekMode};
use std::path::Path;

let frame = extract_frame_rgba(
    Path::new("movie.mp4"),
    12.5, // 12.5 seconds
    Some(1280), Some(720), // Target scale
    SeekMode::Accurate,
    None // Optional Arc<AtomicBool> cancel token
)?;
assert_eq!(frame.data.len(), (1280 * 720 * 4) as usize);
```

### Video Export Pipeline
```rust
use claynext_ffmpeg::{run_export_job, ExportJob, VideoEncoderConfig, AudioEncoderConfig};
use std::path::PathBuf;

let job = ExportJob {
    input_path: PathBuf::from("input.mp4"),
    output_path: PathBuf::from("output.mp4"),
    video: VideoEncoderConfig {
        codec: "libx264".into(),
        crf: Some(20),
        preset: "faster".into(),
        ..Default::default()
    },
    audio: AudioEncoderConfig::default(),
    start_time_secs: None,
    duration_secs: None,
};

run_export_job(&job, None, None, |progress| {
    if let Some(t) = progress.time_seconds {
        println!("Progress: {:.1}s", t);
    }
})?;
```

---

## 3. Licensing & Distribution Considerations

1. **FFmpeg LGPL vs GPL**:
   - `libx264` and `libx265` are licensed under GNU GPL v2/v3. If distributing FFmpeg binaries statically or dynamically bundled with these codecs, the resulting FFmpeg distribution must comply with the GPL.
   - For closed-source or commercial deployments, FFmpeg can be configured with LGPL-only codecs (e.g. native AAC, OpenH264, VP9, AV1 rav1e, or hardware-accelerated NVENC/AMF/QSV which use proprietary driver APIs outside GPL requirements).
2. **Patent Licensing**:
   - AVC/H.264 and HEVC/H.265 are subject to patent pool royalties (MPEG LA / Via LA).
   - Using system hardware codecs (e.g., NVENC, Intel QSV, Apple VideoToolbox) leverages hardware licensing already paid by device OEMs.
