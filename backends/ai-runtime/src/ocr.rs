use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrBox {
    pub text: String,
    pub confidence: f32,
    #[serde(alias = "box", default)]
    pub bbox: [f32; 4], // [x1, y1, x2, y2]
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaptionSample {
    pub time_sec: f64,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BurnedCaption {
    pub id: i32,
    pub start_sec: f64,
    pub end_sec: f64,
    pub start: String,
    pub end: String,
    pub text: String,
    pub original_text: String,
    pub translated_text: String,
    pub speaker: String,
    pub duration_sec: f64,
}

/// Merge frame readings into timed caption lines. A line must stay up at least `min_dur` seconds.
pub fn stitch_caption_samples(
    samples: &[CaptionSample],
    sample_interval: f64,
    min_dur: f64,
    similarity_thresh: f64,
) -> Vec<BurnedCaption> {
    let step = sample_interval.max(0.05);
    let mut segments: Vec<BurnedCaption> = Vec::new();
    let mut open: Option<BurnedCaption> = None;

    for sample in samples {
        let text = sample.text.split_whitespace().collect::<Vec<_>>().join(" ");
        if text.is_empty() {
            if let Some(seg) = open.take() {
                if seg.end_sec - seg.start_sec >= min_dur {
                    segments.push(seg);
                }
            }
            continue;
        }
        match open.as_mut() {
            None => {
                open = Some(new_caption(segments.len() + 1, sample.time_sec, step, &text));
            }
            Some(seg) => {
                if text_similarity(&seg.text, &text) >= similarity_thresh {
                    seg.end_sec = round3(sample.time_sec + step);
                    seg.end = sec_to_timestamp(seg.end_sec);
                    if text.chars().count() > seg.text.chars().count() {
                        seg.text = text.clone();
                        seg.original_text = text;
                    }
                } else {
                    let prev = open.take().unwrap();
                    if prev.end_sec - prev.start_sec >= min_dur {
                        segments.push(prev);
                    }
                    open = Some(new_caption(segments.len() + 1, sample.time_sec, step, &text));
                }
            }
        }
    }
    if let Some(seg) = open.take() {
        if seg.end_sec - seg.start_sec >= min_dur {
            segments.push(seg);
        }
    }
    for (i, seg) in segments.iter_mut().enumerate() {
        seg.id = i as i32 + 1;
        seg.duration_sec = round3((seg.end_sec - seg.start_sec).max(0.15));
    }
    segments
}

fn new_caption(id: usize, start: f64, step: f64, text: &str) -> BurnedCaption {
    let end = round3(start + step);
    BurnedCaption {
        id: id as i32,
        start_sec: round3(start),
        end_sec: end,
        start: sec_to_timestamp(start),
        end: sec_to_timestamp(end),
        text: text.to_string(),
        original_text: text.to_string(),
        translated_text: String::new(),
        speaker: "Speaker 1".into(),
        duration_sec: round3(step),
    }
}

pub fn sec_to_timestamp(sec: f64) -> String {
    let sec = sec.max(0.0);
    let millis = (sec.fract() * 1000.0).round() as u32;
    let mut whole = sec.floor() as u32;
    let mut millis = millis;
    if millis >= 1000 {
        whole += 1;
        millis = 0;
    }
    let hours = whole / 3600;
    let minutes = (whole % 3600) / 60;
    let seconds = whole % 60;
    format!("{hours:02}:{minutes:02}:{seconds:02}.{millis:03}")
}

fn round3(value: f64) -> f64 {
    (value * 1000.0).round() / 1000.0
}

fn text_similarity(a: &str, b: &str) -> f64 {
    let s1: Vec<char> = a.chars().filter(|c| !c.is_whitespace()).flat_map(|c| c.to_lowercase()).collect();
    let s2: Vec<char> = b.chars().filter(|c| !c.is_whitespace()).flat_map(|c| c.to_lowercase()).collect();
    if s1.is_empty() && s2.is_empty() {
        return 1.0;
    }
    if s1.is_empty() || s2.is_empty() {
        return 0.0;
    }
    if s1 == s2 {
        return 1.0;
    }
    let matched = lcs_len(&s1, &s2) as f64;
    2.0 * matched / (s1.len() + s2.len()) as f64
}

fn lcs_len(a: &[char], b: &[char]) -> usize {
    let mut prev = vec![0usize; b.len() + 1];
    let mut cur = vec![0usize; b.len() + 1];
    for i in 1..=a.len() {
        for j in 1..=b.len() {
            cur[j] = if a[i - 1] == b[j - 1] {
                prev[j - 1] + 1
            } else {
                prev[j].max(cur[j - 1])
            };
        }
        std::mem::swap(&mut prev, &mut cur);
        cur.fill(0);
    }
    prev[b.len()]
}

#[derive(Debug, Clone, Deserialize)]
pub struct CaptionScanRequest {
    pub video: String,
    pub roi: CaptionRoi,
    #[serde(default = "default_interval")]
    pub sample_interval: f64,
    #[serde(default)]
    pub start_sec: f64,
    #[serde(default)]
    pub end_sec: f64,
    #[serde(default = "default_lang")]
    pub lang: String,
    #[serde(default = "default_conf")]
    pub min_confidence: f32,
    pub reader: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CaptionRoi {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

fn default_interval() -> f64 { 0.4 }
fn default_lang() -> String { "Auto".into() }
fn default_conf() -> f32 { 0.5 }

/// Sample the capture zone and stitch burned-in captions. Progress is `(percent, message)`.
pub fn scan_burned_captions<F>(req: &CaptionScanRequest, mut progress: F) -> Result<Vec<BurnedCaption>, String>
where
    F: FnMut(i32, &str),
{
    let video = PathBuf::from(&req.video);
    if !video.is_file() {
        return Err(format!("Video file not found: {}", video.display()));
    }
    let reader = PathBuf::from(&req.reader);
    if !reader.is_file() {
        return Err("On-device subtitle reader is missing.".into());
    }
    let ffmpeg = ffmpeg_bin().ok_or_else(|| "ffmpeg was not found".to_string())?;
    let interval = req.sample_interval.clamp(0.15, 2.0);
    let duration = probe_duration(&ffmpeg, &video).unwrap_or(0.0);
    let start = req.start_sec.max(0.0);
    let mut end = if req.end_sec > 0.0 { req.end_sec } else { duration };
    if duration > 0.0 {
        end = end.min(duration);
    }
    if end <= start {
        end = start + duration.max(1.0);
    }

    progress(6, "Sampling the capture zone…");
    let dir = std::env::temp_dir().join(format!("claynext-ocr-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let pattern = dir.join("f-%06d.png");
    let filter = crop_filter(&req.roi, interval);
    let mut cmd = Command::new(&ffmpeg);
    cmd.args(["-hide_banner", "-loglevel", "error", "-y", "-i"]);
    cmd.arg(&video);
    if start > 0.05 {
        cmd.args(["-ss", &format!("{start:.3}")]);
    }
    let span = (end - start).max(interval);
    cmd.args(["-t", &format!("{span:.3}")]);
    cmd.args(["-vf", &filter, "-start_number", "0"]);
    cmd.arg(&pattern);
    let status = cmd.status().map_err(|e| e.to_string())?;
    if !status.success() {
        let _ = fs::remove_dir_all(&dir);
        return Err("Could not sample frames from the video.".into());
    }

    let mut frames: Vec<PathBuf> = fs::read_dir(&dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("png"))
        .collect();
    frames.sort();
    if frames.is_empty() {
        let _ = fs::remove_dir_all(&dir);
        return Err("No frames were sampled from the capture zone.".into());
    }

    let langs = vision_languages(&req.lang);
    let floor = req.min_confidence.clamp(0.15, 0.35);
    let total = frames.len();
    let mut samples = Vec::with_capacity(total);
    for (i, frame) in frames.iter().enumerate() {
        let t = round3(start + i as f64 * interval);
        if i % 4 == 0 || i + 1 == total {
            let pct = 8 + ((i as f64 / total as f64) * 82.0) as i32;
            progress(pct, &format!("Reading frame {}/{}", i + 1, total));
        }
        let text = read_caption(&reader, frame, floor, &langs);
        samples.push(CaptionSample { time_sec: t, text });
    }
    let _ = fs::remove_dir_all(&dir);
    progress(94, "Timing the caption lines…");
    let lines = stitch_caption_samples(&samples, interval, 0.28, 0.75);
    progress(100, &format!("Found {} subtitle lines.", lines.len()));
    Ok(lines)
}

fn crop_filter(roi: &CaptionRoi, interval: f64) -> String {
    let x = roi.x.clamp(0.0, 0.98);
    let y = roi.y.clamp(0.0, 0.98);
    let w = roi.w.clamp(0.02, 1.0 - x);
    let h = roi.h.clamp(0.02, 1.0 - y);
    format!(
        "fps=1/{interval:.3},crop=trunc(iw*{w:.4}/2)*2:trunc(ih*{h:.4}/2)*2:trunc(iw*{x:.4}/2)*2:trunc(ih*{y:.4}/2)*2,scale=-2:'if(lt(ih,96),96,ih)':flags=lanczos"
    )
}

fn vision_languages(lang: &str) -> Vec<&'static str> {
    let key = lang.to_lowercase();
    if key.contains("chinese") || key == "zh" || key.contains("zh-") {
        vec!["zh-Hans", "zh-Hant"]
    } else if key.contains("english") {
        vec!["en-US"]
    } else if key.contains("japanese") {
        vec!["ja-JP"]
    } else if key.contains("korean") {
        vec!["ko-KR"]
    } else if key.contains("vietnamese") {
        vec!["vi-VN", "en-US"]
    } else {
        vec!["zh-Hans", "zh-Hant", "en-US"]
    }
}

fn read_caption(reader: &Path, image: &Path, min_conf: f32, langs: &[&str]) -> String {
    let mut cmd = Command::new(reader);
    cmd.arg(image);
    cmd.arg(format!("{min_conf:.2}"));
    for lang in langs {
        cmd.arg(lang);
    }
    let Ok(out) = cmd.output() else { return String::new() };
    let raw = String::from_utf8_lossy(&out.stdout);
    let lines: Vec<&str> = raw.lines().map(str::trim).filter(|s| !s.is_empty()).collect();
    if lines.is_empty() {
        return String::new();
    }
    if lines.iter().all(|ln| !ln.contains(' ')) {
        lines.concat()
    } else {
        lines.join(" ")
    }
}

fn ffmpeg_bin() -> Option<PathBuf> {
    if let Ok(path) = std::env::var("CLAYNEXT_FFMPEG_PATH") {
        let p = PathBuf::from(path);
        if p.is_file() {
            return Some(p);
        }
    }
    Some(PathBuf::from("ffmpeg"))
}

fn probe_duration(ffmpeg: &Path, video: &Path) -> Option<f64> {
    let out = Command::new(ffmpeg)
        .args(["-hide_banner", "-i"])
        .arg(video)
        .output()
        .ok()?;
    let text = String::from_utf8_lossy(&out.stderr);
    let marker = text.find("Duration: ")?;
    let rest = &text[marker + "Duration: ".len()..];
    let stamp = rest.split(',').next()?.trim();
    let mut parts = stamp.split(':');
    let h: f64 = parts.next()?.parse().ok()?;
    let m: f64 = parts.next()?.parse().ok()?;
    let s: f64 = parts.next()?.parse().ok()?;
    Some(h * 3600.0 + m * 60.0 + s)
}

pub fn filter_ocr_results(boxes: &[OcrBox], min_confidence: f32) -> Vec<OcrBox> {
    boxes
        .iter()
        .filter(|b| b.confidence >= min_confidence && !b.text.trim().is_empty())
        .cloned()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_filter() {
        let boxes = vec![
            OcrBox {
                text: "Valid text".to_string(),
                confidence: 0.95,
                bbox: [0.1, 0.1, 0.5, 0.2],
            },
            OcrBox {
                text: "Noise".to_string(),
                confidence: 0.2,
                bbox: [0.1, 0.1, 0.5, 0.2],
            },
        ];
        let filtered = filter_ocr_results(&boxes, 0.5);
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].text, "Valid text");
    }

    #[test]
    fn stitch_keeps_a_line_that_holds_and_drops_a_flash() {
        let samples = vec![
            CaptionSample { time_sec: 0.0, text: "".into() },
            CaptionSample { time_sec: 0.4, text: "啊苍茫的天涯是我的爱".into() },
            CaptionSample { time_sec: 0.8, text: "啊苍茫的天涯是我的爱".into() },
            CaptionSample { time_sec: 1.2, text: "".into() },
            CaptionSample { time_sec: 1.6, text: "闪".into() },
        ];
        let lines = stitch_caption_samples(&samples, 0.4, 0.28, 0.75);
        assert_eq!(lines.len(), 2);
        assert_eq!(lines[0].text, "啊苍茫的天涯是我的爱");
        assert!((lines[0].start_sec - 0.4).abs() < 0.001);
        assert!(lines[0].end_sec >= 1.1);
        assert_eq!(lines[1].text, "闪");
    }
}
