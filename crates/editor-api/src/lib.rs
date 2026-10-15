//! editor-api: Command and Query interface connecting Python frontend to Rust engine.

use editor_types::{ClipId, MediaType, ProjectId, Timecode, TrackId, TrackKind, Transform2D};
use serde::{Deserialize, Serialize};

/// High-level commands executable by the engine.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "command", content = "payload", rename_all = "snake_case")]
pub enum Command {
    // Project operations
    CreateProject {
        name: String,
        width: u32,
        height: u32,
        fps_num: i64,
        fps_den: i64,
    },
    OpenProject {
        path: String,
    },
    SaveProject {
        path: String,
    },

    // Timeline operations
    AddTrack {
        kind: TrackKind,
        name: String,
    },
    RemoveTrack {
        track_id: TrackId,
    },
    AddClip {
        track_id: TrackId,
        media_path: String,
        media_type: MediaType,
        start_seconds: f64,
        duration_seconds: f64,
        source_in_seconds: f64,
    },
    RemoveClip {
        clip_id: ClipId,
    },
    SplitClip {
        clip_id: ClipId,
        split_seconds: f64,
    },
    TrimClip {
        clip_id: ClipId,
        new_in_seconds: f64,
        new_duration_seconds: f64,
    },
    MoveClip {
        clip_id: ClipId,
        target_track_id: TrackId,
        target_start_seconds: f64,
    },
    ApplyTransform {
        clip_id: ClipId,
        transform: Transform2D,
    },

    // Audio & Ducking
    SetAudioDucking {
        music_track_id: TrackId,
        voice_track_id: TrackId,
        ducking_db: f32,
        attack_ms: f32,
        release_ms: f32,
    },

    // Media & Export
    ProbeMedia {
        path: String,
    },
    RenderTimeline {
        output_path: String,
        encoder: Option<String>,
        crf: Option<u32>,
        preset: Option<String>,
    },
    CancelJob {
        job_id: String,
    },
}

/// Structured response from command execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "status", content = "data", rename_all = "snake_case")]
pub enum CommandResult {
    Ok(serde_json::Value),
    Error { code: String, message: String },
}

impl CommandResult {
    pub fn success<T: Serialize>(val: &T) -> Self {
        match serde_json::to_value(val) {
            Ok(v) => Self::Ok(v),
            Err(e) => Self::Error {
                code: "SERIALIZATION_ERROR".to_string(),
                message: e.to_string(),
            },
        }
    }

    pub fn err(code: impl Into<String>, msg: impl Into<String>) -> Self {
        Self::Error {
            code: code.into(),
            message: msg.into(),
        }
    }
}

/// Asynchronous events emitted by the Rust engine to the Python frontend.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "event", content = "payload", rename_all = "snake_case")]
pub enum EngineEvent {
    ProjectLoaded {
        project_id: ProjectId,
        name: String,
    },
    TimelineModified,
    PlaybackPositionChanged {
        current_timecode: Timecode,
        playback_rate: f32,
    },
    RenderProgress {
        percentage: f32,
        fps: f32,
        eta_seconds: f32,
    },
    RenderCompleted {
        output_path: String,
        duration_seconds: f64,
    },
    JobCancelled {
        job_id: String,
    },
}
