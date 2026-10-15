use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoDenoiseOptions {
    pub temporal_strength: f32,
    pub spatial_strength: f32,
    pub preserve_details: bool,
}

impl Default for VideoDenoiseOptions {
    fn default() -> Self {
        Self {
            temporal_strength: 0.6,
            spatial_strength: 0.4,
            preserve_details: true,
        }
    }
}
