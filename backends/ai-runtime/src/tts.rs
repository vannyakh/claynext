use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TtsVoiceSpec {
    pub voice_id: String,
    pub name: String,
    pub language: String,
    pub gender: String, // "male", "female", "neutral"
    pub rate: f32,      // 0.5 to 2.0
    pub pitch: f32,     // -10.0 to +10.0
    pub volume: f32,    // 0.0 to 1.0
}

impl Default for TtsVoiceSpec {
    fn default() -> Self {
        Self {
            voice_id: "km-KH-PisethNeural".to_string(),
            name: "Piseth (Khmer)".to_string(),
            language: "km-KH".to_string(),
            gender: "male".to_string(),
            rate: 1.0,
            pitch: 0.0,
            volume: 1.0,
        }
    }
}
