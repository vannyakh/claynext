//! editor-subtitles: Subtitle data models, ASS header generation, and event formatting.

use editor_types::ColorRgba;
use serde::{Deserialize, Serialize};

/// Individual subtitle caption item.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubtitleItem {
    pub start_seconds: f64,
    pub end_seconds: f64,
    pub text: String,
    pub speaker: Option<String>,
}

/// Advanced SubStation Alpha (.ass) style description.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssStyle {
    pub name: String,
    pub font_name: String,
    pub font_size: u32,
    pub primary_color: ColorRgba,
    pub outline_color: ColorRgba,
    pub outline_width: f32,
    pub shadow_depth: f32,
    pub alignment: u32, // numpad layout: 2 = bottom center
}

impl Default for AssStyle {
    fn default() -> Self {
        Self {
            name: "Default".to_string(),
            font_name: "Arial".to_string(),
            font_size: 24,
            primary_color: ColorRgba::new(255, 255, 255, 255),
            outline_color: ColorRgba::new(0, 0, 0, 255),
            outline_width: 2.0,
            shadow_depth: 1.0,
            alignment: 2,
        }
    }
}

/// Convert seconds to ASS time format `H:MM:SS.cc` (centiseconds).
pub fn format_ass_time(seconds: f64) -> String {
    let h = (seconds / 3600.0).floor() as u32;
    let m = ((seconds % 3600.0) / 60.0).floor() as u32;
    let s = (seconds % 60.0).floor() as u32;
    let cs = ((seconds % 1.0) * 100.0).round() as u32;
    format!("{}:{:02}:{:02}.{:02}", h, m, s, cs)
}

/// Format a subtitle item into an ASS Dialogue line.
pub fn format_ass_dialogue(style_name: &str, item: &SubtitleItem) -> String {
    format!(
        "Dialogue: 0,{},{},{},{},0,0,0,,{}",
        format_ass_time(item.start_seconds),
        format_ass_time(item.end_seconds),
        style_name,
        item.speaker.as_deref().unwrap_or(""),
        item.text.replace('\n', "\\N")
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ass_time_format() {
        assert_eq!(format_ass_time(65.432), "0:01:05.43");
        assert_eq!(format_ass_time(3600.0), "1:00:00.00");
    }

    #[test]
    fn test_dialogue_line() {
        let item = SubtitleItem {
            start_seconds: 1.5,
            end_seconds: 3.8,
            text: "Hello\nWorld".to_string(),
            speaker: Some("Narrator".to_string()),
        };
        let line = format_ass_dialogue("Default", &item);
        assert_eq!(
            line,
            "Dialogue: 0,0:00:01.50,0:00:03.80,Default,Narrator,0,0,0,,Hello\\NWorld"
        );
    }
}
