//! editor-audio: Audio ducking curve calculation, volume envelopes, and decibel transformations.

use serde::{Deserialize, Serialize};

/// Audio Ducking configuration for voice-over and background bed.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DuckingConfig {
    pub ducking_db: f32,   // e.g. -14.0 dB
    pub attack_ms: f32,    // e.g. 150.0 ms
    pub release_ms: f32,   // e.g. 400.0 ms
    pub threshold_db: f32, // e.g. -24.0 dB
}

impl Default for DuckingConfig {
    fn default() -> Self {
        Self {
            ducking_db: -14.0,
            attack_ms: 150.0,
            release_ms: 400.0,
            threshold_db: -24.0,
        }
    }
}

/// A speech activity interval that causes background music to duck.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SpeechInterval {
    pub start_seconds: f64,
    pub end_seconds: f64,
}

/// Compute gain multiplier at a specific time given speech intervals and ducking parameters.
pub fn calculate_ducked_gain(
    time_seconds: f64,
    speech_intervals: &[SpeechInterval],
    config: &DuckingConfig,
) -> f32 {
    let ducked_linear = db_to_linear(config.ducking_db);
    let attack_sec = (config.attack_ms / 1000.0) as f64;
    let release_sec = (config.release_ms / 1000.0) as f64;

    for interval in speech_intervals {
        let duck_start = interval.start_seconds - attack_sec;
        let duck_end = interval.end_seconds + release_sec;

        if time_seconds >= duck_start && time_seconds <= duck_end {
            if time_seconds < interval.start_seconds {
                // In attack ramp
                let progress = ((time_seconds - duck_start) / attack_sec).clamp(0.0, 1.0) as f32;
                return 1.0 - progress * (1.0 - ducked_linear);
            } else if time_seconds > interval.end_seconds {
                // In release ramp
                let progress =
                    ((time_seconds - interval.end_seconds) / release_sec).clamp(0.0, 1.0) as f32;
                return ducked_linear + progress * (1.0 - ducked_linear);
            } else {
                // Fully ducked
                return ducked_linear;
            }
        }
    }
    1.0
}

/// Convert Decibels to linear amplitude multiplier.
pub fn db_to_linear(db: f32) -> f32 {
    10.0f32.powf(db / 20.0)
}

/// Convert linear amplitude multiplier to Decibels.
pub fn linear_to_db(linear: f32) -> f32 {
    if linear <= 1e-6 {
        -120.0
    } else {
        20.0 * linear.log10()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_db_conversions() {
        assert_eq!(linear_to_db(1.0), 0.0);
        assert!((db_to_linear(-6.0) - 0.501187).abs() < 1e-4);
    }

    #[test]
    fn test_ducked_gain_levels() {
        let config = DuckingConfig::default();
        let intervals = vec![SpeechInterval {
            start_seconds: 5.0,
            end_seconds: 10.0,
        }];

        // Before interval (un-ducked)
        assert_eq!(calculate_ducked_gain(2.0, &intervals, &config), 1.0);

        // Middle of speech (fully ducked)
        let ducked = calculate_ducked_gain(7.5, &intervals, &config);
        assert!((ducked - db_to_linear(-14.0)).abs() < 1e-4);

        // After release (un-ducked)
        assert_eq!(calculate_ducked_gain(12.0, &intervals, &config), 1.0);
    }
}
