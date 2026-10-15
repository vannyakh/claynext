use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DemucsStemConfig {
    pub model_name: String,
    pub shifts: u32,
    pub overlap: f32,
    pub ducking_speech_gain_db: f32,
    pub ducking_music_gain_db: f32,
}

impl Default for DemucsStemConfig {
    fn default() -> Self {
        Self {
            model_name: "htdemucs".to_string(),
            shifts: 1,
            overlap: 0.25,
            ducking_speech_gain_db: 0.0,
            ducking_music_gain_db: -12.0,
        }
    }
}

pub fn calculate_ducked_background_volume(base_volume: f32, attenuation_db: f32) -> f32 {
    let factor = 10.0f32.powf(attenuation_db / 20.0);
    (base_volume * factor).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ducked_volume() {
        let v = calculate_ducked_background_volume(1.0, -12.0);
        assert!(v < 0.3 && v > 0.2);
    }
}
