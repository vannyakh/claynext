use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AmfProfile {
    pub codec: String,   // "h264_amf", "hevc_amf", "av1_amf"
    pub usage: String,   // "transcoding", "ultralowlatency", "lowlatency", "webcam"
    pub quality: String, // "speed", "balanced", "quality"
    pub rc: String,      // "cbr", "vbr_latency", "vbr_peak"
}

impl Default for AmfProfile {
    fn default() -> Self {
        Self {
            codec: "hevc_amf".to_string(),
            usage: "transcoding".to_string(),
            quality: "quality".to_string(),
            rc: "vbr_peak".to_string(),
        }
    }
}

impl AmfProfile {
    pub fn to_ffmpeg_args(&self) -> Vec<String> {
        vec![
            "-c:v".to_string(),
            self.codec.clone(),
            "-usage".to_string(),
            self.usage.clone(),
            "-quality".to_string(),
            self.quality.clone(),
            "-rc".to_string(),
            self.rc.clone(),
        ]
    }
}
