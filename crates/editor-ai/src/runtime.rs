use crate::device::AiDeviceDescriptor;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AiRuntimeConfig {
    pub device: AiDeviceDescriptor,
    pub num_worker_threads: usize,
    pub inter_op_threads: usize,
    pub intra_op_threads: usize,
    pub enable_profiling: bool,
}

impl Default for AiRuntimeConfig {
    fn default() -> Self {
        Self {
            device: AiDeviceDescriptor::default(),
            num_worker_threads: 4,
            inter_op_threads: 2,
            intra_op_threads: 4,
            enable_profiling: false,
        }
    }
}
