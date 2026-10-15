use editor_types::Rational;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AsrWord {
    pub word: String,
    pub start: Rational,
    pub end: Rational,
    pub probability: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AsrSegment {
    pub id: u32,
    pub start: Rational,
    pub end: Rational,
    pub text: String,
    pub speaker: Option<String>,
    pub words: Vec<AsrWord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AsrOptions {
    pub model_size: String,
    pub language: Option<String>,
    pub temperature: f32,
    pub beam_size: u32,
    pub word_timestamps: bool,
}

impl Default for AsrOptions {
    fn default() -> Self {
        Self {
            model_size: "medium".to_string(),
            language: None,
            temperature: 0.0,
            beam_size: 5,
            word_timestamps: true,
        }
    }
}
