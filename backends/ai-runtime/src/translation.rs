use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranslationChunk {
    pub chunk_index: usize,
    pub text: String,
    pub line_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpeechQuota {
    pub min: i32,
    pub target: i32,
    pub max: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TranslateStyle {
    #[serde(default = "default_true")]
    pub fit_duration: bool,
    #[serde(default = "default_true")]
    pub use_slang: bool,
    #[serde(default = "default_true")]
    pub use_expression: bool,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DubPromptRequest {
    pub payload: serde_json::Value,
    pub target_lang: String,
    #[serde(default = "default_source_lang")]
    pub source_lang: String,
    #[serde(default)]
    pub style: TranslateStyle,
}

fn default_source_lang() -> String {
    "auto".to_string()
}

/// Syllables / speaking units per second by display language name.
fn pace_rate(target_lang: &str) -> f64 {
    match target_lang {
        "Khmer" | "Khmer (ភាសាខ្មែរ)" => 3.6,
        "Chinese (Simplified)" => 4.0,
        "Chinese (Traditional)" => 4.0,
        "Japanese" => 4.2,
        "Korean" => 4.0,
        "Vietnamese" => 3.8,
        "Thai" => 3.8,
        "English" => 3.2,
        "Spanish" => 3.4,
        "French" => 3.3,
        "German" => 3.1,
        "Russian" => 3.2,
        _ => 3.5,
    }
}

/// min / target / max speaking units for a line slot (LLM duration fit).
pub fn estimate_speech_quota(duration_sec: f64, target_lang: &str) -> SpeechQuota {
    let dur = duration_sec.max(0.0);
    let rate = pace_rate(target_lang);
    let target = (dur * rate) as i32;
    SpeechQuota {
        min: ((dur * rate * 0.80) as i32).max(1),
        target: target.max(1),
        max: ((dur * rate * 1.20) as i32).max(2),
    }
}

/// Expression chips the LLM may insert when `use_expression` is on.
pub fn expression_chip_tokens() -> &'static [&'static str] {
    &[
        "[laugh]",
        "[sigh]",
        "[gasp]",
        "[pause]",
        "[excited]",
        "[whisper]",
        "[angry]",
        "[sad]",
        "[shout]",
    ]
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

/// Cinematic dubbing prompt with optional duration-fit, slang, and expression tags.
pub fn build_dubbing_llm_prompt(
    payload: &serde_json::Value,
    target_lang: &str,
    source_lang: &str,
    style: &TranslateStyle,
) -> String {
    let lang_name = if target_lang == "Khmer" {
        "natural conversational Khmer (ភាសាខ្មែរ)".to_string()
    } else {
        target_lang.to_string()
    };
    let src_name = if !source_lang.is_empty()
        && source_lang != "auto"
        && source_lang != "Auto Detect"
    {
        format!("from {} ", source_lang)
    } else {
        String::new()
    };

    let mut rules: Vec<String> = vec![
        "1. Preserve emotional tone, character nuance, and actor delivery — write spoken dialogue, not subtitle captions.".into(),
        "2. Keep each line's meaning accurate; do not invent plot facts.".into(),
    ];
    let mut n: usize = 3;

    if style.fit_duration {
        rules.push(format!(
            "{n}. TTS DURATION FIT (critical): keep spoken length inside recommended_syllables \
             (min/target/max) for duration_sec. Prefer shorter natural phrasing over padding. \
             Stay within speed_tolerance (typically 0.65–1.85). Count syllables/units for {target_lang}."
        ));
        n += 1;
    }
    if style.use_slang {
        rules.push(format!(
            "{n}. SLANG & IDIOM: prefer natural slang, colloquialisms, and idioms a native \
             {target_lang} speaker would say in film — not stiff word-for-word translation. \
             Match register (teen slang, formal, rough) to the character."
        ));
        n += 1;
    }
    if style.use_expression {
        let tags = expression_chip_tokens().join(", ");
        rules.push(format!(
            "{n}. EXPRESSION TAGS: when the source implies a non-verbal beat or strong emotion, \
             you MAY insert at most one short TTS cue at the start or mid-line from: {tags}. \
             Never invent story; never stack multiple tags; omit tags when the line is plain speech."
        ));
        n += 1;
    }
    rules.push(format!(
        "{n}. Return STRICTLY a JSON array of objects with keys id (or segment_id) and khmer_text \
         (use khmer_text for the translated spoken line even when the target is not Khmer)."
    ));

    let mut features = Vec::new();
    if style.fit_duration {
        features.push("duration-fit");
    }
    if style.use_slang {
        features.push("slang/idiom");
    }
    if style.use_expression {
        features.push("expression-tags");
    }
    let feat = if features.is_empty() {
        "literal".to_string()
    } else {
        features.join(", ")
    };

    let payload_json = serde_json::to_string(payload).unwrap_or_else(|_| "[]".to_string());

    format!(
        "You are a cinematic dubbing adapter translating film dialogue {src_name}into {lang_name}.\n\
         Active features: {feat}.\n\
         Rules:\n{}\n\n\
         Dialogue segments:\n{payload_json}",
        rules.join("\n")
    )
}

pub fn build_dubbing_llm_prompt_from_request(req: &DubPromptRequest) -> String {
    build_dubbing_llm_prompt(
        &req.payload,
        &req.target_lang,
        &req.source_lang,
        &req.style,
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

    #[test]
    fn test_speech_quota() {
        let q = estimate_speech_quota(2.0, "English");
        assert!(q.target >= 1);
        assert!(q.min <= q.target);
        assert!(q.max >= q.target);
    }

    #[test]
    fn test_dub_prompt_includes_style_flags() {
        let payload = serde_json::json!([{"id": 1, "text": "Hello", "duration_sec": 1.5}]);
        let style = TranslateStyle {
            fit_duration: true,
            use_slang: true,
            use_expression: false,
        };
        let prompt = build_dubbing_llm_prompt(&payload, "Khmer", "English", &style);
        assert!(prompt.contains("DURATION FIT"));
        assert!(prompt.contains("SLANG"));
        assert!(!prompt.contains("EXPRESSION TAGS"));
        assert!(prompt.contains("duration-fit"));
        assert!(prompt.contains("slang/idiom"));
    }
}
