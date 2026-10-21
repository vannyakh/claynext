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
    /// `auto` picks VideoToolbox on macOS and NVENC / QSV / AMF / Media Foundation on Windows.
    pub video_codec: String,
    /// Trim both inputs to this window, in seconds. Video uses it as `-ss`/`-t`.
    pub start_seconds: Option<f64>,
    pub duration_seconds: Option<f64>,
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
            video_codec: "auto".into(),
            start_seconds: None,
            duration_seconds: None,
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
        "-stats_period",
        "0.016",
        "-progress",
        "pipe:2",
    ]);

    if let Some(start) = options.start_seconds {
        if start > 0.0 {
            cmd.args(["-ss", &format!("{:.3}", start)]);
        }
    }
    if let Some(dur) = options.duration_seconds {
        if dur > 0.0 {
            cmd.args(["-t", &format!("{:.3}", dur)]);
        }
    }
    // Video input (0)
    cmd.args(["-i", video_input.to_str().unwrap_or_default()]);

    // Audio input (1). The mix is already the master window, so it is not seeked.
    if let Some(delay) = options.audio_delay_seconds {
        if delay != 0.0 {
            cmd.args(["-itsoffset", &format!("{:.3}", delay)]);
        }
    }
    cmd.args(["-i", audio_input.to_str().unwrap_or_default()]);

    // A canvas graph (split / overlay / labels) is not a `-vf` chain. `-vf` drops
    // it, so the encode stayed the source frame while the preview showed the canvas.
    let copy_video = options.copy_video && options.video_filter.is_empty();
    match classify_video_filter(&options.video_filter) {
        AppliedFilter::None => {
            cmd.args(["-map", "0:v:0", "-map", "1:a:0"]);
        }
        AppliedFilter::Simple(chain) => {
            cmd.args(["-map", "0:v:0", "-map", "1:a:0", "-vf", &chain]);
        }
        AppliedFilter::Graph(graph) => {
            cmd.args(["-filter_complex", &graph, "-map", "[vout]", "-map", "1:a:0"]);
        }
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
        let codec = if options.video_codec.trim().is_empty()
            || matches!(options.video_codec.as_str(), "auto" | "best")
        {
            crate::encoder::best_platform_codec()
        } else {
            options.video_codec.clone()
        };
        cmd.args(crate::encoder::video_encoder_args(
            &codec,
            options.video_crf,
            preset,
        ));
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

/// How a preview filter string is applied. Graphs need `-filter_complex`.
enum AppliedFilter {
    None,
    Simple(String),
    Graph(String),
}

fn classify_video_filter(filter: &str) -> AppliedFilter {
    let filter = filter.trim();
    if filter.is_empty() {
        return AppliedFilter::None;
    }
    if filter.contains(';') || filter.contains('[') {
        AppliedFilter::Graph(link_filter_graph(filter))
    } else {
        AppliedFilter::Simple(filter.to_string())
    }
}

/// Bind input 0's video and label the graph output `[vout]` for `-map`.
fn link_filter_graph(filter: &str) -> String {
    let linked = if filter.starts_with('[') {
        filter.to_string()
    } else {
        format!("[0:v]{filter}")
    };
    if linked.contains("[vout]") {
        linked
    } else {
        format!("{linked}[vout]")
    }
}

#[cfg(test)]
mod tests {
    use super::classify_video_filter;

    #[test]
    fn a_grade_chain_stays_on_vf() {
        match classify_video_filter("eq=contrast=1.2:saturation=0.85") {
            super::AppliedFilter::Simple(chain) => assert!(chain.starts_with("eq=")),
            _ => panic!("grade chain should stay a simple filter"),
        }
    }

    #[test]
    fn a_canvas_graph_is_mapped_as_vout() {
        let graph = "split[a][b];[a]scale=16:16[bg];[b]scale=8:8[fg];[bg][fg]overlay=0:0,format=yuv420p";
        match classify_video_filter(graph) {
            super::AppliedFilter::Graph(linked) => {
                assert!(linked.starts_with("[0:v]split"));
                assert!(linked.ends_with("[vout]"));
                assert!(!linked.contains("-vf"));
            }
            _ => panic!("canvas graph should use filter_complex"),
        }
    }
}
