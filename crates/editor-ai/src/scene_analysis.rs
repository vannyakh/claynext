use editor_types::Rational;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SceneCut {
    pub timestamp: Rational,
    pub confidence: f32,
    pub transition_type: String, // "cut", "dissolve", "fade"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SceneAnalysisOptions {
    pub threshold: f32,
    pub min_scene_duration_sec: f32,
}

impl Default for SceneAnalysisOptions {
    fn default() -> Self {
        Self {
            threshold: 0.35,
            min_scene_duration_sec: 1.0,
        }
    }
}
