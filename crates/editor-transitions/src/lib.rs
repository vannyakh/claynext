//! editor-transitions: Video transitions and FFmpeg xfade syntax generation.

use serde::{Deserialize, Serialize};

/// Supported transition types.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TransitionKind {
    Fade,
    WipeLeft,
    WipeRight,
    WipeUp,
    WipeDown,
    SlideLeft,
    SlideRight,
    CrossDissolve,
    FadeBlack,
    CircleCrop,
}

impl TransitionKind {
    pub fn xfade_transition_name(&self) -> &'static str {
        match self {
            Self::Fade => "fade",
            Self::WipeLeft => "wipeleft",
            Self::WipeRight => "wiperight",
            Self::WipeUp => "wipeup",
            Self::WipeDown => "wipedown",
            Self::SlideLeft => "slideleft",
            Self::SlideRight => "slideright",
            Self::CrossDissolve => "dissolve",
            Self::FadeBlack => "fadeblack",
            Self::CircleCrop => "circlecrop",
        }
    }
}

/// Transition specification between two adjacent video clips.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Transition {
    pub kind: TransitionKind,
    pub duration_seconds: f64,
    pub offset_seconds: f64,
}

impl Transition {
    /// Format into FFmpeg `xfade` filter parameter.
    pub fn to_xfade_filter(&self, input_a: &str, input_b: &str, output: &str) -> String {
        format!(
            "[{a}][{b}]xfade=transition={tr}:duration={dur:.3}:offset={off:.3}[{out}]",
            a = input_a,
            b = input_b,
            tr = self.kind.xfade_transition_name(),
            dur = self.duration_seconds,
            off = self.offset_seconds,
            out = output
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_xfade_formatting() {
        let tr = Transition {
            kind: TransitionKind::WipeLeft,
            duration_seconds: 1.0,
            offset_seconds: 9.0,
        };
        let filter = tr.to_xfade_filter("0:v", "1:v", "v_trans");
        assert_eq!(
            filter,
            "[0:v][1:v]xfade=transition=wipeleft:duration=1.000:offset=9.000[v_trans]"
        );
    }
}
