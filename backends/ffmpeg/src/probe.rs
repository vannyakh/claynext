use crate::error::{FfmpegError, Result};
use crate::process::find_executable;
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::process::Command;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Rational {
    pub num: i64,
    pub den: i64,
}

impl Rational {
    pub fn parse(s: &str) -> Option<Self> {
        let (num_str, den_str) = s.split_once('/')?;
        let num = num_str.trim().parse::<i64>().ok()?;
        let den = den_str.trim().parse::<i64>().ok()?;
        if den == 0 {
            return None;
        }
        Some(Self { num, den })
    }

    pub fn to_f64(&self) -> f64 {
        if self.den == 0 {
            0.0
        } else {
            self.num as f64 / self.den as f64
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoMetadata {
    pub width: u32,
    pub height: u32,
    pub pixel_format: String,
    pub frame_rate: Option<Rational>,
    pub avg_frame_rate: Option<Rational>,
    pub time_base: Option<Rational>,
    pub bit_rate: Option<u64>,
    pub rotation_degrees: i32,
    pub color_space: Option<String>,
    pub color_transfer: Option<String>,
    pub color_primaries: Option<String>,
    pub is_vfr: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioMetadata {
    pub sample_rate: u32,
    pub channels: u32,
    pub channel_layout: Option<String>,
    pub bit_rate: Option<u64>,
    pub bits_per_sample: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind")]
pub enum StreamKindMetadata {
    Video(VideoMetadata),
    Audio(AudioMetadata),
    Subtitle,
    Other,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamInfo {
    pub index: usize,
    pub codec_name: String,
    pub codec_long_name: Option<String>,
    pub codec_type: String, // "video", "audio", "subtitle"
    pub duration_seconds: Option<f64>,
    pub stream_details: StreamKindMetadata,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MediaInspection {
    pub filepath: String,
    pub format_name: String,
    pub format_long_name: Option<String>,
    pub duration_seconds: f64,
    pub size_bytes: u64,
    pub bit_rate: u64,
    pub streams: Vec<StreamInfo>,
}

impl MediaInspection {
    pub fn video_stream(&self) -> Option<(&StreamInfo, &VideoMetadata)> {
        for s in &self.streams {
            if let StreamKindMetadata::Video(ref v) = s.stream_details {
                return Some((s, v));
            }
        }
        None
    }

    pub fn audio_stream(&self) -> Option<(&StreamInfo, &AudioMetadata)> {
        for s in &self.streams {
            if let StreamKindMetadata::Audio(ref a) = s.stream_details {
                return Some((s, a));
            }
        }
        None
    }
}

pub fn probe_media_file(path: &Path) -> Result<MediaInspection> {
    if !path.exists() {
        return Err(FfmpegError::InvalidInput(format!(
            "File does not exist: {}",
            path.display()
        )));
    }

    let ffprobe_exe = find_executable("ffprobe").ok_or(FfmpegError::FfprobeNotFound)?;

    let output = Command::new(&ffprobe_exe)
        .args([
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path.to_str().unwrap_or_default(),
        ])
        .output()
        .map_err(FfmpegError::ProcessSpawn)?;

    if !output.status.success() {
        return Err(FfmpegError::ProcessFailed {
            exit_code: output.status.code(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        });
    }

    let val: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| FfmpegError::ProbeParse(e.to_string()))?;

    let format_obj = &val["format"];
    let duration_seconds = format_obj["duration"]
        .as_str()
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    let size_bytes = format_obj["size"]
        .as_str()
        .and_then(|s| s.parse::<u64>().ok())
        .unwrap_or(0);
    let bit_rate = format_obj["bit_rate"]
        .as_str()
        .and_then(|s| s.parse::<u64>().ok())
        .unwrap_or(0);
    let format_name = format_obj["format_name"]
        .as_str()
        .unwrap_or("unknown")
        .to_string();
    let format_long_name = format_obj["format_long_name"]
        .as_str()
        .map(|s| s.to_string());

    let mut streams = Vec::new();
    if let Some(arr) = val["streams"].as_array() {
        for s in arr {
            let index = s["index"].as_u64().unwrap_or(0) as usize;
            let codec_name = s["codec_name"].as_str().unwrap_or("unknown").to_string();
            let codec_long_name = s["codec_long_name"].as_str().map(|str_v| str_v.to_string());
            let codec_type = s["codec_type"].as_str().unwrap_or("unknown").to_string();
            let dur = s["duration"].as_str().and_then(|d| d.parse::<f64>().ok());

            let stream_details = match codec_type.as_str() {
                "video" => {
                    let width = s["width"].as_u64().unwrap_or(0) as u32;
                    let height = s["height"].as_u64().unwrap_or(0) as u32;
                    let pixel_format = s["pix_fmt"].as_str().unwrap_or("unknown").to_string();
                    let r_fps = s["r_frame_rate"].as_str().and_then(Rational::parse);
                    let avg_fps = s["avg_frame_rate"].as_str().and_then(Rational::parse);
                    let time_base = s["time_base"].as_str().and_then(Rational::parse);
                    let st_bitrate = s["bit_rate"].as_str().and_then(|b| b.parse::<u64>().ok());

                    // Parse rotation tag
                    let mut rotation = 0;
                    if let Some(tags) = s["tags"].as_object() {
                        if let Some(r_val) = tags.get("rotate").and_then(|r| r.as_str()) {
                            rotation = r_val.parse::<i32>().unwrap_or(0);
                        }
                    }

                    // VFR detection: if avg_frame_rate differs significantly from r_frame_rate
                    let is_vfr = match (&r_fps, &avg_fps) {
                        (Some(r), Some(a)) => (r.to_f64() - a.to_f64()).abs() > 0.1,
                        _ => false,
                    };

                    StreamKindMetadata::Video(VideoMetadata {
                        width,
                        height,
                        pixel_format,
                        frame_rate: r_fps,
                        avg_frame_rate: avg_fps,
                        time_base,
                        bit_rate: st_bitrate,
                        rotation_degrees: rotation,
                        color_space: s["color_space"].as_str().map(|s| s.to_string()),
                        color_transfer: s["color_transfer"].as_str().map(|s| s.to_string()),
                        color_primaries: s["color_primaries"].as_str().map(|s| s.to_string()),
                        is_vfr,
                    })
                }
                "audio" => {
                    let sample_rate = s["sample_rate"]
                        .as_str()
                        .and_then(|r| r.parse::<u32>().ok())
                        .unwrap_or(0);
                    let channels = s["channels"].as_u64().unwrap_or(0) as u32;
                    let channel_layout = s["channel_layout"].as_str().map(|l| l.to_string());
                    let st_bitrate = s["bit_rate"].as_str().and_then(|b| b.parse::<u64>().ok());
                    let bits_per_sample = s["bits_per_sample"].as_u64().map(|b| b as u32);

                    StreamKindMetadata::Audio(AudioMetadata {
                        sample_rate,
                        channels,
                        channel_layout,
                        bit_rate: st_bitrate,
                        bits_per_sample,
                    })
                }
                "subtitle" => StreamKindMetadata::Subtitle,
                _ => StreamKindMetadata::Other,
            };

            streams.push(StreamInfo {
                index,
                codec_name,
                codec_long_name,
                codec_type,
                duration_seconds: dur,
                stream_details,
            });
        }
    }

    Ok(MediaInspection {
        filepath: path.to_string_lossy().to_string(),
        format_name,
        format_long_name,
        duration_seconds,
        size_bytes,
        bit_rate,
        streams,
    })
}
