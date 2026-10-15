use crate::error::{FfmpegError, Result};
use crate::process::{find_executable, FfmpegProgress, ManagedProcess};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoEncoderConfig {
    pub codec: String, // "libx264", "libx265", "h264_nvenc", "hevc_qsv"
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub fps: Option<f32>,
    pub crf: Option<u32>,
    pub bitrate_kbps: Option<u32>,
    pub preset: String,       // "ultrafast", "medium", "slow", "p4"
    pub pixel_format: String, // "yuv420p"
}

impl Default for VideoEncoderConfig {
    fn default() -> Self {
        Self {
            codec: "libx264".to_string(),
            width: None,
            height: None,
            fps: None,
            crf: Some(22),
            bitrate_kbps: None,
            preset: "medium".to_string(),
            pixel_format: "yuv420p".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioEncoderConfig {
    pub codec: String, // "aac", "libopus", "copy"
    pub bitrate_kbps: u32,
    pub sample_rate: Option<u32>,
    pub channels: Option<u32>,
}

impl Default for AudioEncoderConfig {
    fn default() -> Self {
        Self {
            codec: "aac".to_string(),
            bitrate_kbps: 192,
            sample_rate: Some(44100),
            channels: Some(2),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportJob {
    pub input_path: PathBuf,
    pub output_path: PathBuf,
    pub video: VideoEncoderConfig,
    pub audio: AudioEncoderConfig,
    pub start_time_secs: Option<f64>,
    pub duration_secs: Option<f64>,
}

/// Check if a specific encoder name is available in the installed FFmpeg binary.
pub fn is_encoder_available(encoder_name: &str) -> bool {
    let Some(exe) = find_executable("ffmpeg") else {
        return false;
    };

    let Ok(output) = Command::new(exe)
        .args(["-v", "quiet", "-encoders"])
        .output()
    else {
        return false;
    };

    let text = String::from_utf8_lossy(&output.stdout);
    for line in text.lines() {
        if line.contains(encoder_name) {
            return true;
        }
    }
    false
}

/// Execute a complete media transcode export job with real-time progress parsing and cancellation.
pub fn run_export_job<F>(
    job: &ExportJob,
    cancel_token: Option<Arc<AtomicBool>>,
    timeout: Option<Duration>,
    mut on_progress: F,
) -> Result<()>
where
    F: FnMut(FfmpegProgress),
{
    if !job.input_path.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "Input file not found: {}",
            job.input_path.display()
        )));
    }

    if let Some(parent) = job.output_path.parent() {
        std::fs::create_dir_all(parent).map_err(FfmpegError::Io)?;
    }

    let ffmpeg_exe = find_executable("ffmpeg").ok_or(FfmpegError::FfmpegNotFound)?;

    let mut cmd = Command::new(&ffmpeg_exe);
    cmd.arg("-y").arg("-hide_banner");

    if let Some(st) = job.start_time_secs {
        cmd.args(["-ss", &format!("{:.3}", st)]);
    }

    cmd.args(["-i", job.input_path.to_str().unwrap_or_default()]);

    if let Some(dur) = job.duration_secs {
        cmd.args(["-t", &format!("{:.3}", dur)]);
    }

    // Video options
    cmd.args(["-c:v", &job.video.codec]);
    cmd.args(["-preset", &job.video.preset]);
    cmd.args(["-pix_fmt", &job.video.pixel_format]);

    if let Some(crf) = job.video.crf {
        cmd.args(["-crf", &crf.to_string()]);
    } else if let Some(br) = job.video.bitrate_kbps {
        cmd.args(["-b:v", &format!("{}k", br)]);
    }

    if let (Some(w), Some(h)) = (job.video.width, job.video.height) {
        cmd.args(["-vf", &format!("scale={}:{}", w, h)]);
    }

    if let Some(fps) = job.video.fps {
        cmd.args(["-r", &format!("{:.2}", fps)]);
    }

    // Audio options
    cmd.args(["-c:a", &job.audio.codec]);
    if job.audio.codec != "copy" {
        cmd.args(["-b:a", &format!("{}k", job.audio.bitrate_kbps)]);
        if let Some(sr) = job.audio.sample_rate {
            cmd.args(["-ar", &sr.to_string()]);
        }
        if let Some(ch) = job.audio.channels {
            cmd.args(["-ac", &ch.to_string()]);
        }
    }

    cmd.arg(job.output_path.to_str().unwrap_or_default());

    let process = ManagedProcess::spawn(cmd, cancel_token, timeout)?;
    process.wait_with_progress(&mut on_progress)?;

    if !job.output_path.is_file() {
        return Err(FfmpegError::OutputValidation(format!(
            "Export finished without producing expected file: {}",
            job.output_path.display()
        )));
    }

    Ok(())
}
