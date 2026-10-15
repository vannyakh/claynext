//! editor-media: Media stream metadata, waveform decimation, and format detection.

use editor_types::Rational;
use serde::{Deserialize, Serialize};

/// High-level media stream inspection result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MediaInspection {
    pub file_path: String,
    pub format_name: String,
    pub duration_seconds: f64,
    pub size_bytes: u64,
    pub bit_rate: u64,
    pub video_streams: Vec<VideoStreamInfo>,
    pub audio_streams: Vec<AudioStreamInfo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoStreamInfo {
    pub index: usize,
    pub codec_name: String,
    pub width: u32,
    pub height: u32,
    pub frame_rate: Rational,
    pub pixel_format: String,
    pub duration_seconds: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioStreamInfo {
    pub index: usize,
    pub codec_name: String,
    pub sample_rate: u32,
    pub channels: u32,
    pub duration_seconds: f64,
}

/// Waveform peak bin for rapid UI audio scrubbing visualization.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WaveformPeak {
    pub min_sample: f32, // -1.0 .. 0.0
    pub max_sample: f32, //  0.0 .. 1.0
    pub rms: f32,
}

/// Decimate raw PCM samples into `target_bins` peaks for UI waveform visualizer.
pub fn generate_waveform_peaks(samples: &[f32], target_bins: usize) -> Vec<WaveformPeak> {
    if samples.is_empty() || target_bins == 0 {
        return Vec::new();
    }

    let bin_size = (samples.len() as f64 / target_bins as f64).max(1.0);
    let mut peaks = Vec::with_capacity(target_bins);

    for i in 0..target_bins {
        let start = (i as f64 * bin_size) as usize;
        let end = (((i + 1) as f64 * bin_size) as usize).min(samples.len());

        if start >= samples.len() {
            break;
        }

        let slice = &samples[start..end];
        if slice.is_empty() {
            peaks.push(WaveformPeak {
                min_sample: 0.0,
                max_sample: 0.0,
                rms: 0.0,
            });
            continue;
        }

        let mut min = 0.0f32;
        let mut max = 0.0f32;
        let mut sum_sq = 0.0f32;

        for &s in slice {
            if s < min {
                min = s;
            }
            if s > max {
                max = s;
            }
            sum_sq += s * s;
        }

        let rms = (sum_sq / slice.len() as f32).sqrt();
        peaks.push(WaveformPeak {
            min_sample: min,
            max_sample: max,
            rms,
        });
    }

    peaks
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_waveform_binning() {
        let samples = vec![-0.5, 0.8, -0.2, 0.4, -0.9, 0.1];
        let peaks = generate_waveform_peaks(&samples, 2);
        assert_eq!(peaks.len(), 2);
        assert_eq!(peaks[0].min_sample, -0.5);
        assert_eq!(peaks[0].max_sample, 0.8);
    }
}
