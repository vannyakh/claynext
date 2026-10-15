use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum VoiceGender {
    Male,
    Female,
    Child,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VoiceClassificationResult {
    pub gender: VoiceGender,
    pub confidence: f32,
    pub pitch_fundamental_hz: f32,
    pub speaker_embedding: Option<Vec<f32>>,
}

pub fn estimate_gender_from_pitch(f0_hz: f32) -> VoiceGender {
    if f0_hz <= 0.0 {
        VoiceGender::Unknown
    } else if f0_hz < 165.0 {
        VoiceGender::Male
    } else if f0_hz < 260.0 {
        VoiceGender::Female
    } else {
        VoiceGender::Child
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gender_from_pitch() {
        assert_eq!(estimate_gender_from_pitch(120.0), VoiceGender::Male);
        assert_eq!(estimate_gender_from_pitch(210.0), VoiceGender::Female);
        assert_eq!(estimate_gender_from_pitch(300.0), VoiceGender::Child);
    }
}
