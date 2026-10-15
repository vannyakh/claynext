use std::path::Path;
use std::process::Command;

pub fn remux_replace_audio(
    video_input: &Path,
    audio_input: &Path,
    output: &Path,
    ffmpeg_exe: Option<&str>,
) -> Result<(), anyhow::Error> {
    let bin = ffmpeg_exe.unwrap_or("ffmpeg");

    let status = Command::new(bin)
        .args([
            "-y",
            "-i", video_input.to_str().unwrap_or_default(),
            "-i", audio_input.to_str().unwrap_or_default(),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output.to_str().unwrap_or_default(),
        ])
        .status()?;

    if !status.success() {
        return Err(anyhow::anyhow!("FFmpeg audio replacement remux failed"));
    }
    Ok(())
}
