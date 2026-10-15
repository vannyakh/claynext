//! editor-core: Authoritative Claynext Studio engine managing project state, timeline operations, and command dispatching.

use editor_api::{Command, CommandResult};
use editor_timeline::Timeline;
use editor_types::ProjectId;
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum EngineError {
    #[error("No active project loaded")]
    NoActiveProject,
    #[error("Timeline error: {0}")]
    Timeline(#[from] editor_timeline::TimelineError),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
}

/// Project document state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectState {
    pub id: ProjectId,
    pub name: String,
    pub canvas_width: u32,
    pub canvas_height: u32,
    pub timeline: Timeline,
}

/// The stateful core multimedia editing engine instance.
pub struct Engine {
    active_project: Arc<Mutex<Option<ProjectState>>>,
}

impl Default for Engine {
    fn default() -> Self {
        Self::new()
    }
}

impl Engine {
    pub fn new() -> Self {
        Self {
            active_project: Arc::new(Mutex::new(None)),
        }
    }

    /// Dispatch a typed Command and return a typed CommandResult.
    pub fn dispatch(&self, cmd: Command) -> CommandResult {
        match cmd {
            Command::CreateProject {
                name,
                width,
                height,
                fps_num,
                fps_den,
            } => {
                let id = ProjectId::new();
                let timeline = Timeline::new(fps_num, fps_den);
                let project = ProjectState {
                    id,
                    name: name.clone(),
                    canvas_width: width,
                    canvas_height: height,
                    timeline,
                };
                let mut lock = self.active_project.lock().unwrap();
                *lock = Some(project.clone());
                CommandResult::success(&project)
            }

            Command::AddTrack { kind, name } => {
                let mut lock = self.active_project.lock().unwrap();
                if let Some(ref mut proj) = *lock {
                    let track_id = proj.timeline.add_track(kind, name);
                    CommandResult::success(&track_id)
                } else {
                    CommandResult::err("NO_ACTIVE_PROJECT", "No project loaded")
                }
            }

            Command::RemoveTrack { track_id } => {
                let mut lock = self.active_project.lock().unwrap();
                if let Some(ref mut proj) = *lock {
                    match proj.timeline.remove_track(track_id) {
                        Ok(()) => CommandResult::success(&true),
                        Err(e) => CommandResult::err("TIMELINE_ERROR", e.to_string()),
                    }
                } else {
                    CommandResult::err("NO_ACTIVE_PROJECT", "No project loaded")
                }
            }

            Command::AddClip {
                track_id,
                media_path,
                media_type,
                start_seconds,
                duration_seconds,
                source_in_seconds,
            } => {
                let mut lock = self.active_project.lock().unwrap();
                if let Some(ref mut proj) = *lock {
                    match proj.timeline.add_clip(
                        track_id,
                        media_path,
                        media_type,
                        start_seconds,
                        duration_seconds,
                        source_in_seconds,
                    ) {
                        Ok(clip_id) => CommandResult::success(&clip_id),
                        Err(e) => CommandResult::err("TIMELINE_ERROR", e.to_string()),
                    }
                } else {
                    CommandResult::err("NO_ACTIVE_PROJECT", "No project loaded")
                }
            }

            Command::SplitClip {
                clip_id,
                split_seconds,
            } => {
                let mut lock = self.active_project.lock().unwrap();
                if let Some(ref mut proj) = *lock {
                    match proj.timeline.split_clip(clip_id, split_seconds) {
                        Ok((left, right)) => CommandResult::success(&(left, right)),
                        Err(e) => CommandResult::err("TIMELINE_ERROR", e.to_string()),
                    }
                } else {
                    CommandResult::err("NO_ACTIVE_PROJECT", "No project loaded")
                }
            }

            Command::RemoveClip { clip_id } => {
                let mut lock = self.active_project.lock().unwrap();
                if let Some(ref mut proj) = *lock {
                    match proj.timeline.remove_clip(clip_id) {
                        Ok(()) => CommandResult::success(&true),
                        Err(e) => CommandResult::err("TIMELINE_ERROR", e.to_string()),
                    }
                } else {
                    CommandResult::err("NO_ACTIVE_PROJECT", "No project loaded")
                }
            }

            Command::OpenProject { path } => match std::fs::read_to_string(&path) {
                Ok(json) => match serde_json::from_str::<ProjectState>(&json) {
                    Ok(proj) => {
                        let mut lock = self.active_project.lock().unwrap();
                        *lock = Some(proj.clone());
                        CommandResult::success(&proj)
                    }
                    Err(e) => CommandResult::err("PARSE_ERROR", e.to_string()),
                },
                Err(e) => CommandResult::err("IO_ERROR", e.to_string()),
            },

            Command::SaveProject { path } => {
                let lock = self.active_project.lock().unwrap();
                if let Some(ref proj) = *lock {
                    match serde_json::to_string_pretty(proj) {
                        Ok(json) => match std::fs::write(&path, json) {
                            Ok(()) => CommandResult::success(&true),
                            Err(e) => CommandResult::err("IO_ERROR", e.to_string()),
                        },
                        Err(e) => CommandResult::err("SERIALIZE_ERROR", e.to_string()),
                    }
                } else {
                    CommandResult::err("NO_ACTIVE_PROJECT", "No project loaded")
                }
            }

            _ => CommandResult::err("UNIMPLEMENTED", "Command not yet wired"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use editor_types::{MediaType, TrackKind};

    #[test]
    fn test_engine_create_and_edit() {
        let engine = Engine::new();

        // 1. Create project
        let res = engine.dispatch(Command::CreateProject {
            name: "Demo Project".to_string(),
            width: 1920,
            height: 1080,
            fps_num: 30,
            fps_den: 1,
        });
        match res {
            CommandResult::Ok(_) => {}
            _ => panic!("Expected Ok result"),
        }

        // 2. Add video track
        let res = engine.dispatch(Command::AddTrack {
            kind: TrackKind::Video,
            name: "V1".to_string(),
        });
        let track_id: editor_types::TrackId = match res {
            CommandResult::Ok(val) => serde_json::from_value(val).unwrap(),
            _ => panic!("Failed to add track"),
        };

        // 3. Add clip
        let res = engine.dispatch(Command::AddClip {
            track_id,
            media_path: "intro.mp4".to_string(),
            media_type: MediaType::Video,
            start_seconds: 0.0,
            duration_seconds: 10.0,
            source_in_seconds: 0.0,
        });
        let clip_id: editor_types::ClipId = match res {
            CommandResult::Ok(val) => serde_json::from_value(val).unwrap(),
            _ => panic!("Failed to add clip"),
        };

        // 4. Split clip at 4.0s
        let res = engine.dispatch(Command::SplitClip {
            clip_id,
            split_seconds: 4.0,
        });
        match res {
            CommandResult::Ok(val) => {
                let (left, right): (editor_types::ClipId, editor_types::ClipId) =
                    serde_json::from_value(val).unwrap();
                assert_eq!(left, clip_id);
                assert_ne!(left, right);
            }
            _ => panic!("Failed to split clip"),
        }
    }
}
