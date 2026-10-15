use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectedObject {
    pub label: String,
    pub confidence: f32,
    pub bbox: [f32; 4], // [x, y, w, h] normalized
    pub track_id: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObjectDetectionOptions {
    pub confidence_threshold: f32,
    pub nms_threshold: f32,
    pub track_objects: bool,
}

impl Default for ObjectDetectionOptions {
    fn default() -> Self {
        Self {
            confidence_threshold: 0.5,
            nms_threshold: 0.45,
            track_objects: true,
        }
    }
}
