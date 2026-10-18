use crate::error::{FfmpegError, Result};
use crate::process::{find_executable, FfmpegProgress, ManagedProcess};
use std::path::Path;
use std::process::Command;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use std::time::Duration;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContainerFormat {
    Mp4,
    Mkv,
    Webm,
    Mov,
}

impl ContainerFormat {
    pub fn from_extension(ext: &str) -> Option<Self> {
        match ext.to_lowercase().as_str() {
            "mp4" | "m4v" => Some(ContainerFormat::Mp4),
            "mkv" => Some(ContainerFormat::Mkv),
            "webm" => Some(ContainerFormat::Webm),
            "mov" => Some(ContainerFormat::Mov),
            _ => None,
        }
    }
}

pub struct MuxOptions {
    pub copy_video: bool,
    pub copy_audio: bool,
    pub match_shortest: bool,
    pub audio_delay_seconds: Option<f64>,
    pub audio_bitrate_kbps: u32,
    pub video_crf: u32,
    pub video_preset: String,
    /// When set, video is re-encoded with this ffmpeg filter graph.
    pub video_filter: String,
}

impl Default for MuxOptions {
    fn default() -> Self {
        Self {
            copy_video: true,
            copy_audio: false, // Default: re-encode to a safe compatible audio codec (AAC)
            match_shortest: true,
            audio_delay_seconds: None,
            audio_bitrate_kbps: 192,
            video_crf: 18,
            video_preset: "medium".into(),
            video_filter: String::new(),
        }
    }
}

/// Combine video and audio inputs into a single synchronized container file.
pub fn mux_video_audio(
    video_input: &Path,
    audio_input: &Path,
    output: &Path,
    options: &MuxOptions,
) -> Result<()> {
    mux_video_audio_progress(video_input, audio_input, output, options, None, None, |_| {})
}

/// Mux with live ffmpeg progress (encode time) for the export dialog.
pub fn mux_video_audio_progress<F>(
    video_input: &Path,
    audio_input: &Path,
    output: &Path,
    options: &MuxOptions,
    cancel_token: Option<Arc<AtomicBool>>,
    timeout: Option<Duration>,
    on_progress: F,
) -> Result<()>
where
    F: FnMut(FfmpegProgress),
{
    if !video_input.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "Video input not found: {}",
            video_input.display()
        )));
    }
    if !audio_input.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "Audio input not found: {}",
            audio_input.display()
        )));
    }

    if let Some(parent) = output.parent() {
        std::fs::create_dir_all(parent).map_err(FfmpegError::Io)?;
    }

    let ffmpeg_exe = find_executable("ffmpeg").ok_or(FfmpegError::FfmpegNotFound)?;

    let mut cmd = Command::new(&ffmpeg_exe);
    cmd.args([
        "-y",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-progress",
        "pipe:2",
    ]);

    // Video input (0)
    cmd.args(["-i", video_input.to_str().unwrap_or_default()]);

    // Audio input (1) with optional sync delay offset
    if let Some(delay) = options.audio_delay_seconds {
        if delay != 0.0 {
            cmd.args(["-itsoffset", &format!("{:.3}", delay)]);
        }
    }
    cmd.args(["-i", audio_input.to_str().unwrap_or_default()]);

    // Explicit stream mappings
    cmd.args(["-map", "0:v:0", "-map", "1:a:0"]);

    let copy_video = options.copy_video && options.video_filter.is_empty();
    if !options.video_filter.is_empty() {
        cmd.args(["-vf", &options.video_filter]);
    }

    // Video codec handling
    if copy_video {
        cmd.args(["-c:v", "copy"]);
    } else {
        let preset = if options.video_preset.is_empty() {
            "medium"
        } else {
            options.video_preset.as_str()
        };
        cmd.args([
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            &options.video_crf.to_string(),
            "-pix_fmt",
            "yuv420p",
        ]);
    }

    // Audio codec handling
    if options.copy_audio {
        cmd.args(["-c:a", "copy"]);
    } else {
        cmd.args([
            "-c:a",
            "aac",
            "-b:a",
            &format!("{}k", options.audio_bitrate_kbps.max(32)),
            "-ar",
            "44100",
            "-ac",
            "2",
        ]);
    }

    if options.match_shortest {
        cmd.arg("-shortest");
    }

    let out_ext = output
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if matches!(out_ext.as_str(), "mp4" | "m4v" | "mov") {
        cmd.args(["-movflags", "+faststart"]);
    }

    cmd.arg(output.to_str().unwrap_or_default());

    let process = ManagedProcess::spawn(cmd, cancel_token, timeout)?;
    process.wait_with_progress(on_progress)?;

    if !output.is_file() {
        return Err(FfmpegError::OutputValidation(format!(
            "Mux output file not found: {}",
            output.display()
        )));
    }

    Ok(())
}
