use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpeechEnhancementOptions {
    pub remove_background_noise: bool,
    pub remove_reverb: bool,
    pub isolate_vocals: bool,
    pub noise_reduction_db: f32,
}

impl Default for SpeechEnhancementOptions {
    fn default() -> Self {
        Self {
            remove_background_noise: true,
            remove_reverb: true,
            isolate_vocals: false,
            noise_reduction_db: 18.0,
        }
    }
}
