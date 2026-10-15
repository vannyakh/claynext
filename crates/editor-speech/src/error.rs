use thiserror::Error;

#[derive(Error, Debug)]
pub enum SpeechError {
    #[error("ASR transcription error: {0}")]
    AsrFailed(String),

    #[error("TTS synthesis error: {0}")]
    TtsFailed(String),

    #[error("Voice activity detection error: {0}")]
    VadFailed(String),

    #[error("Voice classification/detection error: {0}")]
    VoiceDetectionFailed(String),

    #[error("Expression parsing error: {0}")]
    ExpressionParseFailed(String),

    #[error("Speech model error: {0}")]
    Model(#[from] editor_models::ModelError),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}
