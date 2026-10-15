use claynext_ai_runtime::{
    chunk_subtitles_for_translation, energy_vad_chunking, filter_ocr_results, is_rate_limit_status,
    parse_expression_tags, parse_retry_after, ApiKeyItem, InferenceDeviceConfig, NativeKeyPool,
    OcrBox, RateLimitDecision, VadConfig, WhisperConfig,
};
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    let command = args.get(1).map(|s| s.as_str()).unwrap_or("info");

    match command {
        "device" => {
            let dev = InferenceDeviceConfig::default();
            println!("{}", serde_json::to_string_pretty(&dev).unwrap_or_default());
        }
        "whisper-config" => {
            let conf = WhisperConfig::default();
            println!(
                "{}",
                serde_json::to_string_pretty(&conf).unwrap_or_default()
            );
        }
        "vad-sim" => {
            let sample_rate = 16000;
            let mut samples = vec![0.0f32; sample_rate as usize * 3];
            let start_idx = sample_rate as usize;
            let end_idx = sample_rate as usize * 2;
            for (idx, sample) in samples[start_idx..end_idx].iter_mut().enumerate() {
                let i = start_idx + idx;
                *sample = (i as f32 * 0.05).sin() * 0.8;
            }
            let segments = energy_vad_chunking(&samples, sample_rate, &VadConfig::default());
            println!(
                "{}",
                serde_json::to_string_pretty(&segments).unwrap_or_default()
            );
        }
        "llm-parse-retry" => {
            // Args: status [header] [body]
            let status: u16 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(200);
            let header = args.get(3).map(|s| s.as_str());
            let body = args.get(4).map(|s| s.as_str()).unwrap_or("");

            let limited = is_rate_limit_status(status, body);
            let retry_after = parse_retry_after(header, body);
            let decision = RateLimitDecision {
                is_rate_limit: limited,
                retry_after_secs: retry_after,
            };
            println!("{}", serde_json::to_string(&decision).unwrap_or_default());
        }
        "llm-acquire" => {
            // Args: keys_json provider
            let keys_json = args.get(2).map(|s| s.as_str()).unwrap_or("[]");
            let provider = args.get(3).map(|s| s.as_str()).unwrap_or("gemini");
            let keys: Vec<ApiKeyItem> = serde_json::from_str(keys_json).unwrap_or_default();
            let pool = NativeKeyPool::new();
            let acquired = pool.acquire_key(&keys, provider);
            println!("{}", serde_json::to_string(&acquired).unwrap_or_default());
        }
        "llm-soonest-cooldown" => {
            // Args: keys_json provider
            let keys_json = args.get(2).map(|s| s.as_str()).unwrap_or("[]");
            let provider = args.get(3).map(|s| s.as_str()).unwrap_or("gemini");
            let keys: Vec<ApiKeyItem> = serde_json::from_str(keys_json).unwrap_or_default();
            let pool = NativeKeyPool::new();
            let wait = pool.soonest_cooldown(&keys, provider);
            println!("{{\"soonest_cooldown_secs\": {:.2}}}", wait);
        }
        "parse-expression-tags" => {
            // Args: text
            let text = args.get(2).map(|s| s.as_str()).unwrap_or("");
            let segments = parse_expression_tags(text);
            println!("{}", serde_json::to_string(&segments).unwrap_or_default());
        }
        "chunk-subtitles" => {
            // Args: text [max_chars]
            let text = args.get(2).map(|s| s.as_str()).unwrap_or("");
            let max_chars: usize = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(1500);
            let chunks = chunk_subtitles_for_translation(text, max_chars);
            println!("{}", serde_json::to_string(&chunks).unwrap_or_default());
        }
        "filter-ocr" => {
            // Args: boxes_json [min_confidence]
            let boxes_json = args.get(2).map(|s| s.as_str()).unwrap_or("[]");
            let min_conf: f32 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(0.5);
            let boxes: Vec<OcrBox> = serde_json::from_str(boxes_json).unwrap_or_default();
            let filtered = filter_ocr_results(&boxes, min_conf);
            println!("{}", serde_json::to_string(&filtered).unwrap_or_default());
        }
        _ => {
            eprintln!("Claynext AI Runtime Tool");
            eprintln!("Usage: claynext-ai [device | whisper-config | vad-sim | llm-parse-retry | llm-acquire | llm-soonest-cooldown | parse-expression-tags | chunk-subtitles | filter-ocr]");
            std::process::exit(1);
        }
    }
}
