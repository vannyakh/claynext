use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UtteranceSegment {
    pub text: String,
    pub rate_multiplier: f32,
    pub pitch_offset: f32,
    pub pause_after_sec: f32,
    pub style: Option<String>,
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
        if chars[i] == '[' {
            if let Some(close_idx) = chars[i..].iter().position(|&c| c == ']') {
                let tag_content: String = chars[i + 1..i + close_idx].iter().collect();
                let tag_lower = tag_content.trim().to_lowercase();

                // If we have accumulated text before this tag, push segment
                if !current_text.trim().is_empty() {
                    segments.push(UtteranceSegment {
                        text: current_text.trim().to_string(),
                        rate_multiplier: current_rate,
                        pitch_offset: current_pitch,
                        pause_after_sec: 0.0,
                        style: current_style.clone(),
                    });
                    current_text.clear();
                }

                if tag_lower.starts_with("pause:") || tag_lower.starts_with("silence:") {
                    let val_str = tag_lower
                        .replace("pause:", "")
                        .replace("silence:", "")
                        .replace('s', "")
                        .trim()
                        .to_string();
                    if let Ok(pause_sec) = val_str.parse::<f32>() {
                        if let Some(last) = segments.last_mut() {
                            last.pause_after_sec += pause_sec;
                        } else {
                            segments.push(UtteranceSegment {
                                text: String::new(),
                                rate_multiplier: 1.0,
                                pitch_offset: 0.0,
                                pause_after_sec: pause_sec,
                                style: None,
                            });
                        }
                    }
                } else if tag_lower == "happy" || tag_lower == "cheerful" {
                    current_style = Some("cheerful".to_string());
                    current_pitch = 2.0;
                    current_rate = 1.05;
                } else if tag_lower == "sad" {
                    current_style = Some("sad".to_string());
                    current_pitch = -2.0;
                    current_rate = 0.9;
                } else if tag_lower == "whisper" {
                    current_style = Some("whisper".to_string());
                    current_pitch = -1.0;
                    current_rate = 0.85;
                } else if tag_lower == "excited" {
                    current_style = Some("excited".to_string());
                    current_pitch = 3.0;
                    current_rate = 1.15;
                } else if tag_lower == "reset" || tag_lower == "normal" {
                    current_style = None;
                    current_pitch = 0.0;
                    current_rate = 1.0;
                } else if tag_lower.starts_with("rate:") {
                    let val_str = tag_lower.replace("rate:", "").trim().to_string();
                    if let Ok(r) = val_str.parse::<f32>() {
                        current_rate = r.clamp(0.5, 2.0);
                    }
                } else if tag_lower.starts_with("pitch:") {
                    let val_str = tag_lower.replace("pitch:", "").trim().to_string();
                    if let Ok(p) = val_str.parse::<f32>() {
                        current_pitch = p.clamp(-10.0, 10.0);
                    }
                }

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
}
