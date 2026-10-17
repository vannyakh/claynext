use crate::segments::DubbedSegment;
use claynext_ai_runtime::align_speech_speed;
use editor_types::Rational;

pub struct SegmentAligner;

impl SegmentAligner {
    /// Adjust speech speed so translated segment fits within the original duration slot.
    /// Uses shared ai-runtime timing core (same as claynext-ai align-speed / Python bridge).
    pub fn align_segment_duration(
        segment: &mut DubbedSegment,
        available_duration: Rational,
        min_speed: f32,
        max_speed: f32,
    ) {
        let current_dur = segment.duration().to_f64();
        let target_dur = available_duration.to_f64();
        segment.speech_speed =
            align_speech_speed(current_dur, target_dur, min_speed, max_speed);
    }
}
