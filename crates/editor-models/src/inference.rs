use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum DeviceTarget {
    #[default]
    Auto,
    Cpu,
    Cuda { device_id: u32 },
    DirectMl { device_id: u32 },
    Metal,
    CoreMl,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceSessionOptions {
    pub device: DeviceTarget,
    pub threads: usize,
    pub fp16_enabled: bool,
    pub max_batch_size: usize,
}

impl Default for InferenceSessionOptions {
    fn default() -> Self {
        Self {
            device: DeviceTarget::Auto,
            threads: 4,
            fp16_enabled: true,
            max_batch_size: 8,
        }
    }
}
