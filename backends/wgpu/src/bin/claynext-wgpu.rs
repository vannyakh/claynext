use claynext_wgpu::{TextureDescriptor, WgpuDeviceInfo, COLOR_ADJUST_WGSL};
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    let command = args.get(1).map(|s| s.as_str()).unwrap_or("info");

    match command {
        "info" => {
            let info = WgpuDeviceInfo::default();
            println!(
                "{}",
                serde_json::to_string_pretty(&info).unwrap_or_default()
            );
        }
        "shader" => {
            println!("{}", COLOR_ADJUST_WGSL);
        }
        "calc-texture" => {
            let width = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(1920);
            let height = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(1080);
            let desc = TextureDescriptor::new_rgba(width, height);
            println!(
                "Texture {}x{} RGBA size: {} bytes ({:.2} MB)",
                desc.width,
                desc.height,
                desc.size_bytes(),
                desc.size_bytes() as f64 / 1_048_576.0
            );
        }
        _ => {
            eprintln!("Claynext WGPU Tool");
            eprintln!("Usage: claynext-wgpu [info | shader | calc-texture [width] [height]]");
            std::process::exit(1);
        }
    }
}
