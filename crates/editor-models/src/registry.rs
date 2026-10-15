use crate::error::ModelError;
use crate::providers::{ModelProviderConfig, ModelProviderKind};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::RwLock;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelMetadata {
    pub id: String,
    pub name: String,
    pub description: String,
    pub provider: ModelProviderKind,
    pub local_filename: String,
    pub size_bytes: u64,
    pub sha256: Option<String>,
    pub required_device_memory_mb: usize,
}

pub struct ModelRegistry {
    models: RwLock<HashMap<String, ModelMetadata>>,
    providers: RwLock<HashMap<String, ModelProviderConfig>>,
}

impl Default for ModelRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl ModelRegistry {
    pub fn new() -> Self {
        let registry = Self {
            models: RwLock::new(HashMap::new()),
            providers: RwLock::new(HashMap::new()),
        };
        registry.register_builtin_models();
        registry
    }

    pub fn register_model(&self, metadata: ModelMetadata) {
        let mut lock = self.models.write().unwrap();
        lock.insert(metadata.id.clone(), metadata);
    }

    pub fn register_provider(&self, name: &str, config: ModelProviderConfig) {
        let mut lock = self.providers.write().unwrap();
        lock.insert(name.to_string(), config);
    }

    pub fn get_provider(&self, name: &str) -> Option<ModelProviderConfig> {
        let lock = self.providers.read().unwrap();
        lock.get(name).cloned()
    }

    pub fn get_model(&self, model_id: &str) -> Result<ModelMetadata, ModelError> {
        let lock = self.models.read().unwrap();
        lock.get(model_id)
            .cloned()
            .ok_or_else(|| ModelError::NotFound(model_id.to_string()))
    }

    pub fn list_models(&self) -> Vec<ModelMetadata> {
        let lock = self.models.read().unwrap();
        lock.values().cloned().collect()
    }

    fn register_builtin_models(&self) {
        let builtins = vec![
            ModelMetadata {
                id: "whisper-medium".to_string(),
                name: "Whisper Medium ASR".to_string(),
                description: "Multilingual speech transcription model".to_string(),
                provider: ModelProviderKind::HuggingFace,
                local_filename: "whisper-medium.bin".to_string(),
                size_bytes: 1_500_000_000,
                sha256: None,
                required_device_memory_mb: 2048,
            },
            ModelMetadata {
                id: "silero-vad".to_string(),
                name: "Silero Voice Activity Detector".to_string(),
                description: "Lightweight neural voice chunking model".to_string(),
                provider: ModelProviderKind::OnnxRuntime,
                local_filename: "silero_vad.onnx".to_string(),
                size_bytes: 5_000_000,
                sha256: None,
                required_device_memory_mb: 256,
            },
            ModelMetadata {
                id: "htdemucs".to_string(),
                name: "HTDemucs Audio Stems".to_string(),
                description: "Speech, vocals, music and noise stem separator".to_string(),
                provider: ModelProviderKind::HuggingFace,
                local_filename: "htdemucs.onnx".to_string(),
                size_bytes: 120_000_000,
                sha256: None,
                required_device_memory_mb: 1024,
            },
        ];

        for m in builtins {
            self.register_model(m);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_model_registry() {
        let reg = ModelRegistry::new();
        let models = reg.list_models();
        assert!(models.len() >= 3);
        let whisper = reg.get_model("whisper-medium").unwrap();
        assert_eq!(whisper.required_device_memory_mb, 2048);
    }
}
