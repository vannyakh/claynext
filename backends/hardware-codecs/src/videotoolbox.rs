use serde::{Deserialize, Serialize};

/// Apple VideoToolbox hardware encode profile (macOS / Apple Silicon).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoToolboxProfile {
    pub codec: String, // "h264_videotoolbox", "hevc_videotoolbox"
    pub allow_sw: bool,
    pub realtime: bool,
    /// Average bitrate in bits/s when set (VideoToolbox prefers bitrate over CRF).
    pub bitrate: Option<String>,
}

impl Default for VideoToolboxProfile {
    fn default() -> Self {
        Self {
            codec: "hevc_videotoolbox".to_string(),
            allow_sw: true,
            realtime: false,
            bitrate: Some("8M".to_string()),
        }
    }
}

impl VideoToolboxProfile {
    pub fn to_ffmpeg_args(&self) -> Vec<String> {
        let mut args = vec!["-c:v".to_string(), self.codec.clone()];
        if self.allow_sw {
            args.extend(["-allow_sw".to_string(), "1".to_string()]);
        }
        if self.realtime {
            args.extend(["-realtime".to_string(), "1".to_string()]);
        }
        if let Some(br) = &self.bitrate {
            args.extend(["-b:v".to_string(), br.clone()]);
        }
        args
    }
}
