use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DubbingPipelinePlan {
    pub source_language: String,
    pub target_language: String,
    pub asr_model: String,
    pub translator: String,
    pub default_voice_id: String,
    pub ducking_speech_gain_db: f32,
    pub ducking_music_gain_db: f32,
    pub speech_speed_min: f32,
    pub speech_speed_max: f32,
    /// Fit spoken length to TTS slot (recommended_syllables).
    #[serde(default = "default_true")]
    pub translate_fit_duration: bool,
    /// Prefer natural slang / idioms in the target language.
    #[serde(default = "default_true")]
    pub translate_slang: bool,
    /// Allow optional TTS expression tags in translated lines.
    #[serde(default = "default_true")]
    pub translate_expression: bool,
}

fn default_true() -> bool {
    true
}

impl Default for DubbingPipelinePlan {
    fn default() -> Self {
        Self {
            source_language: "auto".to_string(),
            target_language: "km".to_string(),
            asr_model: "whisper-medium".to_string(),
            translator: "gemini".to_string(),
            default_voice_id: "km-KH-PisethNeural".to_string(),
            ducking_speech_gain_db: 0.0,
            ducking_music_gain_db: -14.0,
            speech_speed_min: 0.85,
            speech_speed_max: 1.35,
            translate_fit_duration: true,
            translate_slang: true,
            translate_expression: true,
        }
    }
}
