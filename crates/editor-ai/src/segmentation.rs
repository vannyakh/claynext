use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SegmentationMask {
    pub width: u32,
    pub height: u32,
    pub mask_rle: Vec<u8>,
    pub label: String,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoSegmentTrack {
    pub track_id: u32,
    pub label: String,
    pub keyframes: Vec<SegmentationMask>,
}
