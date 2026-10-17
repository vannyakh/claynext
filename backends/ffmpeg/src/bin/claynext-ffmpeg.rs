use claynext_ffmpeg::{
    decode_audio_pcm_f32, extract_audio_wav, extract_frame_rgba, extract_still_image,
    is_encoder_available, mux_video_audio, probe_media_file, run_export_job, AudioEncoderConfig,
    ExportJob, MuxOptions, SeekMode, VideoEncoderConfig,
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
                let width = args.get(4).and_then(|s| s.parse::<u32>().ok());
                let height = args.get(5).and_then(|s| s.parse::<u32>().ok());
                match extract_frame_rgba(input, ts, width, height, SeekMode::Accurate, None) {
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
                eprintln!(
                    "Usage: claynext-ffmpeg extract-frame <video_file> <timestamp_secs> [width] [height]"
                );
                std::process::exit(1);
            }
        }
        "extract-still" => {
            // claynext-ffmpeg extract-still <input> <output.jpg> [timestamp] [max_width]
            if args.len() >= 4 {
                let input = Path::new(&args[2]);
                let output = Path::new(&args[3]);
                let ts = args.get(4).and_then(|s| s.parse::<f64>().ok()).unwrap_or(1.0);
                let max_w = args.get(5).and_then(|s| s.parse::<u32>().ok());
                match extract_still_image(input, output, ts, max_w) {
                    Ok(_) => println!("Wrote still: {}", output.display()),
                    Err(e) => {
                        eprintln!("Still extraction error: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!(
                    "Usage: claynext-ffmpeg extract-still <input> <output> [timestamp_secs] [max_width]"
                );
                std::process::exit(1);
            }
        }
        "decode-audio" => {
            // Args: <media> [sample_rate] [channels] [output.f32]
            if args.len() >= 3 {
                let input = Path::new(&args[2]);
                let rate = args
                    .get(3)
                    .and_then(|s| s.parse::<u32>().ok())
                    .unwrap_or(16000);
                let channels = args
                    .get(4)
                    .and_then(|s| s.parse::<u32>().ok())
                    .unwrap_or(1);
                let out_path = args.get(5).map(PathBuf::from);
                match decode_audio_pcm_f32(input, rate, channels, None, None, None) {
                    Ok(frame) => {
                        if let Some(out) = out_path.as_ref() {
                            use std::io::Write;
                            if let Some(parent) = out.parent() {
                                let _ = std::fs::create_dir_all(parent);
                            }
                            let mut bytes = Vec::with_capacity(frame.samples.len() * 4);
                            for s in &frame.samples {
                                bytes.extend_from_slice(&s.to_le_bytes());
                            }
                            if let Err(e) = std::fs::File::create(out).and_then(|mut f| f.write_all(&bytes)) {
                                eprintln!("Failed to write PCM: {}", e);
                                std::process::exit(1);
                            }
                        }
                        let duration = frame.samples.len() as f64
                            / (frame.sample_rate as f64 * frame.channels.max(1) as f64);
                        // Machine-readable JSON for the Python bridge.
                        println!(
                            "{{\"sample_rate\":{},\"channels\":{},\"sample_count\":{},\"duration_sec\":{:.6}}}",
                            frame.sample_rate,
                            frame.channels,
                            frame.samples.len(),
                            duration
                        );
                    }
                    Err(e) => {
                        eprintln!("Audio decode error: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!(
                    "Usage: claynext-ffmpeg decode-audio <media_file> [sample_rate] [channels] [output.f32]"
                );
                std::process::exit(1);
            }
        }
        "export" => {
            if args.len() >= 4 {
                let input = PathBuf::from(&args[2]);
                let output = PathBuf::from(&args[3]);
                let opts = parse_export_flags(&args[4..]);

                let mut video = VideoEncoderConfig::default();
                video.codec = opts.codec.unwrap_or_else(|| "libx264".into());
                video.crf = Some(opts.crf.unwrap_or(22));
                video.preset = opts.preset.unwrap_or_else(|| "veryfast".into());
                video.width = opts.width;
                video.height = opts.height;
                if let Some(fps) = opts.fps {
                    video.fps = Some(fps);
                }

                let mut audio = AudioEncoderConfig::default();
                if let Some(sr) = opts.sample_rate {
                    audio.sample_rate = Some(sr);
                }
                if let Some(ch) = opts.channels {
                    audio.channels = Some(ch);
                }
                if let Some(br) = opts.audio_bitrate {
                    audio.bitrate_kbps = br;
                }

                let job = ExportJob {
                    input_path: input,
                    output_path: output,
                    video,
                    audio,
                    start_time_secs: opts.start,
                    duration_secs: opts.duration,
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
                eprintln!(
                    "Usage: claynext-ffmpeg export <input> <output> [--codec libx264] [--crf 22] [--preset veryfast] [--width N] [--height N] [--fps N] [--start SEC] [--duration SEC] [--sample-rate 44100] [--channels 2] [--audio-bitrate 192]"
                );
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
        "demux-audio" => {
            // Args: <media> <output.wav> [sample_rate] [channels]
            if args.len() >= 4 {
                let input = Path::new(&args[2]);
                let output = Path::new(&args[3]);
                let rate = args
                    .get(4)
                    .and_then(|s| s.parse::<u32>().ok())
                    .unwrap_or(48000);
                let channels = args
                    .get(5)
                    .and_then(|s| s.parse::<u32>().ok())
                    .unwrap_or(2);
                match extract_audio_wav(input, output, rate, channels) {
                    Ok(()) => println!(
                        "{{\"ok\":true,\"output\":\"{}\",\"sample_rate\":{},\"channels\":{}}}",
                        output.display().to_string().replace('\\', "/"),
                        rate,
                        channels
                    ),
                    Err(e) => {
                        eprintln!("demux-audio error: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!(
                    "Usage: claynext-ffmpeg demux-audio <media> <output.wav> [sample_rate] [channels]"
                );
                std::process::exit(1);
            }
        }
        _ => {
            eprintln!("Claynext FFmpeg CLI Tool");
            eprintln!(
                "Commands: probe, extract-frame, extract-still, decode-audio, demux-audio, \
                 export, check-encoder, mux"
            );
            std::process::exit(1);
        }
    }
}

#[derive(Default)]
struct ExportFlags {
    codec: Option<String>,
    crf: Option<u32>,
    preset: Option<String>,
    width: Option<u32>,
    height: Option<u32>,
    fps: Option<f32>,
    start: Option<f64>,
    duration: Option<f64>,
    sample_rate: Option<u32>,
    channels: Option<u32>,
    audio_bitrate: Option<u32>,
}

fn parse_export_flags(args: &[String]) -> ExportFlags {
    let mut flags = ExportFlags::default();
    let mut i = 0;
    while i < args.len() {
        let key = args[i].as_str();
        let val = args.get(i + 1).map(|s| s.as_str());
        match (key, val) {
            ("--codec", Some(v)) => {
                flags.codec = Some(v.to_string());
                i += 2;
            }
            ("--crf", Some(v)) => {
                flags.crf = v.parse().ok();
                i += 2;
            }
            ("--preset", Some(v)) => {
                flags.preset = Some(v.to_string());
                i += 2;
            }
            ("--width", Some(v)) => {
                flags.width = v.parse().ok();
                i += 2;
            }
            ("--height", Some(v)) => {
                flags.height = v.parse().ok();
                i += 2;
            }
            ("--fps", Some(v)) => {
                flags.fps = v.parse().ok();
                i += 2;
            }
            ("--start", Some(v)) => {
                flags.start = v.parse().ok();
                i += 2;
            }
            ("--duration", Some(v)) => {
                flags.duration = v.parse().ok();
                i += 2;
            }
            ("--sample-rate", Some(v)) => {
                flags.sample_rate = v.parse().ok();
                i += 2;
            }
            ("--channels", Some(v)) => {
                flags.channels = v.parse().ok();
                i += 2;
            }
            ("--audio-bitrate", Some(v)) => {
                flags.audio_bitrate = v.parse().ok();
                i += 2;
            }
            _ => i += 1,
        }
    }
    flags
}
