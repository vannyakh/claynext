use thiserror::Error;

#[derive(Error, Debug)]
pub enum AiError {
    #[error("Device selection or acceleration error: {0}")]
    DeviceError(String),

    #[error("Inference runtime error: {0}")]
    InferenceError(String),

    #[error("Model registry error: {0}")]
    ModelError(#[from] editor_models::ModelError),

    #[error("Speech / transcription error: {0}")]
    SpeechError(#[from] editor_speech::SpeechError),

    #[error("Dubbing pipeline error: {0}")]
    DubbingError(#[from] editor_dubbing::DubbingError),

    #[error("Background job execution error: {0}")]
    JobError(String),

    #[error("Vision / video processing error: {0}")]
    VisionError(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}
