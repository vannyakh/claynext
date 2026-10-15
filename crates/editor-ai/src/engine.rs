use crate::jobs::AiJobQueue;
use crate::model_registry::ModelRegistry;
use crate::runtime::AiRuntimeConfig;
use std::sync::Arc;

pub struct AiEngine {
    pub registry: Arc<ModelRegistry>,
    pub jobs: Arc<AiJobQueue>,
    pub runtime_config: AiRuntimeConfig,
}

impl Default for AiEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl AiEngine {
    pub fn new() -> Self {
        Self {
            registry: Arc::new(ModelRegistry::new()),
            jobs: Arc::new(AiJobQueue::new()),
            runtime_config: AiRuntimeConfig::default(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ai_engine_initialization() {
        let engine = AiEngine::new();
        let models = engine.registry.list_models();
        assert!(!models.is_empty());
        let job_id = engine.jobs.submit_job("Transcribe Video", "asr");
        assert!(!job_id.is_empty());
    }
}
