use editor_types::Rational;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DubbedSegment {
    pub id: u32,
    pub original_start: Rational,
    pub original_end: Rational,
    pub target_start: Rational,
    pub target_end: Rational,
    pub source_text: String,
    pub translated_text: String,
    pub voice_id: String,
    pub speech_speed: f32,
    pub pitch_shift: f32,
    pub volume_gain_db: f32,
    pub audio_file_path: Option<String>,
}

impl DubbedSegment {
    pub fn duration(&self) -> Rational {
        self.target_end - self.target_start
    }
}
