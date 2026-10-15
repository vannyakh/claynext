use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranslationChunk {
    pub chunk_index: usize,
    pub text: String,
    pub line_count: usize,
}

pub fn chunk_subtitles_for_translation(text: &str, max_chars: usize) -> Vec<TranslationChunk> {
    let mut chunks = Vec::new();
    let lines: Vec<&str> = text.lines().collect();
    let mut current_chunk = String::new();
    let mut current_lines = 0;
    let mut chunk_idx = 0;

    for line in lines {
        if !current_chunk.is_empty() && (current_chunk.len() + line.len() + 1 > max_chars) {
            chunks.push(TranslationChunk {
                chunk_index: chunk_idx,
                text: current_chunk.trim().to_string(),
                line_count: current_lines,
            });
            chunk_idx += 1;
            current_chunk.clear();
            current_lines = 0;
        }
        current_chunk.push_str(line);
        current_chunk.push('\n');
        current_lines += 1;
    }

    if !current_chunk.trim().is_empty() {
        chunks.push(TranslationChunk {
            chunk_index: chunk_idx,
            text: current_chunk.trim().to_string(),
            line_count: current_lines,
        });
    }

    chunks
}

pub fn build_llm_translation_prompt(source_lang: &str, target_lang: &str, text: &str) -> String {
    format!(
        "Translate the following subtitle cues from {} to {}. Preserve all numbering, timestamps, and line breaks exactly. Do not add explanations or notes.\n\n{}",
        source_lang, target_lang, text
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_chunking() {
        let text = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5";
        let chunks = chunk_subtitles_for_translation(text, 15);
        assert!(chunks.len() >= 2);
    }
}
