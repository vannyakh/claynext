//! claynext-plugin-exporters: Native Rust export format profiles and FFmpeg argument builders.

use editor_render::RenderProfile;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Trait implemented by export format presets.
pub trait ExporterPlugin: Send + Sync {
    fn id(&self) -> &'static str;
    fn display_name(&self) -> &'static str;
    fn file_extension(&self) -> &'static str;
    fn build_profile(
        &self,
        width: u32,
        height: u32,
        fps_num: i64,
        fps_den: i64,
        output_path: &str,
    ) -> RenderProfile;
}

/// Standard H.264 / AAC MP4 Exporter.
pub struct Mp4H264Exporter;

impl ExporterPlugin for Mp4H264Exporter {
    fn id(&self) -> &'static str {
        "exporter.mp4_h264"
    }

    fn display_name(&self) -> &'static str {
        "MP4 (H.264 / AAC)"
    }

    fn file_extension(&self) -> &'static str {
        "mp4"
    }

    fn build_profile(
        &self,
        width: u32,
        height: u32,
        fps_num: i64,
        fps_den: i64,
        output_path: &str,
    ) -> RenderProfile {
        RenderProfile {
            output_path: output_path.to_string(),
            width,
            height,
            fps_num,
            fps_den,
            video_codec: "libx264".to_string(),
            video_bitrate_kbps: 8000,
            crf: Some(20),
            preset: "medium".to_string(),
            audio_codec: "aac".to_string(),
            audio_bitrate_kbps: 192,
        }
    }
}

/// Apple ProRes High-Quality Editing Master Exporter.
pub struct ProResExporter;

impl ExporterPlugin for ProResExporter {
    fn id(&self) -> &'static str {
        "exporter.prores_mov"
    }

    fn display_name(&self) -> &'static str {
        "QuickTime ProRes 422 (MOV)"
    }

    fn file_extension(&self) -> &'static str {
        "mov"
    }

    fn build_profile(
        &self,
        width: u32,
        height: u32,
        fps_num: i64,
        fps_den: i64,
        output_path: &str,
    ) -> RenderProfile {
        RenderProfile {
            output_path: output_path.to_string(),
            width,
            height,
            fps_num,
            fps_den,
            video_codec: "prores_ks".to_string(),
            video_bitrate_kbps: 150000,
            crf: None,
            preset: "profile=standard".to_string(),
            audio_codec: "pcm_s16le".to_string(),
            audio_bitrate_kbps: 1536,
        }
    }
}

/// Registry of exporter plugins.
pub struct ExporterPluginRegistry {
    plugins: HashMap<String, Box<dyn ExporterPlugin>>,
}

impl Default for ExporterPluginRegistry {
    fn default() -> Self {
        let mut reg = Self {
            plugins: HashMap::new(),
        };
        reg.register(Box::new(Mp4H264Exporter));
        reg.register(Box::new(ProResExporter));
        reg
    }
}

impl ExporterPluginRegistry {
    pub fn register(&mut self, plugin: Box<dyn ExporterPlugin>) {
        self.plugins.insert(plugin.id().to_string(), plugin);
    }

    pub fn get(&self, id: &str) -> Option<&dyn ExporterPlugin> {
        self.plugins.get(id).map(|b| b.as_ref())
    }

    pub fn list(&self) -> Vec<ExporterPluginInfo> {
        self.plugins
            .values()
            .map(|p| ExporterPluginInfo {
                id: p.id().to_string(),
                name: p.display_name().to_string(),
                extension: p.file_extension().to_string(),
            })
            .collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExporterPluginInfo {
    pub id: String,
    pub name: String,
    pub extension: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exporter_profile() {
        let exporter = Mp4H264Exporter;
        let prof = exporter.build_profile(1920, 1080, 30, 1, "render.mp4");
        assert_eq!(prof.width, 1920);
        assert_eq!(prof.video_codec, "libx264");
    }
}
