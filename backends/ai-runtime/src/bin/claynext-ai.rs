use claynext_ai_runtime::{
    align_speech_speed_result, build_dubbing_llm_prompt_from_request, build_fit_rewrite_prompt,
    build_llm_translation_prompt, calculate_ducked_background_volume,
    chunk_subtitles_for_translation, energy_vad_chunking, estimate_speech_quota, filter_ocr_results,
    fit_lines_to_speech, scan_burned_captions,
    is_rate_limit_status, parse_expression_tags, spoken_units,
    parse_retry_after, ApiKeyItem, CaptionScanRequest, DubPromptRequest, FitSpeechRequest,
    InferenceDeviceConfig, NativeKeyPool, OcrBox, RateLimitDecision, VadConfig, WhisperConfig,
};
use std::env;
use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

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
        "energy-vad" => {
            // Args: pcm_f32_path sample_rate [threshold]
            let path = args.get(2).map(|s| s.as_str()).unwrap_or("");
            let sample_rate: u32 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(16000);
            let threshold: f32 = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(0.22);
            match read_pcm_f32(path) {
                Ok(samples) => {
                    let mut cfg = VadConfig::default();
                    cfg.threshold = threshold;
                    let segments = energy_vad_chunking(&samples, sample_rate, &cfg);
                    println!("{}", serde_json::to_string(&segments).unwrap_or_default());
                }
                Err(e) => {
                    eprintln!("energy-vad failed: {e}");
                    std::process::exit(2);
                }
            }
        }
        "fit-speech" => {
            // JSON on stdin when the arg is "-", otherwise a file path or inline JSON.
            let raw = args.get(2).map(|s| s.as_str()).unwrap_or("-");
            let text = if raw == "-" {
                let mut buf = String::new();
                io::Read::read_to_string(&mut io::stdin(), &mut buf).ok();
                buf
            } else if Path::new(raw).is_file() {
                std::fs::read_to_string(raw).unwrap_or_default()
            } else {
                raw.to_string()
            };
            let req: FitSpeechRequest = serde_json::from_str(&text).unwrap_or_default();
            let fitted = fit_lines_to_speech(&req.lines, &req.turns);
            println!("{}", serde_json::to_string(&fitted).unwrap_or_default());
        }
        "llm-parse-retry" => {
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
            let keys_json = args.get(2).map(|s| s.as_str()).unwrap_or("[]");
            let provider = args.get(3).map(|s| s.as_str()).unwrap_or("gemini");
            let keys: Vec<ApiKeyItem> = serde_json::from_str(keys_json).unwrap_or_default();
            let pool = NativeKeyPool::new();
            let acquired = pool.acquire_key(&keys, provider);
            println!("{}", serde_json::to_string(&acquired).unwrap_or_default());
        }
        "llm-soonest-cooldown" => {
            let keys_json = args.get(2).map(|s| s.as_str()).unwrap_or("[]");
            let provider = args.get(3).map(|s| s.as_str()).unwrap_or("gemini");
            let keys: Vec<ApiKeyItem> = serde_json::from_str(keys_json).unwrap_or_default();
            let pool = NativeKeyPool::new();
            let wait = pool.soonest_cooldown(&keys, provider);
            println!("{{\"soonest_cooldown_secs\": {:.2}}}", wait);
        }
        "parse-expression-tags" => {
            let text = args.get(2).map(|s| s.as_str()).unwrap_or("");
            let segments = parse_expression_tags(text);
            println!("{}", serde_json::to_string(&segments).unwrap_or_default());
        }
        "chunk-subtitles" => {
            let text = args.get(2).map(|s| s.as_str()).unwrap_or("");
            let max_chars: usize = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(1500);
            let chunks = chunk_subtitles_for_translation(text, max_chars);
            println!("{}", serde_json::to_string(&chunks).unwrap_or_default());
        }
        "scan-captions" => {
            let raw = if args.get(2).map(|s| s.as_str()) == Some("-") {
                let mut buf = String::new();
                io::stdin().read_to_string(&mut buf).ok();
                buf
            } else {
                args.get(2).cloned().unwrap_or_default()
            };
            let req: CaptionScanRequest = match serde_json::from_str(&raw) {
                Ok(req) => req,
                Err(e) => {
                    eprintln!("Invalid caption scan request: {e}");
                    std::process::exit(2);
                }
            };
            match scan_burned_captions(&req, |pct, msg| {
                println!(
                    "{}",
                    serde_json::json!({"kind": "progress", "pct": pct, "message": msg})
                );
            }) {
                Ok(lines) => {
                    println!(
                        "{}",
                        serde_json::json!({"kind": "result", "segments": lines})
                    );
                }
                Err(e) => {
                    eprintln!("{e}");
                    std::process::exit(2);
                }
            }
        }
        "filter-ocr" => {
            let boxes_json = args.get(2).map(|s| s.as_str()).unwrap_or("[]");
            let min_conf: f32 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(0.5);
            let boxes: Vec<OcrBox> = serde_json::from_str(boxes_json).unwrap_or_default();
            let filtered = filter_ocr_results(&boxes, min_conf);
            println!("{}", serde_json::to_string(&filtered).unwrap_or_default());
        }
        "speech-quota" => {
            let duration: f64 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(0.0);
            let lang = args.get(3).map(|s| s.as_str()).unwrap_or("");
            let quota = estimate_speech_quota(duration, lang);
            println!("{}", serde_json::to_string(&quota).unwrap_or_default());
        }
        "spoken-units" => {
            let raw = args.get(2).cloned().unwrap_or_else(|| "{}".to_string());
            let value: serde_json::Value = serde_json::from_str(&raw).unwrap_or(serde_json::json!({}));
            let lang = value.get("lang").and_then(|v| v.as_str()).unwrap_or("");
            if let Some(texts) = value.get("texts").and_then(|v| v.as_array()) {
                let counts: Vec<i32> = texts
                    .iter()
                    .map(|item| spoken_units(item.as_str().unwrap_or(""), lang))
                    .collect();
                println!("{}", serde_json::to_string(&counts).unwrap_or_else(|_| "[]".into()));
            } else {
                let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
                println!("{}", spoken_units(text, lang));
            }
        }
        "build-fit-prompt" => {
            let raw = args.get(2).cloned().unwrap_or_else(|| "{}".to_string());
            let value: serde_json::Value = serde_json::from_str(&raw).unwrap_or(serde_json::json!({}));
            let lang = value
                .get("target_lang")
                .and_then(|v| v.as_str())
                .unwrap_or("Khmer");
            let lines = value.get("lines").cloned().unwrap_or(serde_json::json!([]));
            print!("{}", build_fit_rewrite_prompt(&lines, lang));
        }
        "build-dub-prompt" => {
            let raw = if args.get(2).map(|s| s.as_str()) == Some("-") {
                let mut buf = String::new();
                io::stdin().read_to_string(&mut buf).ok();
                buf
            } else {
                args.get(2).cloned().unwrap_or_else(|| "{}".to_string())
            };
            match serde_json::from_str::<DubPromptRequest>(&raw) {
                Ok(req) => {
                    let prompt = build_dubbing_llm_prompt_from_request(&req);
                    print!("{prompt}");
                }
                Err(e) => {
                    eprintln!("Invalid DubPromptRequest JSON: {e}");
                    std::process::exit(2);
                }
            }
        }
        "build-translate-prompt" => {
            // Args: source_lang target_lang text
            let source = args.get(2).map(|s| s.as_str()).unwrap_or("auto");
            let target = args.get(3).map(|s| s.as_str()).unwrap_or("en");
            let text = args.get(4).map(|s| s.as_str()).unwrap_or("");
            print!("{}", build_llm_translation_prompt(source, target, text));
        }
        "ducked-volume" => {
            // Args: base_volume attenuation_db
            let base: f32 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(1.0);
            let atten: f32 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(-12.0);
            let vol = calculate_ducked_background_volume(base, atten);
            println!("{{\"volume\":{vol}}}");
        }
        "align-speed" => {
            // Args: audio_dur slot_dur [min_speed] [max_speed]
            let audio: f64 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(0.0);
            let slot: f64 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(0.0);
            let min_s: f32 = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(0.65);
            let max_s: f32 = args.get(5).and_then(|s| s.parse().ok()).unwrap_or(1.85);
            let result = align_speech_speed_result(audio, slot, min_s, max_s);
            println!("{}", serde_json::to_string(&result).unwrap_or_default());
        }
        _ => {
            eprintln!("Claynext AI Runtime Tool");
            eprintln!(
                "Usage: claynext-ai [device | whisper-config | vad-sim | energy-vad | fit-speech | \
                 llm-parse-retry | llm-acquire | llm-soonest-cooldown | parse-expression-tags | \
                 chunk-subtitles | filter-ocr | scan-captions | speech-quota | spoken-units | \
                 build-dub-prompt | build-fit-prompt | build-translate-prompt | \
                 ducked-volume | align-speed]"
            );
            std::process::exit(1);
        }
    }
}

fn read_pcm_f32(path: &str) -> Result<Vec<f32>, String> {
    if path.is_empty() || !Path::new(path).is_file() {
        return Err("pcm file missing".into());
    }
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    if bytes.len() % 4 != 0 {
        return Err("pcm length not multiple of 4".into());
    }
    let mut samples = Vec::with_capacity(bytes.len() / 4);
    for chunk in bytes.chunks_exact(4) {
        samples.push(f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]));
    }
    Ok(samples)
}
