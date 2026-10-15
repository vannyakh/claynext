use claynext_ffmpeg::{
    decode_audio_pcm_f32, extract_frame_rgba, is_encoder_available, mux_video_audio,
    probe_media_file, run_export_job, AudioEncoderConfig, ExportJob, MuxOptions, SeekMode,
    VideoEncoderConfig,
};
use std::env;
use std::path::{Path, PathBuf};

fn main() {
    let args: Vec<String> = env::args().collect();
    let command = args.get(1).map(|s| s.as_str()).unwrap_or("help");

    match command {
        "probe" => {
            if let Some(path_str) = args.get(2) {
                match probe_media_file(Path::new(path_str)) {
                    Ok(info) => {
                        println!(
                            "{}",
                            serde_json::to_string_pretty(&info).unwrap_or_default()
                        );
                    }
                    Err(e) => {
                        eprintln!("Probe error: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!("Usage: claynext-ffmpeg probe <file_path>");
                std::process::exit(1);
            }
        }
        "extract-frame" => {
            if args.len() >= 4 {
                let input = Path::new(&args[2]);
                let ts = args[3].parse::<f64>().unwrap_or(0.0);
                match extract_frame_rgba(input, ts, None, None, SeekMode::Accurate, None) {
                    Ok(frame) => {
                        println!(
                            "Extracted frame at {:.3}s: {}x{} RGBA ({} bytes)",
                            frame.pts,
                            frame.width,
                            frame.height,
                            frame.data.len()
                        );
                    }
                    Err(e) => {
                        eprintln!("Frame extraction error: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!("Usage: claynext-ffmpeg extract-frame <video_file> <timestamp_secs>");
                std::process::exit(1);
            }
        }
        "decode-audio" => {
            if args.len() >= 3 {
                let input = Path::new(&args[2]);
                match decode_audio_pcm_f32(input, 16000, 1, None, None, None) {
                    Ok(frame) => {
                        println!(
                            "Decoded audio: {} samples (16kHz mono), {:.2}s duration",
                            frame.samples.len(),
                            frame.samples.len() as f64 / 16000.0
                        );
                    }
                    Err(e) => {
                        eprintln!("Audio decode error: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!("Usage: claynext-ffmpeg decode-audio <media_file>");
                std::process::exit(1);
            }
        }
        "export" => {
            if args.len() >= 4 {
                let input = PathBuf::from(&args[2]);
                let output = PathBuf::from(&args[3]);
                let job = ExportJob {
                    input_path: input,
                    output_path: output,
                    video: VideoEncoderConfig::default(),
                    audio: AudioEncoderConfig::default(),
                    start_time_secs: None,
                    duration_secs: None,
                };
                match run_export_job(&job, None, None, |p| {
                    if let Some(t) = p.time_seconds {
                        print!("\rExporting: time={:.2}s", t);
                    }
                }) {
                    Ok(_) => println!("\nExport finished successfully!"),
                    Err(e) => {
                        eprintln!("\nExport error: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!("Usage: claynext-ffmpeg export <input> <output>");
                std::process::exit(1);
            }
        }
        "check-encoder" => {
            if let Some(codec) = args.get(2) {
                let available = is_encoder_available(codec);
                println!("Encoder '{}' available: {}", codec, available);
            } else {
                eprintln!("Usage: claynext-ffmpeg check-encoder <encoder_name>");
                std::process::exit(1);
            }
        }
        "mux" => {
            if args.len() >= 5 {
                let video = Path::new(&args[2]);
                let audio = Path::new(&args[3]);
                let output = Path::new(&args[4]);
                match mux_video_audio(video, audio, output, &MuxOptions::default()) {
                    Ok(_) => println!("Muxed successfully to: {}", output.display()),
                    Err(e) => {
                        eprintln!("Mux error: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!("Usage: claynext-ffmpeg mux <video_in> <audio_in> <output>");
                std::process::exit(1);
            }
        }
        _ => {
            eprintln!("Claynext FFmpeg CLI Tool");
            eprintln!("Commands: probe, extract-frame, decode-audio, export, check-encoder, mux");
            std::process::exit(1);
        }
    }
}
