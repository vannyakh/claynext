pub mod decoder;
pub mod demux;
pub mod demuxer;
pub mod encoder;
pub mod error;
pub mod muxer;
pub mod probe;
pub mod process;

// Re-export primary types and functions
pub use decoder::{
    decode_audio_pcm_f32, extract_frame_rgba, AudioFrame, PixelFormat, SeekMode, VideoFrame,
};
pub use demux::extract_audio_wav;
pub use demuxer::{extract_stream_copy, StreamSelector};
pub use encoder::{
    extract_still_image, is_encoder_available, run_export_job, AudioEncoderConfig, ExportJob,
    VideoEncoderConfig,
};
pub use error::{FfmpegError, Result};
pub use muxer::{mux_video_audio, ContainerFormat, MuxOptions};
pub use probe::{
    probe_media_file, AudioMetadata, MediaInspection, Rational, StreamInfo, StreamKindMetadata,
    VideoMetadata,
};
pub use process::{find_executable, FfmpegProgress, ManagedProcess, ProcessConfig};
