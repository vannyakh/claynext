//! claynext-bench: High-precision performance microbenchmarks for core multimedia algorithms.

use editor_audio::{calculate_ducked_gain, DuckingConfig, SpeechInterval};
use editor_media::generate_waveform_peaks;
use editor_video::{calculate_fit_geometry, FitMode};
use std::time::Instant;

fn main() {
    println!("========================================================");
    println!("     Claynext Studio — Rust Core Benchmark Suite        ");
    println!("========================================================");

    // 1. Waveform Peak Decimation (1,000,000 PCM samples down to 2,000 bins)
    let pcm_samples: Vec<f32> = (0..1_000_000).map(|i| ((i as f32) * 0.05).sin()).collect();

    let start = Instant::now();
    let iters = 20;
    for _ in 0..iters {
        let _ = generate_waveform_peaks(&pcm_samples, 2000);
    }
    let elapsed = start.elapsed();
    let per_run = elapsed / iters;
    println!(
        "[Waveform Binning] 1M samples -> 2000 bins: {:?} per iteration ({:.2} Msamples/sec)",
        per_run,
        (1.0 / per_run.as_secs_f64())
    );

    // 2. Audio Ducking Gain Calculation (100,000 sample points against 50 speech intervals)
    let intervals: Vec<SpeechInterval> = (0..50)
        .map(|i| SpeechInterval {
            start_seconds: (i * 10) as f64,
            end_seconds: (i * 10 + 6) as f64,
        })
        .collect();
    let config = DuckingConfig::default();

    let start = Instant::now();
    let mut dummy_sum = 0.0f32;
    for t in 0..100_000 {
        let sec = (t as f64) * 0.005;
        dummy_sum += calculate_ducked_gain(sec, &intervals, &config);
    }
    let elapsed = start.elapsed();
    println!(
        "[Audio Ducking] 100K timecode gain queries: {:?} ({:.2} M queries/sec)",
        elapsed,
        (0.1 / elapsed.as_secs_f64())
    );

    // 3. Viewport Geometry & Letterbox math (1,000,000 layout recalculations)
    let start = Instant::now();
    for _ in 0..1_000_000 {
        let _ = calculate_fit_geometry(1920, 1080, 1080, 1920, FitMode::Fit);
    }
    let elapsed = start.elapsed();
    println!(
        "[Viewport Fit Geometry] 1M geometry calculations: {:?} ({:.2} M ops/sec)",
        elapsed,
        (1.0 / elapsed.as_secs_f64())
    );

    println!("========================================================");
    println!("     All Benchmarks Completed Successfully!             ");
    println!("========================================================");
    if dummy_sum < 0.0 {
        println!("Checksum: {}", dummy_sum);
    }
}
