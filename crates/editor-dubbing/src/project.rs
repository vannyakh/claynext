use crate::plan::DubbingPipelinePlan;
use crate::segments::DubbedSegment;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DubbingProject {
    pub id: String,
    pub title: String,
    pub media_file_path: String,
    pub plan: DubbingPipelinePlan,
    pub segments: Vec<DubbedSegment>,
    pub created_at: String,
    pub updated_at: String,
}

impl DubbingProject {
    pub fn new(id: String, title: String, media_path: String) -> Self {
        Self {
            id,
            title,
            media_file_path: media_path,
            plan: DubbingPipelinePlan::default(),
            segments: Vec::new(),
            created_at: String::new(),
            updated_at: String::new(),
        }
    }
}
