use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrBox {
    pub text: String,
    pub confidence: f32,
    #[serde(alias = "box", default)]
    pub bbox: [f32; 4], // [x1, y1, x2, y2]
}

pub fn filter_ocr_results(boxes: &[OcrBox], min_confidence: f32) -> Vec<OcrBox> {
    boxes
        .iter()
        .filter(|b| b.confidence >= min_confidence && !b.text.trim().is_empty())
        .cloned()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_filter() {
        let boxes = vec![
            OcrBox {
                text: "Valid text".to_string(),
                confidence: 0.95,
                bbox: [0.1, 0.1, 0.5, 0.2],
            },
            OcrBox {
                text: "Noise".to_string(),
                confidence: 0.2,
                bbox: [0.1, 0.1, 0.5, 0.2],
            },
        ];
        let filtered = filter_ocr_results(&boxes, 0.5);
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].text, "Valid text");
    }
}
