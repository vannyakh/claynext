use crate::error::{FfmpegError, Result};
use crate::process::find_executable;
use std::path::Path;
use std::process::Command;

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
}

impl Default for MuxOptions {
    fn default() -> Self {
        Self {
            copy_video: true,
            copy_audio: false, // Default: re-encode to a safe compatible audio codec (AAC)
            match_shortest: true,
            audio_delay_seconds: None,
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
    cmd.arg("-y").arg("-v").arg("error");

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

    // Video codec handling
    if options.copy_video {
        cmd.args(["-c:v", "copy"]);
    } else {
        cmd.args([
            "-c:v", "libx264", "-preset", "faster", "-crf", "22", "-pix_fmt", "yuv420p",
        ]);
    }

    // Audio codec handling
    if options.copy_audio {
        cmd.args(["-c:a", "copy"]);
    } else {
        cmd.args(["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]);
    }

    if options.match_shortest {
        cmd.arg("-shortest");
    }

    cmd.arg(output.to_str().unwrap_or_default());

    let status = cmd.status().map_err(FfmpegError::ProcessSpawn)?;
    if !status.success() {
        return Err(FfmpegError::ProcessFailed {
            exit_code: status.code(),
            stderr: "Muxing video and audio streams failed".into(),
        });
    }

    if !output.is_file() {
        return Err(FfmpegError::OutputValidation(format!(
            "Mux output file not found: {}",
            output.display()
        )));
    }

    Ok(())
}
