//! editor-video: Video composition layout, canvas scaling, and letterbox geometry math.

use serde::{Deserialize, Serialize};

/// Scaling mode for placing media clips into a target canvas.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FitMode {
    Fit,     // Keep aspect ratio with black bars (letterbox/pillarbox)
    Fill,    // Keep aspect ratio, crop overflow
    Stretch, // Distort to fill exact dimensions
}

/// Calculated destination bounding box for placing a video frame into a canvas.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ViewportRect {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

/// Calculate the exact positioning and letterbox/pillarbox placement.
pub fn calculate_fit_geometry(
    source_width: u32,
    source_height: u32,
    canvas_width: u32,
    canvas_height: u32,
    mode: FitMode,
) -> ViewportRect {
    if source_width == 0 || source_height == 0 || canvas_width == 0 || canvas_height == 0 {
        return ViewportRect {
            x: 0.0,
            y: 0.0,
            width: 0.0,
            height: 0.0,
        };
    }

    let src_ratio = source_width as f32 / source_height as f32;
    let canvas_ratio = canvas_width as f32 / canvas_height as f32;

    match mode {
        FitMode::Stretch => ViewportRect {
            x: 0.0,
            y: 0.0,
            width: canvas_width as f32,
            height: canvas_height as f32,
        },
        FitMode::Fit => {
            if src_ratio > canvas_ratio {
                // Letterbox: wider than canvas -> black bars on top/bottom
                let w = canvas_width as f32;
                let h = w / src_ratio;
                let y = (canvas_height as f32 - h) / 2.0;
                ViewportRect {
                    x: 0.0,
                    y,
                    width: w,
                    height: h,
                }
            } else {
                // Pillarbox: taller than canvas -> black bars on sides
                let h = canvas_height as f32;
                let w = h * src_ratio;
                let x = (canvas_width as f32 - w) / 2.0;
                ViewportRect {
                    x,
                    y: 0.0,
                    width: w,
                    height: h,
                }
            }
        }
        FitMode::Fill => {
            if src_ratio > canvas_ratio {
                let h = canvas_height as f32;
                let w = h * src_ratio;
                let x = (canvas_width as f32 - w) / 2.0;
                ViewportRect {
                    x,
                    y: 0.0,
                    width: w,
                    height: h,
                }
            } else {
                let w = canvas_width as f32;
                let h = w / src_ratio;
                let y = (canvas_height as f32 - h) / 2.0;
                ViewportRect {
                    x: 0.0,
                    y,
                    width: w,
                    height: h,
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_letterbox_fit() {
        // 16:9 source in 1:1 canvas (1920x1080 in 1080x1080)
        let rect = calculate_fit_geometry(1920, 1080, 1080, 1080, FitMode::Fit);
        assert_eq!(rect.width, 1080.0);
        assert!((rect.height - 607.5).abs() < 1.0);
        assert!((rect.y - 236.25).abs() < 1.0);
        assert_eq!(rect.x, 0.0);
    }
}
