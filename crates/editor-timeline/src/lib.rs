//! editor-timeline: Multi-track timeline state machine, trimming, splitting, snapping, and collisions.

use editor_types::{ClipId, MediaType, TrackId, TrackKind, Transform2D};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum TimelineError {
    #[error("Track not found: {0:?}")]
    TrackNotFound(TrackId),
    #[error("Clip not found: {0:?}")]
    ClipNotFound(ClipId),
    #[error("Invalid clip bounds: start {start}, duration {duration}")]
    InvalidBounds { start: f64, duration: f64 },
    #[error("Split point {split_seconds}s outside of clip [{clip_start}s, {clip_end}s]")]
    SplitOutOfBounds {
        split_seconds: f64,
        clip_start: f64,
        clip_end: f64,
    },
}

/// Individual media clip instance placed on a timeline track.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimelineClip {
    pub id: ClipId,
    pub track_id: TrackId,
    pub media_path: String,
    pub media_type: MediaType,
    pub start_seconds: f64,
    pub duration_seconds: f64,
    pub source_in_seconds: f64,
    pub speed: f32,
    pub volume: f32,
    pub is_muted: bool,
    pub transform: Transform2D,
}

impl TimelineClip {
    pub fn end_seconds(&self) -> f64 {
        self.start_seconds + self.duration_seconds
    }

    pub fn overlaps(&self, other_start: f64, other_end: f64) -> bool {
        self.start_seconds < other_end && self.end_seconds() > other_start
    }
}

/// Individual track containing an ordered list of clips.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimelineTrack {
    pub id: TrackId,
    pub kind: TrackKind,
    pub name: String,
    pub is_muted: bool,
    pub is_locked: bool,
    pub volume: f32,
    pub clips: Vec<TimelineClip>,
}

impl TimelineTrack {
    pub fn new(kind: TrackKind, name: impl Into<String>) -> Self {
        Self {
            id: TrackId::new(),
            kind,
            name: name.into(),
            is_muted: false,
            is_locked: false,
            volume: 1.0,
            clips: Vec::new(),
        }
    }

    pub fn sort_clips(&mut self) {
        self.clips
            .sort_by(|a, b| a.start_seconds.partial_cmp(&b.start_seconds).unwrap());
    }
}

/// Complete multi-track timeline data structure.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Timeline {
    pub fps_num: i64,
    pub fps_den: i64,
    pub playhead_seconds: f64,
    pub tracks: Vec<TimelineTrack>,
}

impl Timeline {
    pub fn new(fps_num: i64, fps_den: i64) -> Self {
        Self {
            fps_num,
            fps_den,
            playhead_seconds: 0.0,
            tracks: Vec::new(),
        }
    }

    pub fn add_track(&mut self, kind: TrackKind, name: impl Into<String>) -> TrackId {
        let track = TimelineTrack::new(kind, name);
        let id = track.id;
        self.tracks.push(track);
        id
    }

    pub fn remove_track(&mut self, track_id: TrackId) -> Result<(), TimelineError> {
        let idx = self
            .tracks
            .iter()
            .position(|t| t.id == track_id)
            .ok_or(TimelineError::TrackNotFound(track_id))?;
        self.tracks.remove(idx);
        Ok(())
    }

    pub fn add_clip(
        &mut self,
        track_id: TrackId,
        media_path: impl Into<String>,
        media_type: MediaType,
        start_seconds: f64,
        duration_seconds: f64,
        source_in_seconds: f64,
    ) -> Result<ClipId, TimelineError> {
        if duration_seconds <= 0.0 || start_seconds < 0.0 {
            return Err(TimelineError::InvalidBounds {
                start: start_seconds,
                duration: duration_seconds,
            });
        }
        let track = self
            .tracks
            .iter_mut()
            .find(|t| t.id == track_id)
            .ok_or(TimelineError::TrackNotFound(track_id))?;

        let id = ClipId::new();
        let clip = TimelineClip {
            id,
            track_id,
            media_path: media_path.into(),
            media_type,
            start_seconds,
            duration_seconds,
            source_in_seconds,
            speed: 1.0,
            volume: 1.0,
            is_muted: false,
            transform: Transform2D::default(),
        };
        track.clips.push(clip);
        track.sort_clips();
        Ok(id)
    }

    pub fn remove_clip(&mut self, clip_id: ClipId) -> Result<(), TimelineError> {
        for track in &mut self.tracks {
            if let Some(pos) = track.clips.iter().position(|c| c.id == clip_id) {
                track.clips.remove(pos);
                return Ok(());
            }
        }
        Err(TimelineError::ClipNotFound(clip_id))
    }

    /// Split a clip into two distinct clips at a given timecode point.
    pub fn split_clip(
        &mut self,
        clip_id: ClipId,
        split_seconds: f64,
    ) -> Result<(ClipId, ClipId), TimelineError> {
        for track in &mut self.tracks {
            if let Some(pos) = track.clips.iter().position(|c| c.id == clip_id) {
                let clip = &track.clips[pos];
                if split_seconds <= clip.start_seconds || split_seconds >= clip.end_seconds() {
                    return Err(TimelineError::SplitOutOfBounds {
                        split_seconds,
                        clip_start: clip.start_seconds,
                        clip_end: clip.end_seconds(),
                    });
                }

                let left_duration = split_seconds - clip.start_seconds;
                let right_duration = clip.duration_seconds - left_duration;
                let right_source_in = clip.source_in_seconds + left_duration;

                // Mutate existing left clip
                let left_id = clip.id;
                let mut right_clip = clip.clone();
                right_clip.id = ClipId::new();
                right_clip.start_seconds = split_seconds;
                right_clip.duration_seconds = right_duration;
                right_clip.source_in_seconds = right_source_in;

                let right_id = right_clip.id;

                track.clips[pos].duration_seconds = left_duration;
                track.clips.insert(pos + 1, right_clip);
                return Ok((left_id, right_id));
            }
        }
        Err(TimelineError::ClipNotFound(clip_id))
    }

    /// Find magnetic snap point within a threshold (in seconds).
    pub fn calculate_snap(&self, target_seconds: f64, threshold_seconds: f64) -> f64 {
        let mut closest = target_seconds;
        let mut min_diff = threshold_seconds;

        // Snap to playhead
        let diff_playhead = (target_seconds - self.playhead_seconds).abs();
        if diff_playhead < min_diff {
            closest = self.playhead_seconds;
            min_diff = diff_playhead;
        }

        // Snap to start or end of all clips across tracks
        for track in &self.tracks {
            for clip in &track.clips {
                let diff_start = (target_seconds - clip.start_seconds).abs();
                if diff_start < min_diff {
                    closest = clip.start_seconds;
                    min_diff = diff_start;
                }
                let diff_end = (target_seconds - clip.end_seconds()).abs();
                if diff_end < min_diff {
                    closest = clip.end_seconds();
                    min_diff = diff_end;
                }
            }
        }
        closest
    }

    /// Total timeline duration in seconds.
    pub fn total_duration(&self) -> f64 {
        self.tracks
            .iter()
            .flat_map(|t| t.clips.iter())
            .map(|c| c.end_seconds())
            .fold(0.0, f64::max)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_timeline_add_and_split() {
        let mut tl = Timeline::new(30, 1);
        let track_id = tl.add_track(TrackKind::Video, "Video 1");
        let clip_id = tl
            .add_clip(track_id, "video.mp4", MediaType::Video, 0.0, 10.0, 0.0)
            .unwrap();

        assert_eq!(tl.total_duration(), 10.0);

        let (left, right) = tl.split_clip(clip_id, 4.0).unwrap();
        assert_eq!(left, clip_id);
        assert_ne!(left, right);

        let track = &tl.tracks[0];
        assert_eq!(track.clips.len(), 2);
        assert_eq!(track.clips[0].duration_seconds, 4.0);
        assert_eq!(track.clips[1].start_seconds, 4.0);
        assert_eq!(track.clips[1].duration_seconds, 6.0);
    }

    #[test]
    fn test_snapping() {
        let mut tl = Timeline::new(30, 1);
        let track_id = tl.add_track(TrackKind::Video, "Video 1");
        tl.add_clip(track_id, "video.mp4", MediaType::Video, 0.0, 5.0, 0.0)
            .unwrap();

        // Target near 5.0 (clip end)
        let snapped = tl.calculate_snap(5.08, 0.15);
        assert_eq!(snapped, 5.0);
    }
}
