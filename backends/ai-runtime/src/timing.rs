use serde::{Deserialize, Serialize};

/// Speech tempo needed to fit `audio_dur` into `slot_dur`, clamped to [min, max].
pub fn align_speech_speed(
    audio_dur: f64,
    slot_dur: f64,
    min_speed: f32,
    max_speed: f32,
) -> f32 {
    if audio_dur > 0.0 && slot_dur > 0.0 {
        ((audio_dur / slot_dur) as f32).clamp(min_speed, max_speed)
    } else {
        1.0
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlignSpeedResult {
    pub speech_speed: f32,
    pub audio_dur: f64,
    pub slot_dur: f64,
}

pub fn align_speech_speed_result(
    audio_dur: f64,
    slot_dur: f64,
    min_speed: f32,
    max_speed: f32,
) -> AlignSpeedResult {
    AlignSpeedResult {
        speech_speed: align_speech_speed(audio_dur, slot_dur, min_speed, max_speed),
        audio_dur,
        slot_dur,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamps_fast_speech() {
        let s = align_speech_speed(4.0, 2.0, 0.65, 1.85);
        assert!((s - 1.85).abs() < 0.001);
    }

    #[test]
    fn identity_when_matched() {
        let s = align_speech_speed(2.0, 2.0, 0.65, 1.85);
        assert!((s - 1.0).abs() < 0.001);
    }
}
