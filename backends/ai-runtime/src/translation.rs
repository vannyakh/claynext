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

/// min / target / max speaking beats for a line slot.
///
/// `max` is a natural pace for `duration_sec` (not a sped-up reading). The model
/// should land near `target` so the dubbed line finishes with the actor.
pub fn estimate_speech_quota(duration_sec: f64, target_lang: &str) -> SpeechQuota {
    let dur = duration_sec.max(0.0);
    let beats = dur * pace_rate(target_lang);
    let target = (beats * 0.90).round() as i32;
    let min = (beats * 0.60).round() as i32;
    let max = beats.round() as i32;
    SpeechQuota {
        min: min.max(1),
        target: target.max(1),
        max: max.max(target).max(1),
    }
}

/// Spoken beats in `text` for duration checks.
///
/// Khmer counts syllables (a final consonant stays in its syllable). Latin counts
/// vowel groups. Expression cues like `[laugh]` are ignored.
pub fn spoken_units(text: &str, lang: &str) -> i32 {
    let bare = strip_expression_cues(text);
    if bare.trim().is_empty() {
        return 0;
    }
    let khmerish = lang_is_khmer(lang) || bare.chars().any(is_khmer);
    if khmerish {
        return khmer_beats(&bare).max(1);
    }
    let cjk = bare.chars().filter(|c| is_cjk(*c)).count() as i32;
    let latin = bare.chars().filter(|c| c.is_ascii_alphabetic()).count();
    if cjk > 0 && (latin == 0 || cjk as usize * 2 >= latin) {
        return cjk.max(1);
    }
    latin_beats(&bare).max(1)
}

fn lang_is_khmer(lang: &str) -> bool {
    let name = lang.trim();
    name == "Khmer" || name.starts_with("Khmer") || name.contains("ខ្មែរ")
}

fn is_khmer(c: char) -> bool {
    ('\u{1780}'..='\u{17FF}').contains(&c)
}

fn is_cjk(c: char) -> bool {
    ('\u{4E00}'..='\u{9FFF}').contains(&c)
        || ('\u{3040}'..='\u{30FF}').contains(&c)
        || ('\u{AC00}'..='\u{D7AF}').contains(&c)
}

fn strip_expression_cues(text: &str) -> String {
    let mut out = String::new();
    let mut skipping = false;
    for c in text.chars() {
        if c == '[' {
            skipping = true;
            continue;
        }
        if c == ']' && skipping {
            skipping = false;
            continue;
        }
        if !skipping {
            out.push(c);
        }
    }
    out
}

fn is_khmer_base(c: char) -> bool {
    ('\u{1780}'..='\u{17B3}').contains(&c)
}

fn is_khmer_vowel(c: char) -> bool {
    ('\u{17B6}'..='\u{17C5}').contains(&c)
}

fn is_khmer_sign(c: char) -> bool {
    ('\u{17C6}'..='\u{17D1}').contains(&c) || c == '\u{17D3}' || c == '\u{17DD}'
}

/// A consonant is a coda when it has no vowel of its own (គាត់ → one beat, not two).
fn is_khmer_coda(chars: &[char], index: usize) -> bool {
    let mut j = index + 1;
    if j < chars.len() && chars[j] == '\u{17D2}' {
        return false;
    }
    while j < chars.len() && is_khmer_sign(chars[j]) {
        j += 1;
    }
    if j < chars.len() && is_khmer_vowel(chars[j]) {
        return false;
    }
    true
}

/// Khmer spoken beats: one per syllable onset. Final consonants stay in the syllable.
fn khmer_beats(text: &str) -> i32 {
    let chars: Vec<char> = text.chars().collect();
    let mut i = 0;
    let mut beats = 0i32;
    while i < chars.len() {
        if !is_khmer_base(chars[i]) {
            i += 1;
            continue;
        }
        beats += 1;
        i += 1;
        while i < chars.len() {
            if chars[i] == '\u{17D2}' && i + 1 < chars.len() && is_khmer_base(chars[i + 1]) {
                i += 2;
                continue;
            }
            if is_khmer_vowel(chars[i]) || is_khmer_sign(chars[i]) {
                i += 1;
                continue;
            }
            if is_khmer_base(chars[i]) && is_khmer_coda(&chars, i) {
                i += 1;
                continue;
            }
            break;
        }
    }
    beats
}

fn latin_beats(text: &str) -> i32 {
    let mut beats = 0i32;
    let mut in_vowel = false;
    for c in text.chars() {
        if "aeiouyAEIOUY".contains(c) {
            if !in_vowel {
                beats += 1;
                in_vowel = true;
            }
        } else {
            in_vowel = false;
        }
    }
    beats
}

fn voice_rewrite_rule() -> String {
    "1. VOICE REWRITE: Do not translate word by word. Understand the line, then write new words — \
     the best line a native speaker would say in that moment. Keep who did it, what happened, \
     the feeling, and the sound of the voice (short or drawn out, sharp or soft, polite or rough). \
     Do not copy the source grammar. A dictionary line nobody would say is wrong."
        .into()
}

fn register_rule(n: usize, target_lang: &str) -> String {
    let mut rule = format!(
        "{n}. SLANG: Match how this person talks. If they are casual, rude, or swearing, \
         keep that heat with the short word people actually say — slang, an insult, or a swear word. \
         Do not swap it for a polite or textbook word. Do not add a curse the line did not earn."
    );
    if lang_is_khmer(target_lang) {
        rule.push_str(
            " Khmer — \"What the hell are you doing?\" is said \"ឯងធ្វើអីហ្នឹង?\", \
             not \"តើអ្នកកំពុងធ្វើអ្វី?\".",
        );
    }
    rule
}

fn spoken_fit_rule(n: usize, target_lang: &str) -> String {
    let mut rule = format!(
        "{n}. SPOKEN FIT (critical): write what a voice actor can say inside duration_sec \
         at a natural pace. Aim at recommended_syllables.target. Do not pass max. \
         Those numbers are spoken beats, not written words. If unsure, choose the shorter line. \
         Drop fillers that do not change the action (then, so, well, and, you know). \
         Drop a repeated owner when that person is already in the line (\"her room\" → \"the room\")."
    );
    if lang_is_khmer(target_lang) {
        rule.push_str(
            " Khmer pattern — source \"then he sent her to her room\"; \
             too long to say: \"បន្ទាប់មកគាត់បានបញ្ជូននាងទៅបន្ទប់របស់នាង\"; \
             say: \"គាត់បានជួននាងទៅបន្ទប់\".",
        );
    }
    rule
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
        voice_rewrite_rule(),
        "2. Keep the scene true. Do not invent plot, names, or actions. Change the words so the line sounds spoken.".into(),
    ];
    let mut n: usize = 3;

    if style.fit_duration {
        rules.push(spoken_fit_rule(n, target_lang));
        n += 1;
    }
    if style.use_slang {
        rules.push(register_rule(n, target_lang));
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
        "You are a dubbing writer for film dialogue {src_name}into {lang_name}.\n\
         You know the script. Write a new spoken line, not a translation of each word.\n\
         It must sound like this person talking, in the same breath.\n\
         Active features: {feat}.\n\
         Rules:\n{}\n\n\
         Dialogue segments:\n{payload_json}",
        rules.join("\n")
    )
}

/// Second pass for lines whose spoken beats run past the slot.
pub fn build_fit_rewrite_prompt(payload: &serde_json::Value, target_lang: &str) -> String {
    let lang_name = if lang_is_khmer(target_lang) {
        "spoken Khmer"
    } else {
        target_lang
    };
    let body = serde_json::to_string(payload).unwrap_or_else(|_| "[]".to_string());
    format!(
        "You are tightening dubbed lines that are too long to say in the actor's slot.\n\
         Write new words in {lang_name} that this person would actually say. Keep the same voice.\n\
         If the line is slang, an insult, or a swear, keep that heat with a shorter spoken word. Do not polish it polite.\n\
         Keep who did the action. Drop fillers and repeated owners.\n\
         Each khmer_text must use at most max_units spoken beats (Khmer: syllables).\n\
         Pattern: \"then he sent her to her room\" is said \"គាត់បានជួននាងទៅបន្ទប់\", \
         not \"បន្ទាប់មកគាត់បានបញ្ជូននាងទៅបន្ទប់របស់នាង\".\n\
         \"What the hell are you doing?\" stays rough and short, not a textbook question.\n\
         Return STRICTLY a JSON array of objects with keys id and khmer_text.\n\n\
         Lines:\n{body}"
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
        assert!(prompt.contains("VOICE REWRITE"));
        assert!(prompt.contains("SPOKEN FIT"));
        assert!(prompt.contains("SLANG"));
        assert!(prompt.contains("swear"));
        assert!(prompt.contains("គាត់បានជួននាងទៅបន្ទប់"));
        assert!(prompt.contains("ឯងធ្វើអីហ្នឹង?"));
        assert!(!prompt.contains("EXPRESSION TAGS"));
        assert!(prompt.contains("duration-fit"));
        assert!(prompt.contains("slang/idiom"));
        let plain = TranslateStyle {
            fit_duration: true,
            use_slang: false,
            use_expression: false,
        };
        let quiet = build_dubbing_llm_prompt(&payload, "Khmer", "English", &plain);
        assert!(quiet.contains("VOICE REWRITE"));
        assert!(!quiet.contains("SLANG"));
    }

    #[test]
    fn test_spoken_fit_rejects_the_long_written_line() {
        let short = "គាត់បានជួននាងទៅបន្ទប់";
        let long = "បន្ទាប់មកគាត់បានបញ្ជូននាងទៅបន្ទប់របស់នាង";
        let short_u = spoken_units(short, "Khmer");
        let long_u = spoken_units(long, "Khmer");
        assert!(short_u >= 4, "short beats {short_u}");
        assert!(long_u > short_u + 2, "long {long_u} vs short {short_u}");
        let slot = (short_u as f64 / pace_rate("Khmer")).max(0.8);
        let quota = estimate_speech_quota(slot, "Khmer");
        assert!(short_u <= quota.max, "short {short_u} max {}", quota.max);
        assert!(long_u > quota.max, "long {long_u} should miss max {}", quota.max);
        let tagged = spoken_units("[sigh] គាត់បានជួននាងទៅបន្ទប់", "Khmer");
        assert_eq!(tagged, short_u);
    }
}
