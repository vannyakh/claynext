use crate::segments::DubbedSegment;
use editor_types::Rational;

pub struct SegmentAligner;

impl SegmentAligner {
    /// Adjust speech speed so translated segment fits within the original duration slot
    pub fn align_segment_duration(
        segment: &mut DubbedSegment,
        available_duration: Rational,
        min_speed: f32,
        max_speed: f32,
    ) {
        let current_dur = segment.duration().to_f64();
        let target_dur = available_duration.to_f64();

        if current_dur > 0.0 && target_dur > 0.0 {
            let required_speed = (current_dur / target_dur) as f32;
            segment.speech_speed = required_speed.clamp(min_speed, max_speed);
        }
    }
}
