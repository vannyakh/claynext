use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackgroundRemovalOptions {
    pub model_name: String,
    pub threshold: f32,
    pub feather_radius_px: u32,
    pub return_mask_only: bool,
}

impl Default for BackgroundRemovalOptions {
    fn default() -> Self {
        Self {
            model_name: "birefnet".to_string(),
            threshold: 0.5,
            feather_radius_px: 2,
            return_mask_only: false,
        }
    }
}
