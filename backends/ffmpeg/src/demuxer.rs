use crate::error::{FfmpegError, Result};
use crate::process::find_executable;
use std::path::Path;
use std::process::Command;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreamSelector {
    FirstVideo,
    FirstAudio,
    FirstSubtitle,
    Index(usize),
}

impl StreamSelector {
    pub fn to_map_specifier(&self) -> String {
        match self {
            StreamSelector::FirstVideo => "0:v:0".to_string(),
            StreamSelector::FirstAudio => "0:a:0".to_string(),
            StreamSelector::FirstSubtitle => "0:s:0".to_string(),
            StreamSelector::Index(idx) => format!("0:{}", idx),
        }
    }
}

/// Extract a single stream into an output file without re-encoding (stream-copy).
pub fn extract_stream_copy(
    input: &Path,
    output: &Path,
    selector: StreamSelector,
    start_secs: Option<f64>,
    duration_secs: Option<f64>,
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

    let mut cmd = Command::new(&ffmpeg_exe);
    cmd.arg("-y").arg("-v").arg("error");

    if let Some(st) = start_secs {
        cmd.args(["-ss", &format!("{:.3}", st)]);
    }

    cmd.args(["-i", input.to_str().unwrap_or_default()]);

    if let Some(dur) = duration_secs {
        cmd.args(["-t", &format!("{:.3}", dur)]);
    }

    let map_spec = selector.to_map_specifier();
    cmd.args(["-map", &map_spec]);
    cmd.args(["-c", "copy"]);
    cmd.args(["-avoid_negative_ts", "make_zero"]);
    cmd.arg(output.to_str().unwrap_or_default());

    let status = cmd.status().map_err(FfmpegError::ProcessSpawn)?;
    if !status.success() {
        return Err(FfmpegError::ProcessFailed {
            exit_code: status.code(),
            stderr: "Stream copy extraction failed".into(),
        });
    }

    if !output.is_file() {
        return Err(FfmpegError::OutputValidation(format!(
            "Demux output not created: {}",
            output.display()
        )));
    }

    Ok(())
}
