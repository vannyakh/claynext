//! editor-effects: Color grading, video adjustments, and FFmpeg filter-graph string builders.

use serde::{Deserialize, Serialize};

/// Color grading and enhancement parameters.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct VideoAdjustments {
    pub brightness: f32,  // -1.0 .. 1.0 (0.0 = neutral)
    pub contrast: f32,    // -1000.0 .. 1000.0 (1.0 = neutral)
    pub saturation: f32,  // 0.0 .. 3.0 (1.0 = neutral)
    pub gamma: f32,       // 0.1 .. 10.0 (1.0 = neutral)
    pub temperature: f32, // -100.0 .. 100.0 (0.0 = neutral)
    pub vignette: f32,    // 0.0 .. 1.0
}

impl Default for VideoAdjustments {
    fn default() -> Self {
        Self {
            brightness: 0.0,
            contrast: 1.0,
            saturation: 1.0,
            gamma: 1.0,
            temperature: 0.0,
            vignette: 0.0,
        }
    }
}

impl VideoAdjustments {
    /// Generate an FFmpeg `eq` filter expression.
    pub fn to_ffmpeg_eq_filter(&self) -> Option<String> {
        let is_neutral = (self.brightness.abs() < 1e-3)
            && ((self.contrast - 1.0).abs() < 1e-3)
            && ((self.saturation - 1.0).abs() < 1e-3)
            && ((self.gamma - 1.0).abs() < 1e-3);

        if is_neutral {
            None
        } else {
            Some(format!(
                "eq=brightness={:.3}:contrast={:.3}:saturation={:.3}:gamma={:.3}",
                self.brightness, self.contrast, self.saturation, self.gamma
            ))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_filter_generation() {
        let mut adj = VideoAdjustments::default();
        assert!(adj.to_ffmpeg_eq_filter().is_none());

        adj.contrast = 1.2;
        adj.saturation = 1.1;
        let filter = adj.to_ffmpeg_eq_filter().unwrap();
        assert!(filter.contains("contrast=1.200"));
        assert!(filter.contains("saturation=1.100"));
    }
}
