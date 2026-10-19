use claynext_cpu::{compute_audio_stats, extract_waveform_peaks, plan_json, resample_linear};
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    let command = args.get(1).map(|s| s.as_str()).unwrap_or("help");

    match command {
        "hardware" => println!("{}", plan_json()),
        "benchmark" => {
            let samples: Vec<f32> = (0..1_000_000).map(|i| (i as f32 * 0.01).sin()).collect();
            let start = std::time::Instant::now();
            let (peak, rms) = compute_audio_stats(&samples);
            let peaks = extract_waveform_peaks(&samples, 100);
            let resampled = resample_linear(&samples, 48000, 16000);
            let elapsed = start.elapsed();

            println!("CPU Benchmark completed in {:?}", elapsed);
            println!(
                "Peak: {:.4}, RMS: {:.4}, Peaks bins: {}, Resampled len: {}",
                peak,
                rms,
                peaks.len(),
                resampled.len()
            );
        }
        _ => {
            eprintln!("Claynext CPU Engine Tool");
            eprintln!("Usage: claynext-cpu <hardware|benchmark>");
            std::process::exit(1);
        }
    }
}
