use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MediaFoundationProfile {
    pub codec: String,        // "h264_mf", "hevc_mf", "av1_mf"
    pub rate_control: String, // "cbr", "vbr", "quality"
    pub quality: u32,         // 1 - 100
}

impl Default for MediaFoundationProfile {
    fn default() -> Self {
        Self {
            codec: "hevc_mf".to_string(),
            rate_control: "quality".to_string(),
            quality: 75,
        }
    }
}

impl MediaFoundationProfile {
    pub fn to_ffmpeg_args(&self) -> Vec<String> {
        vec![
            "-c:v".to_string(),
            self.codec.clone(),
            "-rc".to_string(),
            self.rate_control.clone(),
            "-quality".to_string(),
            self.quality.to_string(),
        ]
    }
}
