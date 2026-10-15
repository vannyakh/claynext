use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BlendMode {
    Normal,
    Multiply,
    Screen,
    Overlay,
    Darken,
    Lighten,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompositorLayer {
    pub id: String,
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub opacity: f32,
    pub blend_mode: BlendMode,
    pub visible: bool,
}

impl Default for CompositorLayer {
    fn default() -> Self {
        Self {
            id: "layer_0".to_string(),
            x: 0.0,
            y: 0.0,
            width: 1.0,
            height: 1.0,
            opacity: 1.0,
            blend_mode: BlendMode::Normal,
            visible: true,
        }
    }
}
