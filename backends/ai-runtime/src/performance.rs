//! Dialogue performance: per-line prosody features and the delivery plan that
//! sits between translation and TTS.
//!
//! Prosody is acoustic only (energy, pitch, voicing). It never claims a
//! speaker's sex, age, or identity; the planner only uses it relative to the
//! same speaker's other lines.

use serde::{Deserialize, Serialize};

use crate::translation::{pace_rate, spoken_units};

/// Styles the planner and the editor share. One label per line.
pub const STYLES: [&str; 9] = [
    "neutral",
    "happy",
    "sad",
    "angry",
    "fearful",
    "whispering",
    "shouting",
    "crying",
    "laughing",
];

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProsodySpan {
    #[serde(default)]
    pub index: usize,
    pub start_sec: f64,
    pub end_sec: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct ProsodyFeatures {
    pub index: usize,
    pub start_sec: f64,
    pub end_sec: f64,
    pub duration_sec: f64,
    /// Mean RMS of the span in dBFS.
    pub rms_db: f32,
    pub peak_db: f32,
    /// Span loudness against the median voiced frame of the whole track.
    pub loudness_rel_db: f32,
    /// Median F0 of voiced frames, 0 when nothing was voiced.
    pub pitch_hz: f32,
    /// p90 - p10 of voiced F0 in semitones.
    pub pitch_range_st: f32,
    pub voiced_ratio: f32,
    /// Share of the span below the track speech floor.
    pub pause_ratio: f32,
    pub confidence: f32,
}

const FRAME_SEC: f64 = 0.04;
const MAX_PITCH_FRAMES: usize = 32;
const F0_MIN: f32 = 70.0;
const F0_MAX: f32 = 420.0;

/// Energy, pitch, and voicing for each span of a mono PCM track.
pub fn analyze_prosody(samples: &[f32], sample_rate: u32, spans: &[ProsodySpan]) -> Vec<ProsodyFeatures> {
    if sample_rate == 0 {
        return Vec::new();
    }
    let frame = ((sample_rate as f64) * FRAME_SEC) as usize;
    let frame = frame.max(16);
    let track_rms = frame_rms(samples, frame);
    let (floor, median_voiced) = track_levels(&track_rms);

    spans
        .iter()
        .map(|span| {
            let start = ((span.start_sec.max(0.0)) * sample_rate as f64) as usize;
            let end = ((span.end_sec.max(span.start_sec)) * sample_rate as f64) as usize;
            let start = start.min(samples.len());
            let end = end.min(samples.len());
            let chunk = &samples[start..end];
            features_for(chunk, sample_rate, frame, floor, median_voiced, span)
        })
        .collect()
}

fn features_for(
    chunk: &[f32],
    sample_rate: u32,
    frame: usize,
    floor: f32,
    median_voiced: f32,
    span: &ProsodySpan,
) -> ProsodyFeatures {
    let duration = (span.end_sec - span.start_sec).max(0.0);
    let mut out = ProsodyFeatures {
        index: span.index,
        start_sec: span.start_sec,
        end_sec: span.end_sec,
        duration_sec: duration,
        rms_db: -90.0,
        peak_db: -90.0,
        ..Default::default()
    };
    if chunk.len() < frame {
        return out;
    }
    let rms = frame_rms(chunk, frame);
    let mean_energy = rms.iter().map(|r| r * r).sum::<f32>() / rms.len().max(1) as f32;
    out.rms_db = to_db(mean_energy.sqrt());
    out.peak_db = to_db(chunk.iter().fold(0.0f32, |m, s| m.max(s.abs())));
    out.loudness_rel_db = out.rms_db - to_db(median_voiced);
    let quiet = rms.iter().filter(|r| **r < floor).count();
    out.pause_ratio = quiet as f32 / rms.len() as f32;

    let loud: Vec<usize> = (0..rms.len()).filter(|i| rms[*i] >= floor).collect();
    let step = (loud.len() / MAX_PITCH_FRAMES).max(1);
    let mut pitches: Vec<f32> = Vec::new();
    let mut tried = 0usize;
    for &i in loud.iter().step_by(step) {
        tried += 1;
        let from = i * frame;
        let to = (from + frame).min(chunk.len());
        if let Some(f0) = frame_pitch(&chunk[from..to], sample_rate) {
            pitches.push(f0);
        }
    }
    out.voiced_ratio = if rms.is_empty() {
        0.0
    } else {
        let voiced_share = if tried == 0 { 0.0 } else { pitches.len() as f32 / tried as f32 };
        voiced_share * (loud.len() as f32 / rms.len() as f32)
    };
    if !pitches.is_empty() {
        pitches.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        out.pitch_hz = pitches[pitches.len() / 2];
        let lo = pitches[(pitches.len() - 1) * 10 / 100];
        let hi = pitches[(pitches.len() - 1) * 90 / 100];
        out.pitch_range_st = if lo > 0.0 { 12.0 * (hi / lo).log2() } else { 0.0 };
    }
    let frames_ok = (rms.len() as f32 / 8.0).min(1.0);
    let voiced_ok = (pitches.len() as f32 / 6.0).min(1.0);
    out.confidence = round3(0.35 + 0.35 * frames_ok + 0.30 * voiced_ok);
    out.rms_db = round3(out.rms_db);
    out.peak_db = round3(out.peak_db);
    out.loudness_rel_db = round3(out.loudness_rel_db);
    out.pitch_hz = round3(out.pitch_hz);
    out.pitch_range_st = round3(out.pitch_range_st);
    out.voiced_ratio = round3(out.voiced_ratio);
    out.pause_ratio = round3(out.pause_ratio);
    out
}

/// Normalized autocorrelation F0 for one frame, None when unvoiced.
fn frame_pitch(frame: &[f32], sample_rate: u32) -> Option<f32> {
    let n = frame.len();
    let min_lag = (sample_rate as f32 / F0_MAX).floor() as usize;
    let max_lag = ((sample_rate as f32 / F0_MIN).ceil() as usize).min(n.saturating_sub(n / 4));
    if min_lag < 2 || max_lag <= min_lag {
        return None;
    }
    let mean = frame.iter().sum::<f32>() / n as f32;
    let x: Vec<f32> = frame.iter().map(|s| s - mean).collect();
    let energy: f32 = x.iter().map(|s| s * s).sum();
    if energy <= 1e-6 {
        return None;
    }
    let mut scores: Vec<f32> = Vec::with_capacity(max_lag - min_lag + 1);
    for lag in min_lag..=max_lag {
        let mut num = 0.0f32;
        let mut e1 = 0.0f32;
        let mut e2 = 0.0f32;
        for i in 0..(n - lag) {
            num += x[i] * x[i + lag];
            e1 += x[i] * x[i];
            e2 += x[i + lag] * x[i + lag];
        }
        let denom = (e1 * e2).sqrt();
        scores.push(if denom <= 1e-9 { 0.0 } else { num / denom });
    }
    let best = scores.iter().cloned().fold(0.0f32, f32::max);
    if best < 0.5 {
        return None;
    }
    // Multiples of the period score almost as high; the first near-max peak is F0.
    for (k, r) in scores.iter().enumerate() {
        let left = if k > 0 { scores[k - 1] } else { f32::MIN };
        let right = scores.get(k + 1).copied().unwrap_or(f32::MIN);
        if *r >= best * 0.9 && *r >= left && *r >= right {
            return Some(sample_rate as f32 / (min_lag + k) as f32);
        }
    }
    None
}

fn frame_rms(samples: &[f32], frame: usize) -> Vec<f32> {
    let mut out = Vec::with_capacity(samples.len() / frame.max(1));
    let mut i = 0;
    while frame > 0 && i + frame <= samples.len() {
        let chunk = &samples[i..i + frame];
        out.push((chunk.iter().map(|s| s * s).sum::<f32>() / frame as f32).sqrt());
        i += frame;
    }
    out
}

/// Speech floor and median voiced frame level of the whole track.
fn track_levels(rms: &[f32]) -> (f32, f32) {
    if rms.is_empty() {
        return (0.008, 0.05);
    }
    let mut sorted = rms.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let noise = sorted[(sorted.len() - 1) * 20 / 100];
    let peak = sorted[(sorted.len() - 1) * 95 / 100].max(noise + 1e-4);
    let floor = (noise + (peak - noise) * 0.08).max(0.004);
    let voiced: Vec<f32> = sorted.iter().copied().filter(|r| *r >= floor).collect();
    let median = if voiced.is_empty() { peak } else { voiced[voiced.len() / 2] };
    (floor, median.max(1e-4))
}

fn to_db(v: f32) -> f32 {
    20.0 * v.max(1e-5).log10()
}

fn round3(v: f32) -> f32 {
    (v * 1000.0).round() / 1000.0
}

fn round3d(v: f64) -> f64 {
    (v * 1000.0).round() / 1000.0
}

// ── Performance plan ─────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PerformanceLine {
    #[serde(default)]
    pub index: usize,
    /// Translated line as it will be spoken. Never rewritten here.
    #[serde(default)]
    pub text: String,
    #[serde(default)]
    pub source_text: String,
    #[serde(default)]
    pub start_sec: f64,
    #[serde(default)]
    pub end_sec: f64,
    #[serde(default)]
    pub speaker: String,
    /// Existing cue label from text rules or the LLM analyst.
    #[serde(default)]
    pub expression: String,
    /// Where `expression` came from: llm, text, intent, manual.
    #[serde(default)]
    pub expression_source: String,
    #[serde(default)]
    pub intent: String,
    /// Editor-set style; wins when `manual` is true.
    #[serde(default)]
    pub style: String,
    #[serde(default)]
    pub intensity: Option<f32>,
    #[serde(default)]
    pub manual: bool,
    #[serde(default)]
    pub prosody: Option<ProsodyFeatures>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PerformanceRequest {
    #[serde(default)]
    pub lang: String,
    /// Known character names for pronunciation hints.
    #[serde(default)]
    pub names: Vec<String>,
    #[serde(default)]
    pub lines: Vec<PerformanceLine>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PronunciationHint {
    pub text: String,
    pub kind: String,
    pub hint: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PlanConfidence {
    pub emotion: f32,
    pub intensity: f32,
    pub timing: f32,
    pub overall: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LinePlan {
    pub index: usize,
    pub style: String,
    pub emotion: String,
    pub delivery: String,
    pub intensity: f32,
    pub source: String,
    pub target_duration_sec: f64,
    pub speech_sec: f64,
    pub pause_before_sec: f64,
    pub pause_after_sec: f64,
    pub internal_pause_sec: f64,
    pub units: i32,
    pub natural_units_per_sec: f64,
    pub needed_units_per_sec: f64,
    pub rate_ratio: f64,
    pub tempo_min: f32,
    pub tempo_max: f32,
    pub pronunciation: Vec<PronunciationHint>,
    pub confidence: PlanConfidence,
    pub evidence: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PerformancePlan {
    pub version: u32,
    pub lines: Vec<LinePlan>,
}

/// Emotion and delivery descriptors for a style label.
pub fn style_parts(style: &str) -> (&'static str, &'static str) {
    match style {
        "happy" => ("happy", "normal"),
        "sad" => ("sad", "normal"),
        "angry" => ("angry", "normal"),
        "fearful" => ("fearful", "normal"),
        "whispering" => ("neutral", "whispering"),
        "shouting" => ("angry", "shouting"),
        "crying" => ("sad", "crying"),
        "laughing" => ("happy", "laughing"),
        _ => ("neutral", "normal"),
    }
}

pub fn normalize_style(raw: &str) -> String {
    let low = raw.trim().to_lowercase();
    let mapped = match low.as_str() {
        "" => "",
        "laugh" | "laughs" | "laughter" | "chuckle" | "laughing" => "laughing",
        "whisper" | "whispers" | "whispering" | "aside" => "whispering",
        "shout" | "shouts" | "shouting" | "yell" | "scream" => "shouting",
        "angry" | "anger" | "furious" | "rage" => "angry",
        "sad" | "sigh" | "sighs" | "grief" | "sorrow" => "sad",
        "cry" | "crying" | "sob" | "sobbing" => "crying",
        "gasp" | "fear" | "fearful" | "scared" | "afraid" | "nervous" | "panic" => "fearful",
        "excited" | "happy" | "cheerful" | "joy" | "joyful" => "happy",
        "calm" | "neutral" | "plain" => "neutral",
        _ => "",
    };
    mapped.to_string()
}

fn style_rate(style: &str) -> f64 {
    match style {
        "shouting" => 1.08,
        "angry" => 1.06,
        "happy" => 1.05,
        "fearful" => 1.10,
        "laughing" => 1.0,
        "sad" => 0.90,
        "crying" => 0.85,
        "whispering" => 0.92,
        _ => 1.0,
    }
}

fn pause_factor(style: &str) -> f64 {
    match style {
        "sad" => 1.3,
        "crying" => 1.4,
        "whispering" => 1.2,
        "fearful" => 0.9,
        "shouting" => 0.7,
        "angry" => 0.8,
        "happy" => 0.9,
        _ => 1.0,
    }
}

fn tempo_bounds(style: &str) -> (f32, f32) {
    match style {
        "sad" | "crying" | "whispering" => (0.85, 1.30),
        "shouting" | "angry" | "fearful" => (0.90, 1.80),
        _ => (0.85, 1.60),
    }
}

/// Lowest intensity a label may carry; strong labels never drop to calm.
fn intensity_floor(style: &str) -> f32 {
    match style {
        "shouting" => 0.65,
        "angry" | "crying" => 0.6,
        "laughing" | "fearful" => 0.5,
        "happy" | "sad" => 0.35,
        "whispering" => 0.3,
        _ => 0.0,
    }
}

const CRY_CUES: [&str; 8] = ["sob", "crying", "cries", "tears", "呜呜", "哭", "流泪", "យំ"];
const FEAR_CUES: [&str; 9] = [
    "help!", "help me", "no, no", "please don't", "救命", "不要", "害怕", "ជួយផង", "ខ្លាច",
];

fn text_style(text: &str) -> Option<(&'static str, f32, String)> {
    let low = text.to_lowercase();
    let bangs = text.matches('!').count() + text.matches('！').count();
    let latin: Vec<char> = text.chars().filter(|c| c.is_ascii_alphabetic()).collect();
    let upper = latin.iter().filter(|c| c.is_ascii_uppercase()).count();
    if latin.len() >= 6 && upper * 10 >= latin.len() * 7 {
        return Some(("shouting", 0.55, "all-caps line".into()));
    }
    if bangs >= 2 {
        return Some(("shouting", 0.55, format!("{bangs} exclamation marks")));
    }
    if CRY_CUES.iter().any(|c| low.contains(c)) {
        return Some(("crying", 0.5, "crying cue in text".into()));
    }
    if FEAR_CUES.iter().any(|c| low.contains(c)) {
        return Some(("fearful", 0.45, "fear cue in text".into()));
    }
    None
}

fn expression_confidence(source: &str) -> f32 {
    match source {
        "manual" => 1.0,
        "llm" => 0.7,
        "text" | "" => 0.6,
        "intent" => 0.45,
        _ => 0.5,
    }
}

fn median(values: &mut [f32]) -> Option<f32> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    Some(values[values.len() / 2])
}

/// Speaker baselines: (median rms dB, median pitch Hz) over that speaker's lines.
fn speaker_baselines(lines: &[PerformanceLine]) -> std::collections::HashMap<String, (f32, f32)> {
    let mut acc: std::collections::HashMap<String, (Vec<f32>, Vec<f32>)> = Default::default();
    for line in lines {
        if let Some(p) = &line.prosody {
            if p.confidence <= 0.0 || p.rms_db <= -80.0 {
                continue;
            }
            let entry = acc.entry(line.speaker.clone()).or_default();
            entry.0.push(p.rms_db);
            if p.pitch_hz > 0.0 {
                entry.1.push(p.pitch_hz);
            }
        }
    }
    acc.into_iter()
        .map(|(k, (mut r, mut p))| {
            let rms = median(&mut r).unwrap_or(-30.0);
            let pitch = median(&mut p).unwrap_or(0.0);
            (k, (rms, pitch))
        })
        .collect()
}

/// Arousal 0..1 from loudness and pitch against the speaker's own baseline.
fn arousal(p: &ProsodyFeatures, base: Option<&(f32, f32)>) -> (f32, f32, f32) {
    let (rms_base, pitch_base) = base.copied().unwrap_or((p.rms_db, p.pitch_hz));
    let rel_loud = p.rms_db - rms_base;
    let rel_pitch = if p.pitch_hz > 0.0 && pitch_base > 0.0 {
        12.0 * (p.pitch_hz / pitch_base).log2()
    } else {
        0.0
    };
    let a = 0.5 + rel_loud / 12.0 + rel_pitch / 24.0 + (p.pitch_range_st - 4.0) / 20.0;
    (a.clamp(0.0, 1.0), rel_loud, rel_pitch)
}

fn clause_breaks(text: &str) -> usize {
    text.chars()
        .filter(|c| matches!(c, ',' | '，' | '、' | ';' | '；' | '…' | '—' | '។' | ':' | '：'))
        .count()
}

fn pronunciation_hints(text: &str, names: &[String], lang: &str) -> Vec<PronunciationHint> {
    let mut out: Vec<PronunciationHint> = Vec::new();
    let mut seen: Vec<String> = Vec::new();
    for name in names {
        let clean = name.trim();
        if clean.chars().count() < 2 || seen.iter().any(|s| s == clean) {
            continue;
        }
        if text.contains(clean) {
            seen.push(clean.to_string());
            out.push(PronunciationHint {
                text: clean.to_string(),
                kind: "name".into(),
                hint: "character name; keep one consistent reading".into(),
            });
        }
    }
    let non_latin_target = {
        let l = lang.to_lowercase();
        !(l.is_empty()
            || l.starts_with("english")
            || l.starts_with("spanish")
            || l.starts_with("french")
            || l.starts_with("german")
            || l.starts_with("vietnamese"))
    };
    let mut word = String::new();
    let mut words: Vec<(String, &'static str)> = Vec::new();
    let mut kind: &'static str = "";
    let flush = |word: &mut String, kind: &mut &'static str, words: &mut Vec<(String, &'static str)>| {
        if !word.is_empty() {
            words.push((word.clone(), kind));
            word.clear();
        }
        *kind = "";
    };
    for c in text.chars() {
        let k: &'static str = if c.is_ascii_digit() {
            "number"
        } else if c.is_ascii_alphabetic() {
            "foreign"
        } else if ('\u{4E00}'..='\u{9FFF}').contains(&c) {
            "untranslated"
        } else {
            ""
        };
        if k.is_empty() || (!kind.is_empty() && k != kind) {
            flush(&mut word, &mut kind, &mut words);
        }
        if !k.is_empty() {
            word.push(c);
            kind = k;
        }
    }
    flush(&mut word, &mut kind, &mut words);
    for (w, k) in words {
        if seen.iter().any(|s| s == &w || s.contains(w.as_str())) {
            continue;
        }
        let hint = match k {
            "number" => "read the number as words in the target language",
            "foreign" if non_latin_target && w.chars().count() >= 2 => {
                "Latin-script word in the line; check the TTS reading"
            }
            "untranslated" if non_latin_target && !lang.to_lowercase().starts_with("chinese") => {
                "source-script text left in the line"
            }
            _ => "",
        };
        if !hint.is_empty() {
            seen.push(w.clone());
            out.push(PronunciationHint { text: w, kind: k.into(), hint: hint.into() });
        }
    }
    out
}

/// Delivery plan for every line: style, intensity, timing, hints, confidence.
pub fn plan_performance(req: &PerformanceRequest) -> PerformancePlan {
    let baselines = speaker_baselines(&req.lines);
    let mut order: Vec<usize> = (0..req.lines.len()).collect();
    order.sort_by(|&a, &b| {
        req.lines[a]
            .start_sec
            .partial_cmp(&req.lines[b].start_sec)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let mut prev_end: Vec<Option<f64>> = vec![None; req.lines.len()];
    let mut next_start: Vec<Option<f64>> = vec![None; req.lines.len()];
    for w in order.windows(2) {
        next_start[w[0]] = Some(req.lines[w[1]].start_sec);
        prev_end[w[1]] = Some(req.lines[w[0]].end_sec);
    }

    let lines = req
        .lines
        .iter()
        .enumerate()
        .map(|(pos, line)| plan_line(line, req, baselines.get(&line.speaker), prev_end[pos], next_start[pos]))
        .collect();
    PerformancePlan { version: 1, lines }
}

fn plan_line(
    line: &PerformanceLine,
    req: &PerformanceRequest,
    base: Option<&(f32, f32)>,
    prev_end: Option<f64>,
    next_start: Option<f64>,
) -> LinePlan {
    let mut evidence: Vec<String> = Vec::new();
    let spoken = if line.text.trim().is_empty() { &line.source_text } else { &line.text };
    let prosody = line.prosody.as_ref().filter(|p| p.confidence > 0.0 && p.rms_db > -80.0);
    let (arousal_v, rel_loud, rel_pitch) = match prosody {
        Some(p) => arousal(p, base),
        None => (0.5, 0.0, 0.0),
    };

    let manual_style = normalize_style(&line.style);
    let (style, intensity, emotion_conf, source): (String, f32, f32, String) = if line.manual && !manual_style.is_empty() {
        evidence.push("set in the editor".into());
        let i = line.intensity.unwrap_or(0.5).clamp(0.0, 1.0);
        (manual_style, i, 1.0, "manual".into())
    } else {
        let labelled = normalize_style(&line.expression);
        let from_text = text_style(&line.source_text).or_else(|| text_style(spoken));
        let (mut style, mut conf, mut src) = if !labelled.is_empty() {
            let src = if line.expression_source.is_empty() { "text".to_string() } else { line.expression_source.clone() };
            evidence.push(format!("{} cue '{}'", src, line.expression));
            (labelled, expression_confidence(&src), src)
        } else if let Some((s, c, why)) = &from_text {
            evidence.push(why.clone());
            (s.to_string(), *c, "text".to_string())
        } else {
            ("neutral".to_string(), 0.5, "default".to_string())
        };
        if let Some((s, c, why)) = &from_text {
            if *s == "crying" && style == "sad" {
                style = "crying".into();
                conf = conf.max(*c);
                evidence.push(why.clone());
            }
            if *s == "shouting" && style == "angry" {
                style = "shouting".into();
                conf = conf.max(*c);
                evidence.push(why.clone());
            }
        }
        if prosody.is_some() {
            if style == "neutral" && rel_loud >= 6.0 && arousal_v >= 0.75 {
                style = "shouting".into();
                conf = 0.5;
                src = "prosody".into();
                evidence.push(format!("{rel_loud:+.1} dB over this speaker's level"));
            } else if style == "neutral" && rel_loud <= -9.0 && prosody.map(|p| p.voiced_ratio < 0.35).unwrap_or(false) {
                style = "whispering".into();
                conf = 0.4;
                src = "prosody".into();
                evidence.push(format!("{rel_loud:+.1} dB and little voicing"));
            } else if style == "angry" && rel_loud >= 6.0 {
                style = "shouting".into();
                conf = conf.max(0.6);
                evidence.push(format!("angry and {rel_loud:+.1} dB louder"));
            } else if (style == "shouting" || style == "angry") && rel_loud >= 2.0 {
                conf = (conf + 0.15).min(0.95);
                evidence.push(format!("audio agrees: {rel_loud:+.1} dB"));
            }
            if rel_pitch.abs() >= 3.0 {
                evidence.push(format!("pitch {rel_pitch:+.1} st vs speaker"));
            }
        }
        let base_i: f32 = match style.as_str() {
            "neutral" => 0.3,
            "whispering" => 0.45,
            "sad" | "happy" => 0.55,
            "fearful" | "laughing" => 0.6,
            "angry" | "crying" => 0.7,
            "shouting" => 0.8,
            _ => 0.5,
        };
        let soft = line.expression.trim().eq_ignore_ascii_case("calm") || line.expression.trim().eq_ignore_ascii_case("sigh");
        let mut i = if prosody.is_some() { 0.6 * base_i + 0.4 * arousal_v } else { base_i };
        if soft {
            i = i.min(0.35);
        }
        if line.intent == "command" && style == "shouting" && line.expression_source == "intent" {
            i = i.min(0.6);
        }
        i = i.max(intensity_floor(&style)).clamp(0.0, 1.0);
        (style, i, conf, src)
    };

    let intensity_conf = match (source.as_str(), prosody.is_some()) {
        ("manual", _) => 1.0,
        (_, true) => 0.6 + 0.3 * prosody.map(|p| p.confidence).unwrap_or(0.0),
        _ => 0.45,
    };

    let slot = (line.end_sec - line.start_sec).max(0.15);
    let pause_before = prev_end.map(|e| (line.start_sec - e).clamp(0.0, 2.0)).unwrap_or(0.0);
    let pause_after = next_start.map(|s| (s - line.end_sec).clamp(0.0, 2.0)).unwrap_or(0.0);
    let breaks = clause_breaks(spoken) as f64;
    let internal = (breaks * 0.15 * pause_factor(&style)).min(slot * 0.35);
    let speech_sec = (slot - internal).max(0.1);
    let units = spoken_units(spoken, &req.lang).max(0);
    let natural = pace_rate(&req.lang) * style_rate(&style);
    let needed = units as f64 / speech_sec;
    let ratio = if natural > 0.0 && units > 0 { needed / natural } else { 1.0 };
    let (tempo_min, tempo_max) = tempo_bounds(&style);
    let timing_conf = if units == 0 {
        0.3
    } else if ratio <= 1.0 {
        (1.0 - (1.0 - ratio) * 0.6).clamp(0.0, 1.0) as f32
    } else {
        (1.0 - (ratio.ln() / 2f64.ln())).clamp(0.0, 1.0) as f32
    };
    if ratio > tempo_max as f64 {
        evidence.push(format!("needs {ratio:.2}x pace; line may run long"));
    }

    let (emotion, delivery) = style_parts(&style);
    let overall = 0.5 * emotion_conf + 0.2 * intensity_conf + 0.3 * timing_conf;
    LinePlan {
        index: line.index,
        emotion: emotion.into(),
        delivery: delivery.into(),
        style,
        intensity: round3(intensity),
        source,
        target_duration_sec: round3d(slot),
        speech_sec: round3d(speech_sec),
        pause_before_sec: round3d(pause_before),
        pause_after_sec: round3d(pause_after),
        internal_pause_sec: round3d(internal),
        units,
        natural_units_per_sec: round3d(natural),
        needed_units_per_sec: round3d(needed),
        rate_ratio: round3d(ratio),
        tempo_min,
        tempo_max,
        pronunciation: pronunciation_hints(spoken, &req.names, &req.lang),
        confidence: PlanConfidence {
            emotion: round3(emotion_conf),
            intensity: round3(intensity_conf),
            timing: round3(timing_conf),
            overall: round3(overall),
        },
        evidence,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn line(index: usize, text: &str, expr: &str, src: &str) -> PerformanceLine {
        PerformanceLine {
            index,
            text: text.into(),
            source_text: text.into(),
            start_sec: index as f64 * 3.0,
            end_sec: index as f64 * 3.0 + 2.0,
            speaker: "SPEAKER_00".into(),
            expression: expr.into(),
            expression_source: src.into(),
            ..Default::default()
        }
    }

    fn tone(rate: u32, secs: f32, hz: f32, amp: f32) -> Vec<f32> {
        (0..(rate as f32 * secs) as usize)
            .map(|n| (n as f32 * hz * std::f32::consts::TAU / rate as f32).sin() * amp)
            .collect()
    }

    #[test]
    fn angry_line_is_never_neutral() {
        let req = PerformanceRequest {
            lang: "Khmer".into(),
            lines: vec![line(0, "How dare you!", "angry", "llm")],
            ..Default::default()
        };
        let plan = plan_performance(&req);
        assert_eq!(plan.lines[0].style, "angry");
        assert!(plan.lines[0].intensity >= 0.6);
    }

    #[test]
    fn exclamations_make_shouting_without_a_label() {
        let req = PerformanceRequest {
            lang: "English".into(),
            lines: vec![line(0, "Get out!! Now!", "", "")],
            ..Default::default()
        };
        let plan = plan_performance(&req);
        assert_eq!(plan.lines[0].style, "shouting");
        assert_eq!(plan.lines[0].delivery, "shouting");
    }

    #[test]
    fn loud_line_against_speaker_baseline_becomes_shouting() {
        let quiet = ProsodyFeatures { rms_db: -30.0, pitch_hz: 150.0, pitch_range_st: 3.0, voiced_ratio: 0.8, confidence: 0.9, ..Default::default() };
        let loud = ProsodyFeatures { rms_db: -18.0, pitch_hz: 220.0, pitch_range_st: 8.0, voiced_ratio: 0.9, confidence: 0.9, ..Default::default() };
        let mut lines = vec![line(0, "ok", "", ""), line(1, "ok", "", ""), line(2, "stop", "", "")];
        lines[0].prosody = Some(quiet.clone());
        lines[1].prosody = Some(quiet);
        lines[2].prosody = Some(loud);
        let plan = plan_performance(&PerformanceRequest { lang: "English".into(), lines, ..Default::default() });
        assert_eq!(plan.lines[0].style, "neutral");
        assert_eq!(plan.lines[2].style, "shouting");
        assert_eq!(plan.lines[2].source, "prosody");
    }

    #[test]
    fn editor_style_wins() {
        let mut l = line(0, "Get out!!", "shout", "llm");
        l.manual = true;
        l.style = "whispering".into();
        l.intensity = Some(0.2);
        let plan = plan_performance(&PerformanceRequest { lines: vec![l], ..Default::default() });
        assert_eq!(plan.lines[0].style, "whispering");
        assert_eq!(plan.lines[0].confidence.emotion, 1.0);
        assert!((plan.lines[0].intensity - 0.2).abs() < 1e-6);
    }

    #[test]
    fn pauses_and_hints_are_planned() {
        let mut a = line(0, "សួស្តី John, 3 ថ្ងៃ", "", "");
        a.speaker = "A".into();
        let b = line(1, "បាទ", "", "");
        let plan = plan_performance(&PerformanceRequest {
            lang: "Khmer".into(),
            names: vec!["John".into()],
            lines: vec![a, b],
        });
        assert!((plan.lines[0].pause_after_sec - 1.0).abs() < 1e-6);
        assert!((plan.lines[1].pause_before_sec - 1.0).abs() < 1e-6);
        assert!(plan.lines[0].internal_pause_sec > 0.0);
        let kinds: Vec<&str> = plan.lines[0].pronunciation.iter().map(|h| h.kind.as_str()).collect();
        assert!(kinds.contains(&"name"));
        assert!(kinds.contains(&"number"));
    }

    #[test]
    fn pitch_of_a_tone_is_found() {
        let rate = 8000;
        let mut samples = vec![0.0f32; rate as usize];
        samples.extend(tone(rate, 1.0, 200.0, 0.4));
        let spans = vec![ProsodySpan { index: 0, start_sec: 1.0, end_sec: 2.0 }];
        let feats = analyze_prosody(&samples, rate, &spans);
        assert!((feats[0].pitch_hz - 200.0).abs() < 8.0, "{:?}", feats[0]);
        assert!(feats[0].voiced_ratio > 0.5);
    }

    #[test]
    fn louder_span_reads_louder() {
        let rate = 8000;
        let mut samples = tone(rate, 1.0, 180.0, 0.05);
        samples.extend(tone(rate, 1.0, 180.0, 0.5));
        let spans = vec![
            ProsodySpan { index: 0, start_sec: 0.0, end_sec: 1.0 },
            ProsodySpan { index: 1, start_sec: 1.0, end_sec: 2.0 },
        ];
        let feats = analyze_prosody(&samples, rate, &spans);
        assert!(feats[1].rms_db - feats[0].rms_db > 15.0);
    }
}
