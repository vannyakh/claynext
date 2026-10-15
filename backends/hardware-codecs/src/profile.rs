use crate::amf::AmfProfile;
use crate::detect::{detect_system_gpus, GpuVendor};
use crate::media_foundation::MediaFoundationProfile;
use crate::nvenc::NvencProfile;
use crate::qsv::QsvProfile;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SelectedCodec {
    Nvenc(NvencProfile),
    Qsv(QsvProfile),
    Amf(AmfProfile),
    MediaFoundation(MediaFoundationProfile),
    CpuSoftware {
        codec: String,
        crf: u32,
        preset: String,
    },
}

impl SelectedCodec {
    pub fn to_ffmpeg_args(&self) -> Vec<String> {
        match self {
            SelectedCodec::Nvenc(p) => p.to_ffmpeg_args(),
            SelectedCodec::Qsv(p) => p.to_ffmpeg_args(),
            SelectedCodec::Amf(p) => p.to_ffmpeg_args(),
            SelectedCodec::MediaFoundation(p) => p.to_ffmpeg_args(),
            SelectedCodec::CpuSoftware { codec, crf, preset } => vec![
                "-c:v".to_string(),
                codec.clone(),
                "-crf".to_string(),
                crf.to_string(),
                "-preset".to_string(),
                preset.clone(),
            ],
        }
    }

    pub fn codec_name(&self) -> &str {
        match self {
            SelectedCodec::Nvenc(p) => &p.codec,
            SelectedCodec::Qsv(p) => &p.codec,
            SelectedCodec::Amf(p) => &p.codec,
            SelectedCodec::MediaFoundation(p) => &p.codec,
            SelectedCodec::CpuSoftware { codec, .. } => codec,
        }
    }
}

pub fn select_optimal_video_encoder(prefer_hevc: bool) -> SelectedCodec {
    let gpus = detect_system_gpus();
    for gpu in gpus {
        match gpu.vendor {
            GpuVendor::Nvidia if gpu.supports_nvenc => {
                let mut profile = NvencProfile::default();
                if !prefer_hevc {
                    profile.codec = "h264_nvenc".to_string();
                }
                return SelectedCodec::Nvenc(profile);
            }
            GpuVendor::Intel if gpu.supports_qsv => {
                let mut profile = QsvProfile::default();
                if !prefer_hevc {
                    profile.codec = "h264_qsv".to_string();
                }
                return SelectedCodec::Qsv(profile);
            }
            GpuVendor::Amd if gpu.supports_amf => {
                let mut profile = AmfProfile::default();
                if !prefer_hevc {
                    profile.codec = "h264_amf".to_string();
                }
                return SelectedCodec::Amf(profile);
            }
            _ => {}
        }
    }

    // Fallback to CPU Software (libx264/libx265)
    SelectedCodec::CpuSoftware {
        codec: if prefer_hevc {
            "libx265".to_string()
        } else {
            "libx264".to_string()
        },
        crf: 20,
        preset: "faster".to_string(),
    }
}
