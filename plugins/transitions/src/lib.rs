//! claynext-plugin-transitions: Native Rust transition plugins for real-time video blending.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Trait for transition renderers between two video frames.
pub trait TransitionPlugin: Send + Sync {
    fn id(&self) -> &'static str;
    fn display_name(&self) -> &'static str;
    fn render(
        &self,
        frame_a: &[u8],
        frame_b: &[u8],
        out_frame: &mut [u8],
        width: u32,
        height: u32,
        progress: f32, // 0.0 (all A) to 1.0 (all B)
    );
}

/// Cross-dissolve alpha blend transition.
pub struct CrossDissolveTransition;

impl TransitionPlugin for CrossDissolveTransition {
    fn id(&self) -> &'static str {
        "builtin.cross_dissolve"
    }

    fn display_name(&self) -> &'static str {
        "Cross Dissolve"
    }

    fn render(
        &self,
        frame_a: &[u8],
        frame_b: &[u8],
        out_frame: &mut [u8],
        _width: u32,
        _height: u32,
        progress: f32,
    ) {
        let p = progress.clamp(0.0, 1.0);
        let inv_p = 1.0 - p;

        let len = frame_a.len().min(frame_b.len()).min(out_frame.len());
        for i in 0..len {
            let a = frame_a[i] as f32;
            let b = frame_b[i] as f32;
            out_frame[i] = (a * inv_p + b * p).round() as u8;
        }
    }
}

/// Wipe Left-to-Right transition.
pub struct WipeLeftTransition;

impl TransitionPlugin for WipeLeftTransition {
    fn id(&self) -> &'static str {
        "builtin.wipe_left"
    }

    fn display_name(&self) -> &'static str {
        "Wipe Left"
    }

    fn render(
        &self,
        frame_a: &[u8],
        frame_b: &[u8],
        out_frame: &mut [u8],
        width: u32,
        height: u32,
        progress: f32,
    ) {
        let split_x = (width as f32 * progress.clamp(0.0, 1.0)).round() as u32;

        for y in 0..height {
            for x in 0..width {
                let idx = ((y * width + x) * 4) as usize;
                if idx + 3 < out_frame.len() && idx + 3 < frame_a.len() && idx + 3 < frame_b.len() {
                    let src = if x < split_x {
                        &frame_b[idx..idx + 4]
                    } else {
                        &frame_a[idx..idx + 4]
                    };
                    out_frame[idx..idx + 4].copy_from_slice(src);
                }
            }
        }
    }
}

/// Registry of transition plugins.
pub struct TransitionPluginRegistry {
    plugins: HashMap<String, Box<dyn TransitionPlugin>>,
}

impl Default for TransitionPluginRegistry {
    fn default() -> Self {
        let mut reg = Self {
            plugins: HashMap::new(),
        };
        reg.register(Box::new(CrossDissolveTransition));
        reg.register(Box::new(WipeLeftTransition));
        reg
    }
}

impl TransitionPluginRegistry {
    pub fn register(&mut self, plugin: Box<dyn TransitionPlugin>) {
        self.plugins.insert(plugin.id().to_string(), plugin);
    }

    pub fn get(&self, id: &str) -> Option<&dyn TransitionPlugin> {
        self.plugins.get(id).map(|b| b.as_ref())
    }

    pub fn list(&self) -> Vec<TransitionPluginInfo> {
        self.plugins
            .values()
            .map(|p| TransitionPluginInfo {
                id: p.id().to_string(),
                name: p.display_name().to_string(),
            })
            .collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransitionPluginInfo {
    pub id: String,
    pub name: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cross_dissolve() {
        let plugin = CrossDissolveTransition;
        let a = vec![200, 200, 200, 255];
        let b = vec![100, 100, 100, 255];
        let mut out = vec![0, 0, 0, 0];

        plugin.render(&a, &b, &mut out, 1, 1, 0.5);
        assert_eq!(out[0], 150);
        assert_eq!(out[1], 150);
        assert_eq!(out[2], 150);
    }
}
