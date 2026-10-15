/// Calculate peak amplitude and RMS level of an audio slice
pub fn compute_audio_stats(samples: &[f32]) -> (f32, f32) {
    if samples.is_empty() {
        return (0.0, 0.0);
    }

    let mut peak: f32 = 0.0;
    let mut sum_sq: f64 = 0.0;

    for &s in samples {
        let abs = s.abs();
        if abs > peak {
            peak = abs;
        }
        sum_sq += (s as f64) * (s as f64);
    }

    let rms = (sum_sq / samples.len() as f64).sqrt() as f32;
    (peak, rms)
}

/// Downsample audio samples into discrete waveform visualizer peak bins
pub fn extract_waveform_peaks(samples: &[f32], target_bins: usize) -> Vec<f32> {
    if samples.is_empty() || target_bins == 0 {
        return vec![0.0; target_bins];
    }

    let chunk_size = (samples.len() as f64 / target_bins as f64).max(1.0);
    let mut peaks = Vec::with_capacity(target_bins);

    for bin in 0..target_bins {
        let start = (bin as f64 * chunk_size) as usize;
        let end = (((bin + 1) as f64 * chunk_size) as usize).min(samples.len());

        let mut max_val: f32 = 0.0;
        for &sample in &samples[start..end] {
            let v = sample.abs();
            if v > max_val {
                max_val = v;
            }
        }
        peaks.push(max_val.min(1.0));
    }

    peaks
}
