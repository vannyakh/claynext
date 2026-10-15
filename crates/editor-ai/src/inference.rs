use crate::error::AiError;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TensorShape {
    pub dims: Vec<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceInput {
    pub name: String,
    pub shape: TensorShape,
    pub data: Vec<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceOutput {
    pub name: String,
    pub shape: TensorShape,
    pub data: Vec<f32>,
}

pub struct InferenceRunner;

impl InferenceRunner {
    pub fn execute(
        _model_id: &str,
        inputs: &[InferenceInput],
    ) -> Result<Vec<InferenceOutput>, AiError> {
        let mut outputs = Vec::new();
        for inp in inputs {
            outputs.push(InferenceOutput {
                name: inp.name.clone(),
                shape: inp.shape.clone(),
                data: inp.data.clone(),
            });
        }
        Ok(outputs)
    }
}
