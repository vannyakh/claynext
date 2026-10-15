use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NvencProfile {
    pub codec: String,        // "h264_nvenc", "hevc_nvenc", "av1_nvenc"
    pub preset: String,       // "p1" to "p7" (fastest to highest quality)
    pub rate_control: String, // "cbr", "vbr", "constqp"
    pub tune: String,         // "hq", "ll", "ull", "lossless"
    pub rc_lookahead: u32,
    pub spatial_aq: bool,
    pub temporal_aq: bool,
}

impl Default for NvencProfile {
    fn default() -> Self {
        Self {
            codec: "hevc_nvenc".to_string(),
            preset: "p4".to_string(),
            rate_control: "vbr".to_string(),
            tune: "hq".to_string(),
            rc_lookahead: 32,
            spatial_aq: true,
            temporal_aq: true,
        }
    }
}

impl NvencProfile {
    pub fn to_ffmpeg_args(&self) -> Vec<String> {
        vec![
            "-c:v".to_string(),
            self.codec.clone(),
            "-preset".to_string(),
            self.preset.clone(),
            "-tune".to_string(),
            self.tune.clone(),
            "-rc".to_string(),
            self.rate_control.clone(),
            "-rc-lookahead".to_string(),
            self.rc_lookahead.to_string(),
            "-spatial-aq".to_string(),
            if self.spatial_aq { "1" } else { "0" }.to_string(),
            "-temporal-aq".to_string(),
            if self.temporal_aq { "1" } else { "0" }.to_string(),
        ]
    }
}
