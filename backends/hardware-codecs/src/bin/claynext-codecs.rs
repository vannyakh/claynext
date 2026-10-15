use claynext_hardware_codecs::{detect_system_gpus, select_optimal_video_encoder};
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    let command = args.get(1).map(|s| s.as_str()).unwrap_or("detect");

    match command {
        "detect" => {
            let gpus = detect_system_gpus();
            println!(
                "{}",
                serde_json::to_string_pretty(&gpus).unwrap_or_default()
            );
        }
        "optimal" => {
            let prefer_hevc = args.get(2).map(|s| s == "--hevc").unwrap_or(true);
            let selected = select_optimal_video_encoder(prefer_hevc);
            println!(
                "{}",
                serde_json::to_string_pretty(&selected).unwrap_or_default()
            );
        }
        "ffmpeg-args" => {
            let prefer_hevc = args.get(2).map(|s| s == "--hevc").unwrap_or(true);
            let selected = select_optimal_video_encoder(prefer_hevc);
            println!("{}", selected.to_ffmpeg_args().join(" "));
        }
        _ => {
            eprintln!("Usage: claynext-codecs [detect | optimal [--hevc|--h264] | ffmpeg-args]");
            std::process::exit(1);
        }
    }
}
