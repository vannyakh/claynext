use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioTrackMix {
    pub volume: f32,
    pub pan: f32, // -1.0 (Left) to +1.0 (Right)
    pub muted: bool,
}

impl Default for AudioTrackMix {
    fn default() -> Self {
        Self {
            volume: 1.0,
            pan: 0.0,
            muted: false,
        }
    }
}

/// Mix two mono audio buffers with individual track gains and ducking envelope
pub fn mix_tracks(
    track_a: &[f32],
    gain_a: f32,
    track_b: &[f32],
    gain_b: f32,
    ducking_b_on_a: Option<&[f32]>, // duck factor [0.0..1.0] applied to track_a
) -> Vec<f32> {
    let max_len = track_a.len().max(track_b.len());
    let mut mixed = Vec::with_capacity(max_len);

    for i in 0..max_len {
        let mut sample_a = if i < track_a.len() {
            track_a[i] * gain_a
        } else {
            0.0
        };
        if let Some(duck) = ducking_b_on_a {
            if i < duck.len() {
                sample_a *= duck[i];
            }
        }

        let sample_b = if i < track_b.len() {
            track_b[i] * gain_b
        } else {
            0.0
        };

        // Soft-clipping mix
        let sum = sample_a + sample_b;
        let clamped = sum.clamp(-1.0, 1.0);
        mixed.push(clamped);
    }

    mixed
}
