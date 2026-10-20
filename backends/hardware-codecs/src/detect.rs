use serde::{Deserialize, Serialize};

#[cfg(target_os = "windows")]
use std::process::Command;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GpuVendor {
    Nvidia,
    Amd,
    Intel,
    Apple,
    Qualcomm,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GpuDevice {
    pub name: String,
    pub vendor: GpuVendor,
    pub driver_version: Option<String>,
    pub supports_nvenc: bool,
    pub supports_nvdec: bool,
    pub supports_qsv: bool,
    pub supports_amf: bool,
    pub supports_d3d11va: bool,
    /// Apple VideoToolbox encode/decode (macOS).
    #[serde(default)]
    pub supports_videotoolbox: bool,
}

pub fn detect_system_gpus() -> Vec<GpuDevice> {
    let mut gpus = Vec::new();

    #[cfg(target_os = "macos")]
    {
        let chip = std::process::Command::new("sysctl")
            .args(["-n", "machdep.cpu.brand_string"])
            .output()
            .ok()
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "Apple GPU".to_string());

        gpus.push(GpuDevice {
            name: chip,
            vendor: GpuVendor::Apple,
            driver_version: None,
            supports_nvenc: false,
            supports_nvdec: false,
            supports_qsv: false,
            supports_amf: false,
            supports_d3d11va: false,
            supports_videotoolbox: true,
        });
    }

    #[cfg(target_os = "windows")]
    {
        // Query PowerShell for video controllers on Windows
        if let Ok(output) = Command::new("powershell")
            .args([
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -Property Name, DriverVersion | ConvertTo-Json",
            ])
            .output()
        {
            if let Ok(json_str) = String::from_utf8(output.stdout) {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&json_str) {
                    let items = if let Some(arr) = val.as_array() {
                        arr.clone()
                    } else if val.is_object() {
                        vec![val]
                    } else {
                        vec![]
                    };

                    for item in items {
                        let name = item["Name"].as_str().unwrap_or("Unknown GPU").to_string();
                        let driver = item["DriverVersion"].as_str().map(|s| s.to_string());
                        let name_lower = name.to_lowercase();

                        let vendor = if name_lower.contains("nvidia")
                            || name_lower.contains("geforce")
                            || name_lower.contains("rtx")
                            || name_lower.contains("quadro")
                        {
                            GpuVendor::Nvidia
                        } else if name_lower.contains("amd") || name_lower.contains("radeon") {
                            GpuVendor::Amd
                        } else if name_lower.contains("intel")
                            || name_lower.contains("arc")
                            || name_lower.contains("uhd")
                            || name_lower.contains("iris")
                        {
                            GpuVendor::Intel
                        } else {
                            GpuVendor::Unknown
                        };

                        gpus.push(GpuDevice {
                            name,
                            vendor,
                            driver_version: driver,
                            supports_nvenc: vendor == GpuVendor::Nvidia,
                            supports_nvdec: vendor == GpuVendor::Nvidia,
                            supports_qsv: vendor == GpuVendor::Intel,
                            supports_amf: vendor == GpuVendor::Amd,
                            supports_d3d11va: true,
                            supports_videotoolbox: false,
                        });
                    }
                }
            }
        }
    }

    if gpus.is_empty() {
        gpus.push(GpuDevice {
            name: "Software / CPU Fallback".to_string(),
            vendor: GpuVendor::Unknown,
            driver_version: None,
            supports_nvenc: false,
            supports_nvdec: false,
            supports_qsv: false,
            supports_amf: false,
            supports_d3d11va: false,
            supports_videotoolbox: false,
        });
    }

    gpus
}
