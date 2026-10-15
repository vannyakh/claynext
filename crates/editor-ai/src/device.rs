use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AiDeviceKind {
    Cpu,
    Cuda,
    DirectMl,
    Metal,
    CoreMl,
    OpenVino,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AiDeviceDescriptor {
    pub kind: AiDeviceKind,
    pub name: String,
    pub index: u32,
    pub total_memory_mb: usize,
    pub available_memory_mb: usize,
    pub supports_fp16: bool,
    pub supports_int8: bool,
}

impl Default for AiDeviceDescriptor {
    fn default() -> Self {
        Self {
            kind: AiDeviceKind::DirectMl,
            name: "Default DirectML Device".to_string(),
            index: 0,
            total_memory_mb: 8192,
            available_memory_mb: 6144,
            supports_fp16: true,
            supports_int8: true,
        }
    }
}
