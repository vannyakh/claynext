use crate::error::{FfmpegError, Result};
use crate::process::find_executable;
use std::path::Path;
use std::process::Command;

/// Demux / extract audio to PCM WAV via bundled or system FFmpeg.
pub fn extract_audio_wav(
    input: &Path,
    output: &Path,
    sample_rate: u32,
    channels: u32,
) -> Result<()> {
    if !input.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "Input file not found: {}",
            input.display()
        )));
    }
    let ffmpeg_exe = find_executable("ffmpeg").ok_or(FfmpegError::FfmpegNotFound)?;
    if let Some(parent) = output.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    let status = Command::new(&ffmpeg_exe)
        .args([
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input.to_str().unwrap_or_default(),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            &sample_rate.to_string(),
            "-ac",
            &channels.to_string(),
            output.to_str().unwrap_or_default(),
        ])
        .status()
        .map_err(FfmpegError::ProcessSpawn)?;

    if !status.success() || !output.is_file() {
        return Err(FfmpegError::ProcessFailed {
            exit_code: status.code(),
            stderr: "FFmpeg audio demux failed".into(),
        });
    }
    Ok(())
}
