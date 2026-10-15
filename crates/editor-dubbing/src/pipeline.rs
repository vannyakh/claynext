use crate::error::DubbingError;
use crate::project::DubbingProject;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DubbingPipelineStage {
    Idle,
    ExtractingAudio,
    SeparatingStems,
    TranscribingAsr,
    TranslatingSubtitles,
    SynthesizingVoices,
    DuckingAndMixing,
    ExportingVideo,
    Finished,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DubbingProgress {
    pub stage: DubbingPipelineStage,
    pub percentage: f32,
    pub message: String,
}

pub struct DubbingPipelineOrchestrator;

impl DubbingPipelineOrchestrator {
    pub fn validate_project(project: &DubbingProject) -> Result<(), DubbingError> {
        if project.media_file_path.is_empty() {
            return Err(DubbingError::ProjectError(
                "Project media file path is missing".to_string(),
            ));
        }
        Ok(())
    }
}
