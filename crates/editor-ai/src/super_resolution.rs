use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SuperResolutionOptions {
    pub scale_factor: u32, // 2 or 4
    pub model_name: String, // "real-esrgan", "compact"
    pub denoise_level: f32,
    pub tile_size: u32,
}

impl Default for SuperResolutionOptions {
    fn default() -> Self {
        Self {
            scale_factor: 2,
            model_name: "real-esrgan".to_string(),
            denoise_level: 0.5,
            tile_size: 256,
        }
    }
}
