use claynext_ai_runtime::{energy_vad_chunking, InferenceDeviceConfig, VadConfig, WhisperConfig};
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
            // Generate 3 seconds of dummy audio: 1s silence, 1s tone (speech), 1s silence
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
        _ => {
            eprintln!("Claynext AI Runtime Tool");
            eprintln!("Usage: claynext-ai [device | whisper-config | vad-sim]");
            std::process::exit(1);
        }
    }
}
