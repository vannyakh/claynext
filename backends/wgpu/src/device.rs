use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WgpuBackendType {
    Vulkan,
    Dx12,
    Metal,
    Gl,
    BrowserWebGpu,
    Primary,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WgpuDeviceInfo {
    pub backend: WgpuBackendType,
    pub adapter_name: String,
    pub max_texture_dimension_2d: u32,
    pub supports_compute_shaders: bool,
    pub preferred_format: String,
}

impl Default for WgpuDeviceInfo {
    fn default() -> Self {
        Self {
            backend: WgpuBackendType::Primary,
            adapter_name: "Auto-Selected GPU Adapter".to_string(),
            max_texture_dimension_2d: 8192,
            supports_compute_shaders: true,
            preferred_format: "Rgba8Unorm".to_string(),
        }
    }
}
