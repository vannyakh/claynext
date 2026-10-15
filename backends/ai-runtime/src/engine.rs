use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ExecutionProvider {
    Cuda,
    DirectML,
    CoreML,
    OpenVino,
    TensorRT,
    Cpu,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceDeviceConfig {
    pub provider: ExecutionProvider,
    pub device_id: i32,
    pub num_threads: usize,
    pub enable_fp16: bool,
    pub memory_limit_mb: Option<usize>,
}

impl Default for InferenceDeviceConfig {
    fn default() -> Self {
        Self {
            provider: ExecutionProvider::DirectML,
            device_id: 0,
            num_threads: 4,
            enable_fp16: true,
            memory_limit_mb: None,
        }
    }
}
