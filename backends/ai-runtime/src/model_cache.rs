use std::path::{Path, PathBuf};

pub fn resolve_model_path(base_dir: &Path, model_name: &str) -> PathBuf {
    base_dir.join("data").join("models").join(model_name)
}

pub fn is_model_cached(base_dir: &Path, model_name: &str) -> bool {
    let p = resolve_model_path(base_dir, model_name);
    p.exists()
}
