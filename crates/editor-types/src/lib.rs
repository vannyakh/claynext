//! editor-types: Foundational types, identifiers, and math primitives for Claynext Studio.

use serde::{Deserialize, Serialize};
use std::fmt;
use uuid::Uuid;

/// Strongly typed project ID.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ProjectId(pub Uuid);

impl ProjectId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl Default for ProjectId {
    fn default() -> Self {
        Self::new()
    }
}

/// Strongly typed track ID.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TrackId(pub Uuid);

impl TrackId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl Default for TrackId {
    fn default() -> Self {
        Self::new()
    }
}

/// Strongly typed clip ID.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ClipId(pub Uuid);

impl ClipId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl Default for ClipId {
    fn default() -> Self {
        Self::new()
    }
}

/// Strongly typed marker ID.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct MarkerId(pub Uuid);

impl MarkerId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl Default for MarkerId {
    fn default() -> Self {
        Self::new()
    }
}

/// Rational number representing frame rates and time bases (e.g. 30/1, 24000/1001).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Rational {
    pub num: i64,
    pub den: i64,
}

impl Rational {
    pub const fn new(num: i64, den: i64) -> Self {
        Self { num, den }
    }

    pub fn to_f64(self) -> f64 {
        if self.den == 0 {
            0.0
        } else {
            self.num as f64 / self.den as f64
        }
    }
}

impl fmt::Display for Rational {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}/{}", self.num, self.den)
    }
}

/// Timecode representation based on frames and framerate.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Timecode {
    pub frames: i64,
    pub fps_num: i64,
    pub fps_den: i64,
}

impl Timecode {
    pub fn from_seconds(seconds: f64, fps_num: i64, fps_den: i64) -> Self {
        let fps = fps_num as f64 / fps_den as f64;
        let frames = (seconds * fps).round() as i64;
        Self {
            frames,
            fps_num,
            fps_den,
        }
    }

    pub fn to_seconds(self) -> f64 {
        let fps = self.fps_num as f64 / self.fps_den as f64;
        if fps <= 0.0 {
            0.0
        } else {
            self.frames as f64 / fps
        }
    }

    pub fn to_hms_string(self) -> String {
        let total_secs = self.to_seconds();
        let h = (total_secs / 3600.0).floor() as u32;
        let rem = total_secs % 3600.0;
        let m = (rem / 60.0).floor() as u32;
        let s = rem % 60.0;
        format!("{:02}:{:02}:{:06.3}", h, m, s)
    }
}

/// Type of media content in track or clip.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MediaType {
    Video,
    Audio,
    Subtitle,
    Image,
    Effect,
}

/// Track classification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TrackKind {
    Video,
    Audio,
    Subtitle,
}

/// Blend modes for compositing layers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum BlendMode {
    Normal,
    Multiply,
    Screen,
    Overlay,
    Darken,
    Lighten,
}

/// 2D geometric transformation for clip positioning.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Transform2D {
    pub position_x: f32,
    pub position_y: f32,
    pub scale_x: f32,
    pub scale_y: f32,
    pub rotation_degrees: f32,
    pub opacity: f32,
}

impl Default for Transform2D {
    fn default() -> Self {
        Self {
            position_x: 0.0,
            position_y: 0.0,
            scale_x: 1.0,
            scale_y: 1.0,
            rotation_degrees: 0.0,
            opacity: 1.0,
        }
    }
}

/// RGBA 8-bit color.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ColorRgba {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

impl ColorRgba {
    pub const fn new(r: u8, g: u8, b: u8, a: u8) -> Self {
        Self { r, g, b, a }
    }

    pub fn to_hex(&self) -> String {
        format!("#{:02x}{:02x}{:02x}{:02x}", self.r, self.g, self.b, self.a)
    }
}

/// Canvas resolution aspect ratio.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct AspectRatio {
    pub width: u32,
    pub height: u32,
}

impl AspectRatio {
    pub const fn r_16_9() -> Self {
        Self {
            width: 16,
            height: 9,
        }
    }

    pub const fn r_9_16() -> Self {
        Self {
            width: 9,
            height: 16,
        }
    }

    pub const fn r_1_1() -> Self {
        Self {
            width: 1,
            height: 1,
        }
    }

    pub const fn r_4_3() -> Self {
        Self {
            width: 4,
            height: 3,
        }
    }

    pub fn ratio(&self) -> f32 {
        if self.height == 0 {
            1.0
        } else {
            self.width as f32 / self.height as f32
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_timecode_conversions() {
        let tc = Timecode::from_seconds(3661.5, 30, 1);
        assert_eq!(tc.to_hms_string(), "01:01:01.500");
    }

    #[test]
    fn test_rational_f64() {
        let r = Rational::new(1920, 1080);
        assert!((r.to_f64() - 1.7777777).abs() < 1e-4);
    }
}
