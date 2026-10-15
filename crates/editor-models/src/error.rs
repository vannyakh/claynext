use thiserror::Error;

#[derive(Error, Debug)]
pub enum ModelError {
    #[error("Model not found in registry: {0}")]
    NotFound(String),

    #[error("Provider error ({provider}): {message}")]
    ProviderError { provider: String, message: String },

    #[error("Download error for {model}: {details}")]
    DownloadFailed { model: String, details: String },

    #[error("Inference execution error: {0}")]
    InferenceFailed(String),

    #[error("Model file corrupted or invalid checksum: {0}")]
    IntegrityCheckFailed(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}
