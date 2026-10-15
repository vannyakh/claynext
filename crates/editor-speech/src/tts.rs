use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TtsVoice {
    pub id: String,
    pub name: String,
    pub locale: String,
    pub gender: String, // "male", "female", "neutral"
    pub sample_rate: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TtsRequest {
    pub text: String,
    pub voice_id: String,
    pub speed: f32,
    pub pitch: f32,
    pub volume: f32,
}

impl Default for TtsRequest {
    fn default() -> Self {
        Self {
            text: String::new(),
            voice_id: "km-KH-PisethNeural".to_string(),
            speed: 1.0,
            pitch: 0.0,
            volume: 1.0,
        }
    }
}
