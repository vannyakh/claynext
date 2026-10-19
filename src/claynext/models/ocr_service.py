"""
Image and Video Frame Optical Character Recognition (OCR) Engine.
Extracts hardcoded / burned-in subtitles from video frames with custom capture zone tracking.
"""
from __future__ import annotations

import base64
import difflib
import io
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

from PIL import Image

logger = logging.getLogger("claynext.models.ocr")


def sec_to_timestamp(sec: float) -> str:
    """Format seconds into 00:00:00.000 timestamp."""
    sec = max(0.0, float(sec))
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = int(sec % 60)
    millis = int(round((sec - int(sec)) * 1000))
    if millis >= 1000:
        seconds += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def timestamp_to_sec(ts: str) -> float:
    """Parse 00:00:00.000 timestamp into float seconds."""
    raw = str(ts or "").strip().replace(",", ".")
    parts = raw.split(":")
    if len(parts) == 3:
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except Exception:
            return 0.0
    elif len(parts) == 2:
        try:
            return int(parts[0]) * 60 + float(parts[1])
        except Exception:
            return 0.0
    try:
        return float(raw)
    except Exception:
        return 0.0


def text_similarity(a: str, b: str) -> float:
    """Calculate character-level fuzzy similarity between two strings (0.0 to 1.0)."""
    s1 = "".join(a.split()).lower()
    s2 = "".join(b.split()).lower()
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    return difflib.SequenceMatcher(None, s1, s2).ratio()


class OCREngine:
    """
    Video Frame Subtitle & Optical Character Recognition Engine.
    Scans video frame-by-frame within a designated capture zone (ROI) to reconstruct subtitle lines.
    """

    ENGINES = [
        "Auto (AI Vision / Multi-backend)",
        "Gemini Flash Vision (Cloud AI)",
        "RapidOCR / EasyOCR (Local Neural)",
    ]

    _local_reader = None
    _reader_tested = False

    @classmethod
    def _get_local_reader(cls):
        """Try to load a local OCR model (rapidocr or easyocr)."""
        if cls._reader_tested:
            return cls._local_reader
        cls._reader_tested = True
        try:
            from rapidocr_onnxruntime import RapidOCR
            cls._local_reader = RapidOCR()
            logger.info("Loaded RapidOCR ONNX engine.")
            return cls._local_reader
        except Exception:
            pass
        try:
            import easyocr
            cls._local_reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            logger.info("Loaded EasyOCR engine.")
            return cls._local_reader
        except Exception:
            pass
        return None

    @classmethod
    def ocr_image(cls, img: Image.Image, lang: str = "Auto", min_conf: float = 0.5) -> str:
        """Run OCR on a PIL Image (cropped frame) using local OCR or Gemini Flash vision."""
        # 1. Try local OCR if available
        reader = cls._get_local_reader()
        if reader is not None:
            try:
                import numpy as np
                arr = np.array(img.convert("RGB"))
                # RapidOCR returns: results, elapse
                if hasattr(reader, "__call__"):
                    res, _ = reader(arr)
                    if res:
                        texts = [item[1] for item in res if item[2] >= min_conf]
                        return " ".join(texts).strip()
            except Exception as exc:
                logger.debug(f"Local OCR failed: {exc}")

        # 2. Try Gemini Flash Vision if API key is in pool
        try:
            from claynext.models.llm_keys import get_key_pool
            secrets = get_key_pool().secrets("gemini")
            if secrets:
                text = cls._gemini_ocr_frame(img, secrets[0], lang=lang)
                if text:
                    return text
        except Exception as exc:
            logger.debug(f"Gemini OCR fallback failed: {exc}")

        return ""

    @classmethod
    def _gemini_ocr_frame(cls, img: Image.Image, api_key: str, lang: str = "Auto") -> str:
        """Extract text from a cropped subtitle frame using Google Gemini Flash."""
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        prompt = (
            "Read the burned-in subtitle / caption text visible in this cropped video frame image. "
            "Output ONLY the exact words/characters found in the subtitle line. "
            "If no clear subtitle text is present, reply with nothing."
        )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            f"?key={urllib.parse.quote(api_key)}"
        )
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "image/jpeg", "data": b64}},
                ]
            }],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 100},
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
        return ""

    @classmethod
    def extract_frame_image(
        cls, video_path: str, sec: float = 0.0, roi: dict | None = None
    ) -> Image.Image | None:
        """
        Extract a single video frame at `sec` seconds, optionally cropped to `roi`.
        ROI format: {"x": float, "y": float, "w": float, "h": float} normalized 0.0 to 1.0.
        """
        if not video_path or not os.path.isfile(video_path):
            return None
        img = None

        # Method 1: Try PyAV
        try:
            import av
            container = av.open(video_path)
            stream = container.streams.video[0]
            tb = stream.time_base
            target_pts = int(sec / tb) if tb else int(sec * 1000)
            container.seek(target_pts, stream=stream, any_frame=False)
            for packet in container.demux(stream):
                for frame in packet.decode():
                    img = frame.to_image()
                    break
                if img is not None:
                    break
            container.close()
        except Exception:
            pass

        # Method 2: Fallback via FFmpeg command
        if img is None:
            try:
                from claynext.adapters.ffmpeg_service import ffmpeg_exe
                import subprocess
                cmd = [
                    ffmpeg_exe(),
                    "-hide_banner",
                    "-loglevel", "error",
                    "-nostdin",
                    "-ss", str(max(0.0, sec)),
                    "-i", video_path,
                    "-vframes", "1",
                    "-f", "image2pipe",
                    "-vcodec", "png",
                    "-",
                ]
                proc = subprocess.run(cmd, capture_output=True, timeout=8)
                if proc.stdout and len(proc.stdout) > 500:
                    img = Image.open(io.BytesIO(proc.stdout)).convert("RGB")
            except Exception:
                pass

        if img is None:
            return None

        # Crop to ROI if specified
        if roi:
            vw, vh = img.size
            rx = max(0.0, min(1.0, float(roi.get("x", 0.0))))
            ry = max(0.0, min(1.0, float(roi.get("y", 0.0))))
            rw = max(0.02, min(1.0 - rx, float(roi.get("w", 1.0))))
            rh = max(0.02, min(1.0 - ry, float(roi.get("h", 1.0))))
            box = (int(rx * vw), int(ry * vh), int((rx + rw) * vw), int((ry + rh) * vh))
            img = img.crop(box)

        return img

    @classmethod
    def extract_subtitles_from_video(
        cls,
        video_path: str,
        roi: dict,
        *,
        sample_interval: float = 0.4,
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        min_confidence: float = 0.5,
        lang: str = "Auto",
        similarity_thresh: float = 0.75,
        progress_callback: Callable | None = None,
        control: Any = None,
    ) -> list[dict[str, Any]]:
        """
        Scan video frame-by-frame inside the ROI capture zone to reconstruct subtitle script lines.
        Merges consecutive frames with matching text into coherent timed subtitle segments.
        """
        if not video_path or not os.path.isfile(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Probe duration
        from claynext.adapters.media import get_media_adapter
        probe = get_media_adapter().probe(video_path)
        video_dur = float(probe.get("duration") or 0.0)
        if end_sec <= 0.0 or end_sec > video_dur:
            end_sec = video_dur if video_dur > 0.0 else 60.0

        total_span = max(0.5, end_sec - start_sec)
        sample_interval = max(0.15, min(2.0, float(sample_interval)))

        # Frame timestamps
        timestamps: list[float] = []
        cur_t = start_sec
        while cur_t <= end_sec:
            timestamps.append(round(cur_t, 3))
            cur_t += sample_interval

        total_frames = len(timestamps)
        if total_frames == 0:
            return []

        def _ping(pct: int, msg: str):
            if control and hasattr(control, "checkpoint"):
                control.checkpoint()
            if progress_callback:
                try:
                    progress_callback(pct, msg)
                except Exception:
                    pass

        _ping(5, f"Starting frame OCR subtitle extraction ({total_frames} frames to scan)…")

        # Open video stream via PyAV if available
        import av
        container = None
        stream = None
        try:
            container = av.open(video_path)
            stream = container.streams.video[0]
        except Exception:
            container = None

        frame_results: list[tuple[float, str]] = []

        for idx, t in enumerate(timestamps):
            if control and hasattr(control, "checkpoint"):
                control.checkpoint()

            pct = int(5 + (idx / total_frames) * 85)
            if idx % 5 == 0 or idx == total_frames - 1:
                _ping(pct, f"Scanning frame at {sec_to_timestamp(t)} ({idx + 1}/{total_frames})…")

            # Extract cropped frame
            cropped_img = None
            if container is not None and stream is not None:
                try:
                    tb = stream.time_base
                    pts = int(t / tb) if tb else int(t * 1000)
                    container.seek(pts, stream=stream, any_frame=False)
                    for packet in container.demux(stream):
                        for f in packet.decode():
                            full_img = f.to_image()
                            vw, vh = full_img.size
                            rx, ry = float(roi.get("x", 0.05)), float(roi.get("y", 0.72))
                            rw, rh = float(roi.get("w", 0.90)), float(roi.get("h", 0.20))
                            box = (int(rx * vw), int(ry * vh), int((rx + rw) * vw), int((ry + rh) * vh))
                            cropped_img = full_img.crop(box)
                            break
                        if cropped_img is not None:
                            break
                except Exception:
                    cropped_img = None

            if cropped_img is None:
                cropped_img = cls.extract_frame_image(video_path, t, roi=roi)

            text = ""
            if cropped_img is not None:
                text = cls.ocr_image(cropped_img, lang=lang, min_conf=min_confidence)

            clean_text = " ".join(text.split()).strip()
            frame_results.append((t, clean_text))

        if container is not None:
            try:
                container.close()
            except Exception:
                pass

        _ping(92, "Deduplicating and timing extracted subtitle segments…")

        # Temporal Stitching & Deduplication
        segments: list[dict[str, Any]] = []
        cur_seg: dict[str, Any] | None = None

        for t, text in frame_results:
            if not text:
                # Text disappeared; finalize current segment if open
                if cur_seg is not None:
                    # Filter out tiny 1-frame glitches (< 0.3s)
                    if (cur_seg["end_sec"] - cur_seg["start_sec"]) >= 0.28:
                        segments.append(cur_seg)
                    cur_seg = None
                continue

            if cur_seg is None:
                # Start new subtitle segment
                cur_seg = {
                    "id": len(segments) + 1,
                    "start_sec": t,
                    "end_sec": round(t + sample_interval, 3),
                    "start": sec_to_timestamp(t),
                    "end": sec_to_timestamp(t + sample_interval),
                    "text": text,
                    "original_text": text,
                    "translated_text": "",
                    "speaker": "Speaker 1",
                }
            else:
                sim = text_similarity(cur_seg["text"], text)
                if sim >= similarity_thresh:
                    # Same subtitle persists on screen; extend end timestamp
                    cur_seg["end_sec"] = round(t + sample_interval, 3)
                    cur_seg["end"] = sec_to_timestamp(cur_seg["end_sec"])
                    # Keep the longest / most complete text string
                    if len(text) > len(cur_seg["text"]):
                        cur_seg["text"] = text
                        cur_seg["original_text"] = text
                else:
                    # Subtitle text changed; finalize previous and start new
                    if (cur_seg["end_sec"] - cur_seg["start_sec"]) >= 0.28:
                        segments.append(cur_seg)
                    cur_seg = {
                        "id": len(segments) + 1,
                        "start_sec": t,
                        "end_sec": round(t + sample_interval, 3),
                        "start": sec_to_timestamp(t),
                        "end": sec_to_timestamp(t + sample_interval),
                        "text": text,
                        "original_text": text,
                        "translated_text": "",
                        "speaker": "Speaker 1",
                    }

        if cur_seg is not None and (cur_seg["end_sec"] - cur_seg["start_sec"]) >= 0.28:
            segments.append(cur_seg)

        # Re-index segments
        for i, s in enumerate(segments):
            s["id"] = i + 1
            dur = max(0.15, s["end_sec"] - s["start_sec"])
            s["duration_sec"] = round(dur, 3)

        _ping(100, f"Frame OCR finished! Extracted {len(segments)} subtitle lines.")
        return segments
