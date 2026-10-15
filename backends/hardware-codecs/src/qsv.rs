use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QsvProfile {
    pub codec: String,  // "h264_qsv", "hevc_qsv", "av1_qsv"
    pub preset: String, // "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"
    pub global_quality: u32,
    pub look_ahead: bool,
}

impl Default for QsvProfile {
    fn default() -> Self {
        Self {
            codec: "hevc_qsv".to_string(),
            preset: "medium".to_string(),
            global_quality: 23,
            look_ahead: true,
        }
    }
}

impl QsvProfile {
    pub fn to_ffmpeg_args(&self) -> Vec<String> {
        vec![
            "-c:v".to_string(),
            self.codec.clone(),
            "-preset".to_string(),
            self.preset.clone(),
            "-global_quality".to_string(),
            self.global_quality.to_string(),
            "-look_ahead".to_string(),
            if self.look_ahead { "1" } else { "0" }.to_string(),
        ]
    }
}
