use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ModelProviderKind {
    HuggingFace,
    Ollama,
    OnnxRuntime,
    LocalPath,
    CloudEndpoint,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelProviderConfig {
    pub kind: ModelProviderKind,
    pub base_url: Option<String>,
    pub api_key_env: Option<String>,
    pub timeout_seconds: u32,
    pub retry_count: u32,
}

impl Default for ModelProviderConfig {
    fn default() -> Self {
        Self {
            kind: ModelProviderKind::HuggingFace,
            base_url: Some("https://huggingface.co".to_string()),
            api_key_env: Some("HF_TOKEN".to_string()),
            timeout_seconds: 60,
            retry_count: 3,
        }
    }
}
