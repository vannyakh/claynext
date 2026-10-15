//! editor-render: Render job configuration and command orchestrator.

use serde::{Deserialize, Serialize};

/// Export container format and codec settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RenderProfile {
    pub output_path: String,
    pub width: u32,
    pub height: u32,
    pub fps_num: i64,
    pub fps_den: i64,
    pub video_codec: String, // e.g. "libx264", "hevc_nvenc", "hevc_qsv", "hevc_amf"
    pub video_bitrate_kbps: u32,
    pub crf: Option<u32>,
    pub preset: String,          // "fast", "medium", "slow", "p4"
    pub audio_codec: String,     // "aac"
    pub audio_bitrate_kbps: u32, // 192, 320
}

impl Default for RenderProfile {
    fn default() -> Self {
        Self {
            output_path: "output.mp4".to_string(),
            width: 1920,
            height: 1080,
            fps_num: 30,
            fps_den: 1,
            video_codec: "libx264".to_string(),
            video_bitrate_kbps: 6000,
            crf: Some(21),
            preset: "medium".to_string(),
            audio_codec: "aac".to_string(),
            audio_bitrate_kbps: 192,
        }
    }
}

/// Render progress updates parsed from ffmpeg progress pipes.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RenderProgress {
    pub frame: u64,
    pub fps: f32,
    pub time_seconds: f64,
    pub percentage: f32,
    pub speed: f32,
}

/// Parse standard FFmpeg progress line key=value.
pub fn parse_ffmpeg_progress_line(
    line: &str,
    total_duration_seconds: f64,
    out: &mut RenderProgress,
) {
    let parts: Vec<&str> = line.trim().split('=').collect();
    if parts.len() == 2 {
        let key = parts[0];
        let val = parts[1];
        match key {
            "frame" => {
                if let Ok(f) = val.parse::<u64>() {
                    out.frame = f;
                }
            }
            "fps" => {
                if let Ok(f) = val.parse::<f32>() {
                    out.fps = f;
                }
            }
            "out_time_ms" => {
                if let Ok(us) = val.parse::<i64>() {
                    out.time_seconds = us as f64 / 1_000_000.0;
                    if total_duration_seconds > 0.0 {
                        out.percentage = ((out.time_seconds / total_duration_seconds) * 100.0)
                            .clamp(0.0, 100.0) as f32;
                    }
                }
            }
            "speed" => {
                let clean = val.trim_end_matches('x');
                if let Ok(s) = clean.parse::<f32>() {
                    out.speed = s;
                }
            }
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_progress_parsing() {
        let mut prog = RenderProgress {
            frame: 0,
            fps: 0.0,
            time_seconds: 0.0,
            percentage: 0.0,
            speed: 0.0,
        };
        parse_ffmpeg_progress_line("frame=120", 10.0, &mut prog);
        assert_eq!(prog.frame, 120);

        parse_ffmpeg_progress_line("out_time_ms=5000000", 10.0, &mut prog);
        assert_eq!(prog.time_seconds, 5.0);
        assert_eq!(prog.percentage, 50.0);
    }
}
