use thiserror::Error;

#[derive(Error, Debug)]
pub enum DubbingError {
    #[error("Dubbing project error: {0}")]
    ProjectError(String),

    #[error("Dubbing pipeline plan error: {0}")]
    PlanError(String),

    #[error("Alignment / synchronization failure: {0}")]
    AlignmentFailed(String),

    #[error("Speech synthesis failed in dubbing pipeline: {0}")]
    Speech(#[from] editor_speech::SpeechError),

    #[error("Model error: {0}")]
    Model(#[from] editor_models::ModelError),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}
