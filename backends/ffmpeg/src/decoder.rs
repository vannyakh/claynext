use crate::error::{FfmpegError, Result};
use crate::process::find_executable;
use serde::{Deserialize, Serialize};
use std::io::Read;
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PixelFormat {
    Rgba8,
    Rgb24,
    Yuv420p,
}

impl PixelFormat {
    pub fn to_ffmpeg_pix_fmt(&self) -> &'static str {
        match self {
            PixelFormat::Rgba8 => "rgba",
            PixelFormat::Rgb24 => "rgb24",
            PixelFormat::Yuv420p => "yuv420p",
        }
    }

    pub fn bytes_per_pixel(&self) -> usize {
        match self {
            PixelFormat::Rgba8 => 4,
            PixelFormat::Rgb24 => 3,
            PixelFormat::Yuv420p => 1, // Planar
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoFrame {
    pub width: u32,
    pub height: u32,
    pub pts: f64,
    pub format: PixelFormat,
    #[serde(skip_serializing)]
    pub data: Vec<u8>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioFrame {
    pub sample_rate: u32,
    pub channels: u32,
    pub pts: f64,
    pub samples: Vec<f32>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SeekMode {
    /// Fast keyframe seek (-ss before -i). Rapid, but jumps to preceding keyframe.
    FastKeyframe,
    /// Accurate frame seek (-ss after -i). Exact timestamp precision by decoding all prior frames.
    Accurate,
}

pub struct DecoderConfig {
    pub max_frames: Option<usize>,
    pub seek_mode: SeekMode,
    pub cancel_token: Option<Arc<AtomicBool>>,
}

impl Default for DecoderConfig {
    fn default() -> Self {
        Self {
            max_frames: None,
            seek_mode: SeekMode::Accurate,
            cancel_token: None,
        }
    }
}

/// Extract a single video frame at the requested timestamp as raw RGBA pixel buffer.
///
/// NOTE on Seeking:
/// - `SeekMode::FastKeyframe` specifies `-ss` before `-i`, enabling sub-second seeking in massive files.
/// - `SeekMode::Accurate` specifies `-ss` after `-i`, decoding up to the exact frame time.
pub fn extract_frame_rgba(
    path: &Path,
    timestamp_secs: f64,
    target_width: Option<u32>,
    target_height: Option<u32>,
    seek_mode: SeekMode,
    cancel_token: Option<Arc<AtomicBool>>,
) -> Result<VideoFrame> {
    if !path.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "Input file not found: {}",
            path.display()
        )));
    }

    let ffmpeg_exe = find_executable("ffmpeg").ok_or(FfmpegError::FfmpegNotFound)?;

    let mut cmd = Command::new(&ffmpeg_exe);
    cmd.arg("-y").arg("-v").arg("error");

    let ts_str = format!("{:.3}", timestamp_secs.max(0.0));

    if seek_mode == SeekMode::FastKeyframe {
        cmd.args(["-ss", &ts_str]);
    }

    cmd.args(["-i", path.to_str().unwrap_or_default()]);

    if seek_mode == SeekMode::Accurate {
        cmd.args(["-ss", &ts_str]);
    }

    cmd.args(["-frames:v", "1"]);

    if let (Some(w), Some(h)) = (target_width, target_height) {
        cmd.args(["-vf", &format!("scale={}:{}", w, h)]);
    }

    cmd.args(["-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1"]);
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    let mut child = cmd.spawn().map_err(FfmpegError::ProcessSpawn)?;

    if let Some(ref token) = cancel_token {
        if token.load(Ordering::Relaxed) {
            let _ = child.kill();
            return Err(FfmpegError::Cancelled);
        }
    }

    let mut stdout = child
        .stdout
        .take()
        .ok_or_else(|| FfmpegError::InvalidInput("Failed to open stdout pipe".into()))?;

    let mut buffer = Vec::new();
    stdout.read_to_end(&mut buffer).map_err(FfmpegError::Io)?;

    let status = child.wait().map_err(FfmpegError::Io)?;
    if !status.success() {
        let mut err_str = String::new();
        if let Some(mut err_pipe) = child.stderr.take() {
            let _ = err_pipe.read_to_string(&mut err_str);
        }
        return Err(FfmpegError::ProcessFailed {
            exit_code: status.code(),
            stderr: err_str,
        });
    }

    if buffer.is_empty() {
        return Err(FfmpegError::ProcessFailed {
            exit_code: status.code(),
            stderr: "Decoder returned empty frame data (end of stream or seek out of bounds)"
                .into(),
        });
    }

    // Determine actual dimensions
    let (final_w, final_h) = if let (Some(w), Some(h)) = (target_width, target_height) {
        (w, h)
    } else {
        // Probe original dimensions
        let info = crate::probe::probe_media_file(path)?;
        if let Some((_, v)) = info.video_stream() {
            (v.width, v.height)
        } else {
            return Err(FfmpegError::StreamNotFound {
                stream_type: "video".into(),
                index: None,
            });
        }
    };

    let expected_bytes = (final_w * final_h * 4) as usize;
    if buffer.len() < expected_bytes {
        return Err(FfmpegError::OutputValidation(format!(
            "Decoded frame size mismatch: got {} bytes, expected {} ({}x{} rgba)",
            buffer.len(),
            expected_bytes,
            final_w,
            final_h
        )));
    }

    buffer.truncate(expected_bytes);

    Ok(VideoFrame {
        width: final_w,
        height: final_h,
        pts: timestamp_secs,
        format: PixelFormat::Rgba8,
        data: buffer,
    })
}

/// Decode audio stream directly into raw interleaved 32-bit floating point PCM.
pub fn decode_audio_pcm_f32(
    path: &Path,
    target_sample_rate: u32,
    target_channels: u32,
    start_time_secs: Option<f64>,
    duration_secs: Option<f64>,
    cancel_token: Option<Arc<AtomicBool>>,
) -> Result<AudioFrame> {
    if !path.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "Input file not found: {}",
            path.display()
        )));
    }

    let ffmpeg_exe = find_executable("ffmpeg").ok_or(FfmpegError::FfmpegNotFound)?;

    let mut cmd = Command::new(&ffmpeg_exe);
    cmd.arg("-y").arg("-v").arg("error");

    if let Some(st) = start_time_secs {
        cmd.args(["-ss", &format!("{:.3}", st)]);
    }

    cmd.args(["-i", path.to_str().unwrap_or_default()]);

    if let Some(dur) = duration_secs {
        cmd.args(["-t", &format!("{:.3}", dur)]);
    }

    cmd.args([
        "-vn",
        "-f",
        "f32le",
        "-ar",
        &target_sample_rate.to_string(),
        "-ac",
        &target_channels.to_string(),
        "pipe:1",
    ]);

    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    let mut child = cmd.spawn().map_err(FfmpegError::ProcessSpawn)?;

    if let Some(ref token) = cancel_token {
        if token.load(Ordering::Relaxed) {
            let _ = child.kill();
            return Err(FfmpegError::Cancelled);
        }
    }

    let mut stdout = child
        .stdout
        .take()
        .ok_or_else(|| FfmpegError::InvalidInput("Failed to open stdout pipe".into()))?;

    let mut raw_bytes = Vec::new();
    stdout
        .read_to_end(&mut raw_bytes)
        .map_err(FfmpegError::Io)?;

    let status = child.wait().map_err(FfmpegError::Io)?;
    if !status.success() {
        let mut err_str = String::new();
        if let Some(mut err_pipe) = child.stderr.take() {
            let _ = err_pipe.read_to_string(&mut err_str);
        }
        return Err(FfmpegError::ProcessFailed {
            exit_code: status.code(),
            stderr: err_str,
        });
    }

    // Convert raw little-endian bytes to f32 samples
    let sample_count = raw_bytes.len() / 4;
    let mut samples = Vec::with_capacity(sample_count);

    for chunk in raw_bytes.chunks_exact(4) {
        let val = f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
        samples.push(val);
    }

    Ok(AudioFrame {
        sample_rate: target_sample_rate,
        channels: target_channels,
        pts: start_time_secs.unwrap_or(0.0),
        samples,
    })
}
