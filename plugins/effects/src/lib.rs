//! claynext-plugin-effects: Extensible Rust plugin architecture for video effects and color filters.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Metadata describing an effect plugin parameter.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EffectParameter {
    pub name: String,
    pub description: String,
    pub min_value: f32,
    pub max_value: f32,
    pub default_value: f32,
}

/// Dynamic trait implemented by all video effect plugins.
pub trait EffectPlugin: Send + Sync {
    fn id(&self) -> &'static str;
    fn display_name(&self) -> &'static str;
    fn category(&self) -> &'static str;
    fn parameters(&self) -> Vec<EffectParameter>;
    fn apply_rgba8(
        &self,
        buffer: &mut [u8],
        width: u32,
        height: u32,
        params: &HashMap<String, f32>,
    );
}

/// Grayscale transformation plugin.
pub struct GrayscaleEffect;

impl EffectPlugin for GrayscaleEffect {
    fn id(&self) -> &'static str {
        "builtin.grayscale"
    }

    fn display_name(&self) -> &'static str {
        "Grayscale"
    }

    fn category(&self) -> &'static str {
        "Color"
    }

    fn parameters(&self) -> Vec<EffectParameter> {
        vec![EffectParameter {
            name: "intensity".to_string(),
            description: "Grayscale blend intensity (0.0 to 1.0)".to_string(),
            min_value: 0.0,
            max_value: 1.0,
            default_value: 1.0,
        }]
    }

    fn apply_rgba8(
        &self,
        buffer: &mut [u8],
        _width: u32,
        _height: u32,
        params: &HashMap<String, f32>,
    ) {
        let intensity = params
            .get("intensity")
            .copied()
            .unwrap_or(1.0)
            .clamp(0.0, 1.0);
        if intensity <= 0.0 {
            return;
        }

        for chunk in buffer.chunks_exact_mut(4) {
            let r = chunk[0] as f32;
            let g = chunk[1] as f32;
            let b = chunk[2] as f32;
            // Rec. 709 luminance weights
            let luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;

            chunk[0] = ((1.0 - intensity) * r + intensity * luma).round() as u8;
            chunk[1] = ((1.0 - intensity) * g + intensity * luma).round() as u8;
            chunk[2] = ((1.0 - intensity) * b + intensity * luma).round() as u8;
        }
    }
}

/// Brightness and Contrast plugin.
pub struct BrightnessContrastEffect;

impl EffectPlugin for BrightnessContrastEffect {
    fn id(&self) -> &'static str {
        "builtin.brightness_contrast"
    }

    fn display_name(&self) -> &'static str {
        "Brightness & Contrast"
    }

    fn category(&self) -> &'static str {
        "Adjust"
    }

    fn parameters(&self) -> Vec<EffectParameter> {
        vec![
            EffectParameter {
                name: "brightness".to_string(),
                description: "Brightness offset (-100 to 100)".to_string(),
                min_value: -100.0,
                max_value: 100.0,
                default_value: 0.0,
            },
            EffectParameter {
                name: "contrast".to_string(),
                description: "Contrast multiplier (0.0 to 3.0)".to_string(),
                min_value: 0.0,
                max_value: 3.0,
                default_value: 1.0,
            },
        ]
    }

    fn apply_rgba8(
        &self,
        buffer: &mut [u8],
        _width: u32,
        _height: u32,
        params: &HashMap<String, f32>,
    ) {
        let brightness = params.get("brightness").copied().unwrap_or(0.0);
        let contrast = params.get("contrast").copied().unwrap_or(1.0);

        for chunk in buffer.chunks_exact_mut(4) {
            for item in chunk.iter_mut().take(3) {
                let val = *item as f32;
                let adjusted = ((val - 128.0) * contrast + 128.0 + brightness).clamp(0.0, 255.0);
                *item = adjusted as u8;
            }
        }
    }
}

/// Registry of available effect plugins.
pub struct EffectPluginRegistry {
    plugins: HashMap<String, Box<dyn EffectPlugin>>,
}

impl Default for EffectPluginRegistry {
    fn default() -> Self {
        let mut reg = Self {
            plugins: HashMap::new(),
        };
        reg.register(Box::new(GrayscaleEffect));
        reg.register(Box::new(BrightnessContrastEffect));
        reg
    }
}

impl EffectPluginRegistry {
    pub fn register(&mut self, plugin: Box<dyn EffectPlugin>) {
        self.plugins.insert(plugin.id().to_string(), plugin);
    }

    pub fn get(&self, id: &str) -> Option<&dyn EffectPlugin> {
        self.plugins.get(id).map(|b| b.as_ref())
    }

    pub fn list(&self) -> Vec<EffectPluginInfo> {
        self.plugins
            .values()
            .map(|p| EffectPluginInfo {
                id: p.id().to_string(),
                name: p.display_name().to_string(),
                category: p.category().to_string(),
                parameters: p.parameters(),
            })
            .collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EffectPluginInfo {
    pub id: String,
    pub name: String,
    pub category: String,
    pub parameters: Vec<EffectParameter>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_grayscale_effect() {
        let effect = GrayscaleEffect;
        let mut frame = vec![255, 0, 0, 255]; // Red pixel
        let mut params = HashMap::new();
        params.insert("intensity".to_string(), 1.0);

        effect.apply_rgba8(&mut frame, 1, 1, &params);
        // Red 255 * 0.2126 = ~54
        assert!((frame[0] as i32 - 54).abs() <= 1);
        assert_eq!(frame[0], frame[1]);
        assert_eq!(frame[1], frame[2]);
    }
}
