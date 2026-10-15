use crate::error::{FfmpegError, Result};
use std::env;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

#[derive(Debug, Clone)]
pub struct ProcessConfig {
    pub ffmpeg_path: Option<PathBuf>,
    pub ffprobe_path: Option<PathBuf>,
    pub timeout: Option<Duration>,
}

impl Default for ProcessConfig {
    fn default() -> Self {
        Self {
            ffmpeg_path: None,
            ffprobe_path: None,
            timeout: Some(Duration::from_secs(600)),
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct FfmpegProgress {
    pub frame: Option<u64>,
    pub fps: Option<f32>,
    pub time_seconds: Option<f64>,
    pub bitrate_kbps: Option<f32>,
    pub speed: Option<f32>,
}

pub fn parse_progress_line(line: &str) -> Option<FfmpegProgress> {
    if !line.contains("time=") && !line.contains("frame=") {
        return None;
    }

    let mut progress = FfmpegProgress::default();
    for part in line.split_whitespace() {
        if let Some((k, v)) = part.split_once('=') {
            match k {
                "frame" => {
                    progress.frame = v.parse::<u64>().ok();
                }
                "fps" => {
                    progress.fps = v.parse::<f32>().ok();
                }
                "time" => {
                    // HH:MM:SS.xx
                    progress.time_seconds = parse_time_str(v);
                }
                "bitrate" => {
                    let clean = v.trim_end_matches("kbits/s");
                    progress.bitrate_kbps = clean.parse::<f32>().ok();
                }
                "speed" => {
                    let clean = v.trim_end_matches('x');
                    progress.speed = clean.parse::<f32>().ok();
                }
                _ => {}
            }
        }
    }
    Some(progress)
}

fn parse_time_str(s: &str) -> Option<f64> {
    let parts: Vec<&str> = s.split(':').collect();
    if parts.len() == 3 {
        let h: f64 = parts[0].parse().ok()?;
        let m: f64 = parts[1].parse().ok()?;
        let sec: f64 = parts[2].parse().ok()?;
        Some(h * 3600.0 + m * 60.0 + sec)
    } else {
        s.parse::<f64>().ok()
    }
}

pub fn find_executable(name: &str) -> Option<PathBuf> {
    // 1. Explicit environment override
    let env_var = match name {
        "ffmpeg" => "CLAYNEXT_FFMPEG_PATH",
        "ffprobe" => "CLAYNEXT_FFPROBE_PATH",
        _ => "",
    };
    if !env_var.is_empty() {
        if let Ok(val) = env::var(env_var) {
            let p = PathBuf::from(val);
            if p.is_file() {
                return Some(p);
            }
        }
    }

    let exe_name = if cfg!(windows) {
        format!("{}.exe", name)
    } else {
        name.to_string()
    };

    // 2. Search PATH
    if let Ok(paths) = env::var("PATH") {
        for dir in env::split_paths(&paths) {
            let candidate = dir.join(&exe_name);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }

    // 3. Known Windows locations (WinGet, AppData)
    #[cfg(windows)]
    {
        if let Ok(local_appdata) = env::var("LOCALAPPDATA") {
            let winget_link = PathBuf::from(&local_appdata)
                .join("Microsoft")
                .join("WinGet")
                .join("Links")
                .join(&exe_name);
            if winget_link.is_file() {
                return Some(winget_link);
            }
        }
    }

    None
}

pub struct ManagedProcess {
    child: Child,
    cancel_token: Option<Arc<AtomicBool>>,
    timeout: Option<Duration>,
    start_time: Instant,
}

impl ManagedProcess {
    pub fn spawn(
        mut cmd: Command,
        cancel_token: Option<Arc<AtomicBool>>,
        timeout: Option<Duration>,
    ) -> Result<Self> {
        cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
        let child = cmd.spawn().map_err(FfmpegError::ProcessSpawn)?;

        Ok(Self {
            child,
            cancel_token,
            timeout,
            start_time: Instant::now(),
        })
    }

    pub fn wait_with_progress<F>(mut self, mut on_progress: F) -> Result<String>
    where
        F: FnMut(FfmpegProgress),
    {
        let stderr = self
            .child
            .stderr
            .take()
            .ok_or_else(|| FfmpegError::InvalidInput("Failed to capture stderr".into()))?;

        let mut reader = BufReader::new(stderr);
        let mut line_buf = String::new();
        let mut all_stderr = String::new();

        loop {
            // Check cancellation
            if let Some(ref token) = self.cancel_token {
                if token.load(Ordering::Relaxed) {
                    let _ = self.child.kill();
                    return Err(FfmpegError::Cancelled);
                }
            }

            // Check timeout
            if let Some(limit) = self.timeout {
                if self.start_time.elapsed() > limit {
                    let _ = self.child.kill();
                    return Err(FfmpegError::ProcessTimeout {
                        timeout_secs: limit.as_secs(),
                    });
                }
            }

            line_buf.clear();
            match reader.read_line(&mut line_buf) {
                Ok(0) => break, // EOF
                Ok(_) => {
                    all_stderr.push_str(&line_buf);
                    if let Some(prog) = parse_progress_line(&line_buf) {
                        on_progress(prog);
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(10));
                }
                Err(e) => return Err(FfmpegError::Io(e)),
            }
        }

        let status = self.child.wait().map_err(FfmpegError::Io)?;
        if !status.success() {
            return Err(FfmpegError::ProcessFailed {
                exit_code: status.code(),
                stderr: all_stderr,
            });
        }

        Ok(all_stderr)
    }
}
