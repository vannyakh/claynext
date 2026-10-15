use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AsrTranscriptionSegment {
    pub id: u32,
    pub start: f64,
    pub end: f64,
    pub text: String,
    pub speaker: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WhisperConfig {
    pub model_size: String, // "tiny", "base", "small", "medium", "large-v3"
    pub language: Option<String>,
    pub beam_size: u32,
    pub vad_filter: bool,
    pub word_timestamps: bool,
}

impl Default for WhisperConfig {
    fn default() -> Self {
        Self {
            model_size: "medium".to_string(),
            language: None,
            beam_size: 5,
            vad_filter: true,
            word_timestamps: true,
        }
    }
}
