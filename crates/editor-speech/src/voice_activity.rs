use editor_types::Rational;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpeechSpan {
    pub start: Rational,
    pub end: Rational,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VadParameters {
    pub energy_threshold: f32,
    pub min_speech_ms: u32,
    pub min_silence_ms: u32,
    pub padding_ms: u32,
}

impl Default for VadParameters {
    fn default() -> Self {
        Self {
            energy_threshold: 0.5,
            min_speech_ms: 250,
            min_silence_ms: 300,
            padding_ms: 100,
        }
    }
}
