use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UtteranceSegment {
    pub text: String,
    pub rate_multiplier: f32,
    pub pitch_offset: f32,
    pub pause_after_sec: f32,
    pub style: Option<String>,
}

fn flush_text(
    segments: &mut Vec<UtteranceSegment>,
    current_text: &mut String,
    rate: f32,
    pitch: f32,
    style: &Option<String>,
) {
    if current_text.trim().is_empty() {
        current_text.clear();
        return;
    }
    segments.push(UtteranceSegment {
        text: current_text.trim().to_string(),
        rate_multiplier: rate,
        pitch_offset: pitch,
        pause_after_sec: 0.0,
        style: style.clone(),
    });
    current_text.clear();
}

fn lead_in(segments: &mut Vec<UtteranceSegment>, secs: f32) {
    match segments.last() {
        Some(last) if last.pause_after_sec == 0.0 => add_pause(segments, secs),
        _ => {}
    }
}

fn add_pause(segments: &mut Vec<UtteranceSegment>, secs: f32) {
    let secs = secs.clamp(0.05, 2.5);
    if let Some(last) = segments.last_mut() {
        last.pause_after_sec += secs;
    } else {
        segments.push(UtteranceSegment {
            text: String::new(),
            rate_multiplier: 1.0,
            pitch_offset: 0.0,
            pause_after_sec: secs,
            style: None,
        });
    }
}

/// Turn one `[tag]` / `{tag}` into a delay, a short vocal, or a voice style.
fn apply_expression_tag(
    tag_lower: &str,
    segments: &mut Vec<UtteranceSegment>,
    current_text: &mut String,
    rate: &mut f32,
    pitch: &mut f32,
    style: &mut Option<String>,
) {
    flush_text(segments, current_text, *rate, *pitch, style);

    let timed = tag_lower
        .strip_prefix("pause:")
        .or_else(|| tag_lower.strip_prefix("silence:"))
        .or_else(|| tag_lower.strip_prefix("break:"));
    if let Some(raw) = timed {
        let val = raw.trim().trim_end_matches('s').trim();
        if let Ok(pause_sec) = val.parse::<f32>() {
            add_pause(segments, pause_sec);
        }
        return;
    }

    match tag_lower {
        "pause" => add_pause(segments, 0.48),
        "break" => add_pause(segments, 0.36),
        "silence" => add_pause(segments, 0.55),
        "laugh" | "laughs" | "laughter" => {
            segments.push(UtteranceSegment {
                text: "ha ha ha".into(),
                rate_multiplier: 1.05,
                pitch_offset: 2.0,
                pause_after_sec: 0.22,
                style: Some("laugh".into()),
            });
        }
        "sigh" | "sighs" => {
            segments.push(UtteranceSegment {
                text: "sigh".into(),
                rate_multiplier: 0.9,
                pitch_offset: -2.0,
                pause_after_sec: 0.28,
                style: Some("sigh".into()),
            });
        }
        "gasp" | "gasps" => {
            segments.push(UtteranceSegment {
                text: "ah".into(),
                rate_multiplier: 1.0,
                pitch_offset: 3.0,
                pause_after_sec: 0.18,
                style: Some("gasp".into()),
            });
        }
        "happy" | "cheerful" => {
            *style = Some("cheerful".into());
            *pitch = 2.0;
            *rate = 1.05;
            lead_in(segments, 0.08);
        }
        "excited" => {
            *style = Some("excited".into());
            *pitch = 3.0;
            *rate = 1.12;
            lead_in(segments, 0.06);
        }
        "angry" | "shout" | "shouts" => {
            *style = Some(tag_lower.to_string());
            *pitch = if tag_lower.starts_with("shout") { 4.0 } else { -1.0 };
            *rate = 1.08;
            lead_in(segments, 0.06);
        }
        "sad" => {
            *style = Some("sad".into());
            *pitch = -3.0;
            *rate = 0.9;
            lead_in(segments, 0.1);
        }
        "whisper" => {
            *style = Some("whisper".into());
            *pitch = -2.0;
            *rate = 0.86;
            lead_in(segments, 0.08);
        }
        "reset" | "normal" => {
            *style = None;
            *pitch = 0.0;
            *rate = 1.0;
        }
        _ if tag_lower.starts_with("rate:") => {
            if let Ok(r) = tag_lower.trim_start_matches("rate:").trim().parse::<f32>() {
                *rate = r.clamp(0.5, 2.0);
            }
        }
        _ if tag_lower.starts_with("pitch:") => {
            if let Ok(p) = tag_lower.trim_start_matches("pitch:").trim().parse::<f32>() {
                *pitch = p.clamp(-10.0, 10.0);
            }
        }
        _ => {}
    }
}

pub fn parse_expression_tags(input: &str) -> Vec<UtteranceSegment> {
    let mut segments = Vec::new();
    let mut current_text = String::new();
    let mut current_rate = 1.0f32;
    let mut current_pitch = 0.0f32;
    let mut current_style: Option<String> = None;

    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;

    while i < chars.len() {
        if chars[i] == '[' || chars[i] == '{' {
            let close = if chars[i] == '[' { ']' } else { '}' };
            if let Some(close_idx) = chars[i..].iter().position(|&c| c == close) {
                let tag_content: String = chars[i + 1..i + close_idx].iter().collect();
                let tag_lower = tag_content.trim().to_lowercase();
                apply_expression_tag(
                    &tag_lower,
                    &mut segments,
                    &mut current_text,
                    &mut current_rate,
                    &mut current_pitch,
                    &mut current_style,
                );
                i += close_idx + 1;
                continue;
            }
        }

        current_text.push(chars[i]);
        i += 1;
    }

    if !current_text.trim().is_empty() {
        segments.push(UtteranceSegment {
            text: current_text.trim().to_string(),
            rate_multiplier: current_rate,
            pitch_offset: current_pitch,
            pause_after_sec: 0.0,
            style: current_style,
        });
    }

    segments
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_tags() {
        let input = "Hello world! [pause: 0.5s] [excited] This is awesome! [normal] Back to normal.";
        let segments = parse_expression_tags(input);
        assert_eq!(segments.len(), 3);
        assert_eq!(segments[0].text, "Hello world!");
        assert_eq!(segments[0].pause_after_sec, 0.5);
        assert_eq!(segments[1].text, "This is awesome!");
        assert_eq!(segments[1].style.as_deref(), Some("excited"));
        assert_eq!(segments[2].text, "Back to normal.");
        assert_eq!(segments[2].style, None);
    }

    #[test]
    fn test_pause_and_laugh_delays() {
        let segments = parse_expression_tags("[sigh] Wait. [pause] Look.");
        assert!(segments.len() >= 3);
        assert_eq!(segments[0].text, "sigh");
        assert!(segments[0].pause_after_sec >= 0.2);
        assert_eq!(segments[1].text, "Wait.");
        assert!(segments[1].pause_after_sec >= 0.4);
        assert_eq!(segments[2].text, "Look.");
    }
}
