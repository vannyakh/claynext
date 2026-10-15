from asyncio import subprocess
import os
from pathlib import Path
from typing import Callable, List, Dict, Any
from moviepy import VideoFileClip, TextClip, CompositeVideoClip
import imageio_ffmpeg as ffmpeg_bin


class VideoEngine:
    """
    Video Processing & FFmpeg / MoviePy Core Engine.
    Provides audio extraction, video clipping/trimming, subtitle burn-in, and frame sampling.
    """

    @staticmethod
    def get_ffmpeg_path() -> str:
        """Returns binary path of imageio-ffmpeg bundled binary."""
        return ffmpeg_bin.get_ffmpeg_exe()

    @staticmethod
    def extract_audio(
        video_path: str,
        output_audio_path: str,
        format: str = "wav",
        sample_rate: int = 48000,
        channels: int = 2,
        progress_callback: Callable = None,
    ) -> str:
        """
        Extracts audio track from a video file with configurable sample rate and channels.
        """
        if progress_callback:
            progress_callback(20, f"Extracting audio ({format.upper()}) at {sample_rate}Hz…")

        from claynext.services.ffmpeg_service import get_ffmpeg
        ffmpeg_bin = get_ffmpeg()
        Path(output_audio_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg_bin, "-y", "-i", video_path,
            "-vn",
            "-ar", str(sample_rate),
            "-ac", str(channels),
            output_audio_path,
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"FFmpeg audio extraction failed: {err}")

        if progress_callback:
            progress_callback(100, f"Audio extracted successfully: {Path(output_audio_path).name}")

        return output_audio_path

    @staticmethod
    def extract_frame_at_time(video_path: str, timestamp_sec: float, output_image_path: str, progress_callback: Callable = None) -> str:
        """
        Extracts a single image frame snapshot at specified timestamp for OCR analysis.
        """
        if progress_callback:
            progress_callback(20, f"Extracting frame snapshot at {timestamp_sec:.2f}s...")

        clip = VideoFileClip(video_path)
        Path(output_image_path).parent.mkdir(parents=True, exist_ok=True)
        clip.save_frame(output_image_path, t=timestamp_sec)
        clip.close()

        if progress_callback:
            progress_callback(100, f"Frame snapshot saved to {Path(output_image_path).name}")

        return output_image_path

    @staticmethod
    def trim_video(video_path: str, start_sec: float, end_sec: float, output_path: str, progress_callback: Callable = None) -> str:
        """
        Trims video from start_sec to end_sec using MoviePy.
        """
        if progress_callback:
            progress_callback(15, f"Loading clip range [{start_sec:.1f}s - {end_sec:.1f}s]...")

        clip = VideoFileClip(video_path).subclipped(start_sec, end_sec)

        if progress_callback:
            progress_callback(50, f"Rendering trimmed video clip...")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        clip.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
        clip.close()

        if progress_callback:
            progress_callback(100, f"Video trimmed successfully: {Path(output_path).name}")

        return output_path

    @staticmethod
    def get_video_info(video_path: str) -> Dict[str, Any]:
        """
        Returns metadata for video file (duration, fps, size).
        """
        try:
            clip = VideoFileClip(video_path)
            info = {
                "duration": clip.duration,
                "fps": clip.fps,
                "size": clip.size, # (width, height)
                "filename": Path(video_path).name
            }
            clip.close()
            return info
        except Exception as e:
            return {"duration": 0, "fps": 0, "size": (0, 0), "filename": Path(video_path).name, "error": str(e)}
