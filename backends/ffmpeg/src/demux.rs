use std::path::Path;
use std::process::Command;

pub fn extract_audio_wav(
    input: &Path,
    output: &Path,
    sample_rate: u32,
    channels: u32,
    ffmpeg_exe: Option<&str>,
) -> Result<(), anyhow::Error> {
    let bin = ffmpeg_exe.unwrap_or("ffmpeg");

    let status = Command::new(bin)
        .args([
            "-y",
            "-i", input.to_str().unwrap_or_default(),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", &sample_rate.to_string(),
            "-ac", &channels.to_string(),
            output.to_str().unwrap_or_default(),
        ])
        .status()?;

    if !status.success() {
        return Err(anyhow::anyhow!("FFmpeg audio extraction failed"));
    }
    Ok(())
}

pub fn extract_time_slice(
    input: &Path,
    output: &Path,
    start_sec: f64,
    duration_sec: f64,
    ffmpeg_exe: Option<&str>,
) -> Result<(), anyhow::Error> {
    let bin = ffmpeg_exe.unwrap_or("ffmpeg");

    let status = Command::new(bin)
        .args([
            "-y",
            "-ss", &format!("{:.3}", start_sec),
            "-i", input.to_str().unwrap_or_default(),
            "-t", &format!("{:.3}", duration_sec),
            "-c", "copy",
            output.to_str().unwrap_or_default(),
        ])
        .status()?;

    if !status.success() {
        return Err(anyhow::anyhow!("FFmpeg time slice extraction failed"));
    }
    Ok(())
}
