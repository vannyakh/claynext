use claynext_ffmpeg::{
    decode_audio_pcm_f32, extract_frame_rgba, extract_stream_copy, is_encoder_available,
    mux_video_audio, probe_media_file, run_export_job, AudioEncoderConfig, ExportJob, MuxOptions,
    SeekMode, StreamSelector, VideoEncoderConfig,
};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

fn generate_synthetic_fixture(output: &Path) {
    if output.exists() {
        return;
    }

    if let Some(parent) = output.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    // Generate a 1.5s 320x240 30fps test video with a 440Hz sine wave audio track using ffmpeg
    let status = Command::new("ffmpeg")
        .args([
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1.5:size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            output.to_str().unwrap(),
        ])
        .status();

    assert!(
        status.is_ok(),
        "Failed to invoke ffmpeg to generate test video"
    );
    assert!(
        status.unwrap().success(),
        "FFmpeg failed to create test fixture"
    );
}

#[test]
fn test_encoder_availability() {
    assert!(
        is_encoder_available("libx264"),
        "libx264 should be available in FFmpeg"
    );
    assert!(
        is_encoder_available("aac"),
        "aac should be available in FFmpeg"
    );
    assert!(
        !is_encoder_available("non_existent_fake_codec_xyz"),
        "Fake codec should not be available"
    );
}

#[test]
fn test_ffmpeg_milestone_b1_end_to_end() {
    let temp_dir = std::env::temp_dir().join("claynext_test_ffmpeg_b1");
    let _ = std::fs::create_dir_all(&temp_dir);

    let sample_video = temp_dir.join("sample_320x240.mp4");
    generate_synthetic_fixture(&sample_video);
    assert!(sample_video.is_file(), "Sample video fixture must exist");

    // 1. Probe test
    let probe_res = probe_media_file(&sample_video);
    assert!(probe_res.is_ok(), "Probe should succeed on valid video");
    let inspection = probe_res.unwrap();
    assert!(
        inspection.duration_seconds >= 1.4,
        "Duration should be ~1.5s"
    );
    assert_eq!(
        inspection.streams.len(),
        2,
        "Fixture should have video + audio streams"
    );

    let video_info = inspection.video_stream();
    assert!(video_info.is_some(), "Video stream must be detected");
    let (_, v_meta) = video_info.unwrap();
    assert_eq!(v_meta.width, 320);
    assert_eq!(v_meta.height, 240);
    assert_eq!(v_meta.pixel_format, "yuv420p");

    let audio_info = inspection.audio_stream();
    assert!(audio_info.is_some(), "Audio stream must be detected");
    let (_, a_meta) = audio_info.unwrap();
    assert!(a_meta.sample_rate > 0);
    assert!(a_meta.channels >= 1);

    // 2. Frame Extraction test
    let frame_res = extract_frame_rgba(&sample_video, 0.5, None, None, SeekMode::Accurate, None);
    assert!(frame_res.is_ok(), "Frame extraction should succeed at 0.5s");
    let frame = frame_res.unwrap();
    assert_eq!(frame.width, 320);
    assert_eq!(frame.height, 240);
    assert_eq!(
        frame.data.len(),
        320 * 240 * 4,
        "RGBA buffer must match width*height*4"
    );

    // 3. Audio PCM Decoding test
    let audio_res = decode_audio_pcm_f32(&sample_video, 16000, 1, Some(0.0), Some(1.0), None);
    assert!(audio_res.is_ok(), "Audio PCM decoding should succeed");
    let audio_frame = audio_res.unwrap();
    assert_eq!(audio_frame.sample_rate, 16000);
    assert_eq!(audio_frame.channels, 1);
    assert!(
        audio_frame.samples.len() >= 15000,
        "Should have ~16000 samples for 1 second"
    );

    // 4. Video Transcode / Export test
    let exported_video = temp_dir.join("exported_640x480.mp4");
    let export_job = ExportJob {
        input_path: sample_video.clone(),
        output_path: exported_video.clone(),
        video: VideoEncoderConfig {
            codec: "libx264".into(),
            width: Some(640),
            height: Some(480),
            fps: Some(30.0),
            crf: Some(23),
            bitrate_kbps: None,
            preset: "ultrafast".into(),
            pixel_format: "yuv420p".into(),
        },
        audio: AudioEncoderConfig::default(),
        start_time_secs: None,
        duration_secs: Some(1.0),
    };

    let mut progress_calls = 0;
    let export_res = run_export_job(&export_job, None, None, |_p| {
        progress_calls += 1;
    });
    assert!(export_res.is_ok(), "Transcode export should succeed");
    assert!(exported_video.is_file(), "Exported video file must exist");

    // Verify exported video metadata
    let exported_inspection =
        probe_media_file(&exported_video).expect("Exported file must probe successfully");
    let (_, exp_v) = exported_inspection
        .video_stream()
        .expect("Exported video stream missing");
    assert_eq!(exp_v.width, 640);
    assert_eq!(exp_v.height, 480);

    // 5. Demux Stream Copy test
    let demuxed_audio = temp_dir.join("extracted_audio.aac");
    let demux_res = extract_stream_copy(
        &sample_video,
        &demuxed_audio,
        StreamSelector::FirstAudio,
        None,
        None,
    );
    assert!(demux_res.is_ok(), "Demux stream copy should succeed");
    assert!(demuxed_audio.is_file(), "Demuxed audio file must exist");

    // 6. Muxing Video + Audio test
    let demuxed_video = temp_dir.join("extracted_video.mp4");
    let _ = extract_stream_copy(
        &sample_video,
        &demuxed_video,
        StreamSelector::FirstVideo,
        None,
        None,
    );

    let remuxed_output = temp_dir.join("remuxed_final.mp4");
    let mux_res = mux_video_audio(
        &demuxed_video,
        &demuxed_audio,
        &remuxed_output,
        &MuxOptions::default(),
    );
    assert!(mux_res.is_ok(), "Remuxing should succeed");
    assert!(remuxed_output.is_file(), "Remuxed output must exist");

    // 7. Cancellation token test
    let cancel_token = Arc::new(AtomicBool::new(true)); // Pre-cancelled
    let cancel_export = temp_dir.join("should_be_cancelled.mp4");
    let mut cancel_job = export_job.clone();
    cancel_job.output_path = cancel_export;
    let cancel_res = run_export_job(&cancel_job, Some(cancel_token), None, |_| {});
    assert!(cancel_res.is_err(), "Pre-cancelled job must return Err");
}

#[test]
fn test_error_handling() {
    let non_existent = PathBuf::from("Z:/non_existent_path_12345/video.mp4");
    let res = probe_media_file(&non_existent);
    assert!(res.is_err(), "Probing non-existent file must error");
}
