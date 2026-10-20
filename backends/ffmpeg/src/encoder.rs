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
    // `-progress pipe:2` writes one key=value per line so the encode percent can move live.
    cmd.args([
        "-y",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-stats_period",
        "0.016",
        "-progress",
        "pipe:2",
    ]);

    if let Some(st) = job.start_time_secs {
        cmd.args(["-ss", &format!("{:.3}", st)]);
    }

    cmd.args(["-i", job.input_path.to_str().unwrap_or_default()]);

    if let Some(dur) = job.duration_secs {
        cmd.args(["-t", &format!("{:.3}", dur)]);
    }

    // Video options
    cmd.args(["-c:v", &job.video.codec]);
    // Hardware encoders use different preset namespaces; keep the requested value.
    if !job.video.preset.is_empty() {
        cmd.args(["-preset", &job.video.preset]);
    }
    cmd.args(["-pix_fmt", &job.video.pixel_format]);

    if let Some(crf) = job.video.crf {
        // NVENC/QSV/AMF prefer -cq / -qp; map CRF onto the closest portable flag.
        let codec = job.video.codec.to_ascii_lowercase();
        if codec.contains("nvenc") {
            cmd.args(["-cq", &crf.to_string()]);
        } else if codec.contains("qsv") {
            cmd.args(["-global_quality", &crf.to_string()]);
        } else if codec.contains("amf") {
            cmd.args(["-qp_i", &crf.to_string(), "-qp_p", &crf.to_string()]);
        } else {
            cmd.args(["-crf", &crf.to_string()]);
        }
    } else if let Some(br) = job.video.bitrate_kbps {
        cmd.args(["-b:v", &format!("{}k", br)]);
    }

    // Scaling: both dims = exact; one dim = keep aspect (even width/height for H.264).
    match (job.video.width, job.video.height) {
        (Some(w), Some(h)) => {
            cmd.args(["-vf", &format!("scale={}:{}", w, h)]);
        }
        (None, Some(h)) => {
            cmd.args(["-vf", &format!("scale=-2:{}", h)]);
        }
        (Some(w), None) => {
            cmd.args(["-vf", &format!("scale={}:-2", w)]);
        }
        (None, None) => {}
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

    // Qt / web players need moov at the front for progressive playback.
    let out_ext = job
        .output_path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if matches!(out_ext.as_str(), "mp4" | "m4v" | "mov") {
        cmd.args(["-movflags", "+faststart"]);
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

/// Accurate still of a normalized capture zone (0–1), for the subtitle tracker preview.
pub fn extract_crop_image(
    input: &std::path::Path,
    output: &std::path::Path,
    timestamp_secs: f64,
    x: f64,
    y: f64,
    w: f64,
    h: f64,
) -> Result<()> {
    if !input.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "Input file not found: {}",
            input.display()
        )));
    }
    if let Some(parent) = output.parent() {
        std::fs::create_dir_all(parent).map_err(FfmpegError::Io)?;
    }
    let ffmpeg_exe = find_executable("ffmpeg").ok_or(FfmpegError::FfmpegNotFound)?;
    let ts = format!("{:.3}", timestamp_secs.max(0.0));
    let x = x.clamp(0.0, 0.98);
    let y = y.clamp(0.0, 0.98);
    let w = w.clamp(0.02, 1.0 - x);
    let h = h.clamp(0.02, 1.0 - y);
    let filter = format!(
        "crop=trunc(iw*{w:.4}/2)*2:trunc(ih*{h:.4}/2)*2:trunc(iw*{x:.4}/2)*2:trunc(ih*{y:.4}/2)*2"
    );
    let mut cmd = Command::new(&ffmpeg_exe);
    cmd.args(["-y", "-hide_banner", "-loglevel", "error"]);
    // -ss after -i so the still is the playhead frame, not the previous keyframe.
    cmd.args(["-i", input.to_str().unwrap_or_default()]);
    cmd.args(["-ss", &ts, "-frames:v", "1", "-vf", &filter]);
    cmd.arg(output.to_str().unwrap_or_default());
    let status = cmd.status().map_err(FfmpegError::ProcessSpawn)?;
    if !status.success() || !output.is_file() {
        return Err(FfmpegError::OutputValidation(format!(
            "Crop extraction failed for {}",
            output.display()
        )));
    }
    Ok(())
}

/// Extract a single JPEG/PNG still for library thumbnails and timeline posters.
pub fn extract_still_image(
    input: &std::path::Path,
    output: &std::path::Path,
    timestamp_secs: f64,
    max_width: Option<u32>,
) -> Result<()> {
    if !input.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "Input file not found: {}",
            input.display()
        )));
    }
    if let Some(parent) = output.parent() {
        std::fs::create_dir_all(parent).map_err(FfmpegError::Io)?;
    }

    let ffmpeg_exe = find_executable("ffmpeg").ok_or(FfmpegError::FfmpegNotFound)?;
    let ts = format!("{:.3}", timestamp_secs.max(0.0));

    let mut cmd = Command::new(&ffmpeg_exe);
    cmd.args(["-y", "-hide_banner", "-loglevel", "error"]);
    // Fast seek before demux for preview/thumbnail latency.
    cmd.args(["-ss", &ts]);
    cmd.args(["-i", input.to_str().unwrap_or_default()]);
    cmd.args(["-frames:v", "1"]);
    if let Some(w) = max_width {
        cmd.args([
            "-vf",
            &format!("scale={}:-1:force_original_aspect_ratio=decrease", w),
        ]);
    }
    cmd.args(["-q:v", "4"]);
    cmd.arg(output.to_str().unwrap_or_default());

    let status = cmd.status().map_err(FfmpegError::ProcessSpawn)?;
    if !status.success() || !output.is_file() {
        return Err(FfmpegError::OutputValidation(format!(
            "Still extraction failed for {}",
            output.display()
        )));
    }
    Ok(())
}
