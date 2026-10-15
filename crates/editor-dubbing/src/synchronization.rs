use crate::segments::DubbedSegment;
use editor_types::Rational;

pub struct TimelineSynchronizer;

impl TimelineSynchronizer {
    /// Prevent segment overlapping by shifting subsequent segments if necessary
    pub fn resolve_overlaps(segments: &mut [DubbedSegment], min_gap: Rational) {
        if segments.len() <= 1 {
            return;
        }

        for i in 0..segments.len() - 1 {
            let next_min_start = segments[i].target_end + min_gap;
            if segments[i + 1].target_start < next_min_start {
                let duration = segments[i + 1].duration();
                segments[i + 1].target_start = next_min_start;
                segments[i + 1].target_end = next_min_start + duration;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_overlap_resolution() {
        let mut segs = vec![
            DubbedSegment {
                id: 1,
                original_start: Rational::new(0, 1),
                original_end: Rational::new(2, 1),
                target_start: Rational::new(0, 1),
                target_end: Rational::new(2, 1),
                source_text: "A".to_string(),
                translated_text: "A".to_string(),
                voice_id: "v".to_string(),
                speech_speed: 1.0,
                pitch_shift: 0.0,
                volume_gain_db: 0.0,
                audio_file_path: None,
            },
            DubbedSegment {
                id: 2,
                original_start: Rational::new(2, 1),
                original_end: Rational::new(4, 1),
                target_start: Rational::new(1, 1), // Overlap!
                target_end: Rational::new(3, 1),
                source_text: "B".to_string(),
                translated_text: "B".to_string(),
                voice_id: "v".to_string(),
                speech_speed: 1.0,
                pitch_shift: 0.0,
                volume_gain_db: 0.0,
                audio_file_path: None,
            },
        ];

        TimelineSynchronizer::resolve_overlaps(&mut segs, Rational::new(1, 10)); // 0.1s gap
        assert_eq!(segs[1].target_start, Rational::new(21, 10)); // 2.1s
    }
}
