use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::RwLock;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AiJobStatus {
    Queued,
    Running,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AiJobRecord {
    pub id: String,
    pub title: String,
    pub task_type: String,
    pub status: AiJobStatus,
    pub progress: f32,
    pub error_message: Option<String>,
}

pub struct AiJobQueue {
    jobs: RwLock<HashMap<String, AiJobRecord>>,
}

impl Default for AiJobQueue {
    fn default() -> Self {
        Self::new()
    }
}

impl AiJobQueue {
    pub fn new() -> Self {
        Self {
            jobs: RwLock::new(HashMap::new()),
        }
    }

    pub fn submit_job(&self, title: &str, task_type: &str) -> String {
        let id = Uuid::new_v4().to_string();
        let record = AiJobRecord {
            id: id.clone(),
            title: title.to_string(),
            task_type: task_type.to_string(),
            status: AiJobStatus::Queued,
            progress: 0.0,
            error_message: None,
        };
        let mut lock = self.jobs.write().unwrap();
        lock.insert(id.clone(), record);
        id
    }

    pub fn update_progress(&self, id: &str, progress: f32, status: AiJobStatus) {
        let mut lock = self.jobs.write().unwrap();
        if let Some(j) = lock.get_mut(id) {
            j.progress = progress;
            j.status = status;
        }
    }

    pub fn get_job(&self, id: &str) -> Option<AiJobRecord> {
        let lock = self.jobs.read().unwrap();
        lock.get(id).cloned()
    }
}
