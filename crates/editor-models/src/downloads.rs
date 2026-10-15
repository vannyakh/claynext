use crate::error::ModelError;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelDownloadProgress {
    pub model_id: String,
    pub bytes_downloaded: u64,
    pub total_bytes: Option<u64>,
    pub percentage: f32,
    pub is_completed: bool,
}

pub struct ModelDownloader;

impl ModelDownloader {
    pub fn destination_path(cache_dir: &Path, repo_or_name: &str) -> PathBuf {
        let clean_name = repo_or_name.replace(['/', '\\', ':'], "_");
        cache_dir.join(clean_name)
    }

    pub fn is_cached(cache_dir: &Path, repo_or_name: &str) -> bool {
        Self::destination_path(cache_dir, repo_or_name).exists()
    }

    pub fn ensure_model_dir(dest: &Path) -> Result<(), ModelError> {
        if !dest.exists() {
            std::fs::create_dir_all(dest)?;
        }
        Ok(())
    }
}
