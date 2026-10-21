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

    // imageio-ffmpeg ships ffmpeg only. A missing ffprobe must not fail the probe.
    if let Some(ffprobe_exe) = find_executable("ffprobe") {
        match probe_with_ffprobe(path, &ffprobe_exe) {
            Ok(info) => return Ok(info),
            Err(err) => {
                if find_executable("ffmpeg").is_some() {
                    if let Ok(info) = probe_with_ffmpeg_banner(path) {
                        return Ok(info);
                    }
                }
                return Err(err);
            }
        }
    }
    probe_with_ffmpeg_banner(path)
}

fn probe_with_ffprobe(path: &Path, ffprobe_exe: &Path) -> Result<MediaInspection> {
    let output = Command::new(ffprobe_exe)
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

fn probe_with_ffmpeg_banner(path: &Path) -> Result<MediaInspection> {
    let ffmpeg_exe = find_executable("ffmpeg").ok_or(FfmpegError::FfmpegNotFound)?;
    let output = Command::new(&ffmpeg_exe)
        .args(["-hide_banner", "-nostdin", "-i"])
        .arg(path)
        .output()
        .map_err(FfmpegError::ProcessSpawn)?;
    let mut text = String::from_utf8_lossy(&output.stderr).into_owned();
    if !text.contains("Duration:") && !text.contains("Stream #") {
        text.push_str(&String::from_utf8_lossy(&output.stdout));
    }
    let size_bytes = std::fs::metadata(path).map(|meta| meta.len()).unwrap_or(0);
    inspection_from_banner(path, &text, size_bytes)
}

pub(crate) fn inspection_from_banner(path: &Path, text: &str, size_bytes: u64) -> Result<MediaInspection> {
    if !text.contains("Duration:") && !text.contains("Stream #") {
        return Err(FfmpegError::ProbeParse(
            "ffmpeg -i produced no media banner".into(),
        ));
    }

    let format_name = text
        .lines()
        .find_map(|line| {
            let rest = line.split_once("Input #")?.1;
            let rest = rest.split_once(',')?.1;
            let name = rest.split(", from").next()?.trim();
            if name.is_empty() { None } else { Some(name.to_string()) }
        })
        .unwrap_or_else(|| "unknown".to_string());

    let duration_seconds = text.lines().find_map(parse_duration_clock).unwrap_or(0.0);
    let bit_rate = text
        .lines()
        .find_map(|line| {
            let kbps = capture_after(line, "bitrate:")?;
            kbps_to_bps(kbps)
        })
        .unwrap_or(0);

    let mut streams = Vec::new();
    let mut rotation = 0;
    if let Some(value) = capture_tag(text, "rotate") {
        rotation = value.parse::<i32>().unwrap_or(0);
    }

    for line in text.lines() {
        let Some((index, kind, payload)) = parse_stream_line(line) else {
            continue;
        };
        let fields = split_csv(payload);
        if fields.is_empty() {
            continue;
        }
        let codec_name = first_token(&fields[0]);
        let stream_details = match kind {
            "video" => {
                let mut width = 0u32;
                let mut height = 0u32;
                let mut pixel_format = "yuv420p".to_string();
                let mut fps = 0.0f64;
                let mut tbr = 0.0f64;
                let mut stream_rate = None;
                for field in fields.iter().skip(1) {
                    if let Some((w, h)) = capture_size(field) {
                        if width == 0 {
                            width = w;
                            height = h;
                        }
                    }
                    if let Some(value) = capture_number_unit(field, "fps") {
                        fps = value;
                    }
                    if let Some(value) = capture_number_unit(field, "tbr") {
                        tbr = value;
                    }
                    if let Some(bps) = kbps_to_bps(field) {
                        stream_rate = Some(bps);
                    }
                    let token = first_token(field).to_ascii_lowercase();
                    if is_pixel_format(&token) {
                        pixel_format = token;
                    }
                }
                let rate = if fps > 0.0 { fps } else { tbr };
                StreamKindMetadata::Video(VideoMetadata {
                    width,
                    height,
                    pixel_format,
                    frame_rate: fps_rational(rate),
                    avg_frame_rate: fps_rational(if tbr > 0.0 { tbr } else { rate }),
                    time_base: None,
                    bit_rate: stream_rate,
                    rotation_degrees: rotation,
                    color_space: None,
                    color_transfer: None,
                    color_primaries: None,
                    is_vfr: fps > 0.0 && tbr > 0.0 && (fps - tbr).abs() > 0.1,
                })
            }
            "audio" => {
                let mut sample_rate = 0u32;
                let mut channels = 2u32;
                let mut channel_layout = Some("stereo".to_string());
                let mut stream_rate = None;
                for field in fields.iter().skip(1) {
                    if let Some(hz) = capture_number_unit(field, "Hz") {
                        sample_rate = hz.round() as u32;
                    }
                    if let Some(bps) = kbps_to_bps(field) {
                        stream_rate = Some(bps);
                    }
                    if is_channel_field(field) {
                        let (count, layout) = channel_count(field);
                        channels = count;
                        channel_layout = Some(layout);
                    }
                }
                StreamKindMetadata::Audio(AudioMetadata {
                    sample_rate,
                    channels,
                    channel_layout,
                    bit_rate: stream_rate,
                    bits_per_sample: None,
                })
            }
            "subtitle" => StreamKindMetadata::Subtitle,
            _ => StreamKindMetadata::Other,
        };
        streams.push(StreamInfo {
            index,
            codec_name,
            codec_long_name: None,
            codec_type: kind.to_string(),
            duration_seconds: if duration_seconds > 0.0 {
                Some(duration_seconds)
            } else {
                None
            },
            stream_details,
        });
    }

    if duration_seconds <= 0.0 && streams.is_empty() {
        return Err(FfmpegError::ProbeParse(
            "ffmpeg -i banner had no duration or streams".into(),
        ));
    }

    Ok(MediaInspection {
        filepath: path.to_string_lossy().to_string(),
        format_name,
        format_long_name: None,
        duration_seconds,
        size_bytes,
        bit_rate,
        streams,
    })
}

fn parse_duration_clock(line: &str) -> Option<f64> {
    let rest = line.split_once("Duration:")?.1.trim();
    let clock = rest.split([',', ' ']).next()?.trim();
    let mut parts = clock.split(':');
    let hours: f64 = parts.next()?.parse().ok()?;
    let minutes: f64 = parts.next()?.parse().ok()?;
    let seconds: f64 = parts.next()?.parse().ok()?;
    Some(hours * 3600.0 + minutes * 60.0 + seconds)
}

fn parse_stream_line(line: &str) -> Option<(usize, &'static str, &str)> {
    let rest = line.trim().strip_prefix("Stream #")?;
    let (_program, after_program) = rest.split_once(':')?;
    let index_digits: String = after_program
        .chars()
        .take_while(|ch| ch.is_ascii_digit())
        .collect();
    if index_digits.is_empty() {
        return None;
    }
    let index: usize = index_digits.parse().ok()?;
    let after_index = &after_program[index_digits.len()..];
    let payload = after_index.split_once(':')?.1.trim();
    let (kind, body) = if let Some(body) = payload.strip_prefix("Video:") {
        ("video", body.trim())
    } else if let Some(body) = payload.strip_prefix("Audio:") {
        ("audio", body.trim())
    } else if let Some(body) = payload.strip_prefix("Subtitle:") {
        ("subtitle", body.trim())
    } else {
        return None;
    };
    Some((index, kind, body))
}

fn split_csv(payload: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut buf = String::new();
    let mut depth = 0i32;
    for ch in payload.chars() {
        match ch {
            '(' => {
                depth += 1;
                buf.push(ch);
            }
            ')' => {
                depth = (depth - 1).max(0);
                buf.push(ch);
            }
            ',' if depth == 0 => {
                fields.push(buf.trim().to_string());
                buf.clear();
            }
            _ => buf.push(ch),
        }
    }
    if !buf.trim().is_empty() {
        fields.push(buf.trim().to_string());
    }
    fields
}

fn first_token(field: &str) -> String {
    field
        .split(|ch: char| ch.is_whitespace() || ch == '(')
        .find(|part| !part.is_empty())
        .unwrap_or("unknown")
        .to_string()
}

fn is_pixel_format(token: &str) -> bool {
    const PREFIXES: [&str; 8] = ["yuv", "rgb", "bgr", "gray", "gbr", "nv", "pal", "ya"];
    PREFIXES.iter().any(|prefix| token.starts_with(prefix)) || token.starts_with("mono")
}

fn capture_size(field: &str) -> Option<(u32, u32)> {
    let (w, h) = field.split_once('x')?;
    let width: u32 = w
        .chars()
        .rev()
        .take_while(|ch| ch.is_ascii_digit())
        .collect::<String>()
        .chars()
        .rev()
        .collect::<String>()
        .parse()
        .ok()?;
    let height: u32 = h
        .chars()
        .take_while(|ch| ch.is_ascii_digit())
        .collect::<String>()
        .parse()
        .ok()?;
    if width < 16 || height < 16 {
        return None;
    }
    Some((width, height))
}

fn capture_number_unit(field: &str, unit: &str) -> Option<f64> {
    let tokens: Vec<&str> = field
        .split_whitespace()
        .map(|token| token.trim_end_matches(','))
        .collect();
    for (index, token) in tokens.iter().enumerate() {
        if *token == unit && index > 0 {
            return tokens[index - 1].parse::<f64>().ok();
        }
        if let Some(number) = token.strip_suffix(unit) {
            if !number.is_empty() {
                return number.trim().parse::<f64>().ok();
            }
        }
    }
    None
}

fn kbps_to_bps(field: &str) -> Option<u64> {
    let kbps = capture_number_unit(field, "kb/s")?;
    Some((kbps * 1000.0).round() as u64)
}

fn capture_after<'a>(line: &'a str, label: &str) -> Option<&'a str> {
    let rest = line.split_once(label)?.1.trim();
    Some(rest.split(',').next()?.trim())
}

fn capture_tag<'a>(text: &'a str, name: &str) -> Option<&'a str> {
    for line in text.lines() {
        let Some(rest) = line.trim().strip_prefix(name) else {
            continue;
        };
        let Some(rest) = rest.trim().strip_prefix(':') else {
            continue;
        };
        let rest = rest.trim();
        if !rest.is_empty() {
            return rest.split_whitespace().next();
        }
    }
    None
}

fn fps_rational(fps: f64) -> Option<Rational> {
    if fps <= 0.0 {
        return None;
    }
    if (fps - fps.round()).abs() < 0.001 {
        Some(Rational {
            num: fps.round() as i64,
            den: 1,
        })
    } else {
        Some(Rational {
            num: (fps * 1000.0).round() as i64,
            den: 1000,
        })
    }
}

fn is_channel_field(field: &str) -> bool {
    let head = field
        .split('(')
        .next()
        .unwrap_or(field)
        .trim()
        .to_ascii_lowercase();
    matches!(
        head.as_str(),
        "mono" | "stereo" | "2.1" | "3.0" | "4.0" | "quad" | "5.0" | "5.1" | "6.1" | "7.1"
    ) || head.contains("channel")
}

fn channel_count(field: &str) -> (u32, String) {
    let layout = field.trim().to_string();
    let head = layout
        .split('(')
        .next()
        .unwrap_or(&layout)
        .trim()
        .to_ascii_lowercase();
    let count = match head.as_str() {
        "mono" => 1,
        "stereo" => 2,
        "2.1" => 3,
        "3.0" => 3,
        "4.0" | "quad" => 4,
        "5.0" => 5,
        "5.1" => 6,
        "6.1" => 7,
        "7.1" => 8,
        _ => head
            .split_whitespace()
            .next()
            .and_then(|part| part.parse::<u32>().ok())
            .filter(|_| head.contains("channel"))
            .unwrap_or(2),
    };
    (count, layout)
}

#[cfg(test)]
mod tests {
    use super::*;

    const BANNER: &str = "\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'episode.mp4':
  Duration: 00:05:12.34, start: 0.000000, bitrate: 1523 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709), 1920x1080 [SAR 1:1 DAR 16:9], 1390 kb/s, 24 fps, 24 tbr, 12288 tbn
    Metadata:
      rotate          : 90
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 128 kb/s
";

    #[test]
    fn banner_reads_video_and_audio_without_ffprobe() {
        let info = inspection_from_banner(Path::new("episode.mp4"), BANNER, 42).unwrap();
        assert_eq!(info.format_name, "mov,mp4,m4a,3gp,3g2,mj2");
        assert!((info.duration_seconds - 312.34).abs() < 0.01);
        assert_eq!(info.bit_rate, 1_523_000);
        let (_, video) = info.video_stream().unwrap();
        assert_eq!(video.width, 1920);
        assert_eq!(video.height, 1080);
        assert_eq!(video.pixel_format, "yuv420p");
        assert_eq!(video.rotation_degrees, 90);
        assert_eq!(info.streams[0].codec_name, "h264");
        let (_, audio) = info.audio_stream().unwrap();
        assert_eq!(audio.sample_rate, 48000);
        assert_eq!(audio.channels, 2);
        assert_eq!(info.streams[1].codec_name, "aac");
    }

    #[test]
    fn banner_reads_wav_channel_count() {
        let text = "\
Input #0, wav, from 'voice.wav':
  Duration: 00:00:03.20, bitrate: 1536 kb/s
  Stream #0:0: Audio: pcm_s16le ([1][0][0][0] / 0x0001), 48000 Hz, 2 channels, s16, 1536 kb/s
";
        let info = inspection_from_banner(Path::new("voice.wav"), text, 10).unwrap();
        let (_, audio) = info.audio_stream().unwrap();
        assert_eq!(audio.channels, 2);
        assert_eq!(audio.sample_rate, 48000);
        assert!(info.video_stream().is_none());
    }
}
