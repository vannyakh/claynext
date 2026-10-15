use thiserror::Error;

#[derive(Error, Debug)]
pub enum FfmpegError {
    #[error("FFmpeg binary not found on system PATH or configured directories")]
    FfmpegNotFound,

    #[error("FFprobe binary not found on system PATH or configured directories")]
    FfprobeNotFound,

    #[error("Failed to spawn FFmpeg/FFprobe process: {0}")]
    ProcessSpawn(#[source] std::io::Error),

    #[error("FFmpeg process failed with exit code {exit_code:?}: {stderr}")]
    ProcessFailed {
        exit_code: Option<i32>,
        stderr: String,
    },

    #[error("Process timed out after {timeout_secs} seconds")]
    ProcessTimeout { timeout_secs: u64 },

    #[error("Operation was cancelled by caller")]
    Cancelled,

    #[error("Invalid input path or parameter: {0}")]
    InvalidInput(String),

    #[error("Failed to parse FFprobe JSON metadata: {0}")]
    ProbeParse(String),

    #[error("Unsupported or unavailable codec: {0}")]
    CodecNotSupported(String),

    #[error("Stream not found: type={stream_type}, index={index:?}")]
    StreamNotFound {
        stream_type: String,
        index: Option<usize>,
    },

    #[error("Output validation failed: {0}")]
    OutputValidation(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON serialization/deserialization error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, FfmpegError>;
