use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoEnhancementOptions {
    pub auto_color_grade: bool,
    pub hdr_tonemap: bool,
    pub face_restoration: bool,
    pub sharpness: f32,
    pub saturation_boost: f32,
}

impl Default for VideoEnhancementOptions {
    fn default() -> Self {
        Self {
            auto_color_grade: true,
            hdr_tonemap: false,
            face_restoration: true,
            sharpness: 1.2,
            saturation_boost: 1.05,
        }
    }
}
