use editor_types::Rational;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpeakerTurn {
    pub speaker_id: String,
    pub speaker_name: Option<String>,
    pub start: Rational,
    pub end: Rational,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiarizationOptions {
    pub max_speakers: Option<usize>,
    pub min_speakers: Option<usize>,
    pub min_turn_duration_ms: u32,
}

impl Default for DiarizationOptions {
    fn default() -> Self {
        Self {
            max_speakers: Some(6),
            min_speakers: Some(1),
            min_turn_duration_ms: 500,
        }
    }
}
