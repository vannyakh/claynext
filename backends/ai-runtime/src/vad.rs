use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VadSegment {
    pub start_sec: f64,
    pub end_sec: f64,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VadConfig {
    pub threshold: f32,
    pub min_speech_duration_ms: u32,
    pub min_silence_duration_ms: u32,
    pub speech_pad_ms: u32,
}

impl Default for VadConfig {
    fn default() -> Self {
        Self {
            threshold: 0.5,
            min_speech_duration_ms: 250,
            min_silence_duration_ms: 300,
            speech_pad_ms: 100,
        }
    }
}

/// Simple energy-based Voice Activity Detection fallback for audio chunking
pub fn energy_vad_chunking(
    samples: &[f32],
    sample_rate: u32,
    config: &VadConfig,
) -> Vec<VadSegment> {
    if samples.is_empty() || sample_rate == 0 {
        return Vec::new();
    }

    let frame_size = (sample_rate as f32 * 0.03) as usize; // 30ms frames
    if frame_size == 0 {
        return Vec::new();
    }

    let mut segments = Vec::new();
    let mut in_speech = false;
    let mut speech_start_frame = 0;

    let num_frames = samples.len() / frame_size;
    for i in 0..num_frames {
        let frame = &samples[i * frame_size..(i + 1) * frame_size];
        let energy: f32 = frame.iter().map(|s| s * s).sum::<f32>() / frame_size as f32;
        let is_voice = energy > (config.threshold * 0.01);

        if is_voice && !in_speech {
            in_speech = true;
            speech_start_frame = i;
        } else if !is_voice && in_speech {
            in_speech = false;
            let start_sec = (speech_start_frame * frame_size) as f64 / sample_rate as f64;
            let end_sec = (i * frame_size) as f64 / sample_rate as f64;
            if (end_sec - start_sec) * 1000.0 >= config.min_speech_duration_ms as f64 {
                segments.push(VadSegment {
                    start_sec,
                    end_sec,
                    confidence: 0.85,
                });
            }
        }
    }

    if in_speech {
        let start_sec = (speech_start_frame * frame_size) as f64 / sample_rate as f64;
        let end_sec = samples.len() as f64 / sample_rate as f64;
        segments.push(VadSegment {
            start_sec,
            end_sec,
            confidence: 0.85,
        });
    }

    segments
}
