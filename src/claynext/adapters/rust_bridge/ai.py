"""Bridge to backends/ai-runtime (claynext-ai)."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from claynext.adapters.rust_bridge.process import _find_binary, _run_rust, _run_rust_stream

logger = logging.getLogger("claynext.adapters.rust")


class RustAiAdapter:
    """Interfaces with `backends/ai-runtime` (claynext-ai) and `crates/editor-ai`."""

    @classmethod
    def _ai(cls, *args: str, check: bool = True) -> subprocess.CompletedProcess[str] | None:
        binary = _find_binary("claynext-ai")
        if not binary:
            return None
        return _run_rust(binary, list(args), check=check)

    @classmethod
    def get_device_config(cls) -> dict[str, Any]:
        try:
            res = cls._ai("device")
            if res:
                return json.loads(res.stdout)
        except Exception as e:
            logger.warning(f"Rust AI device config failed: {e}")
        return {"provider": "DirectML", "device_id": 0, "num_threads": 4, "enable_fp16": True}

    @classmethod
    def vad_chunk(
        cls,
        media_path: str | Path | None = None,
        *,
        sample_rate: int = 16000,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Energy VAD spans from media via Rust ``energy-vad``.

        Decodes mono PCM with bundled FFmpeg, then runs claynext-ai. When
        ``media_path`` is omitted, returns the synthetic ``vad-sim`` demo spans.
        """
        if media_path:
            tmp_path: str | None = None
            try:
                import tempfile

                from claynext.adapters.rust_bridge.ffmpeg import RustFfmpegAdapter

                # Prefer claynext-ffmpeg decode; fall back to bundled FFmpeg.
                chunk = RustFfmpegAdapter.decode_audio_pcm_f32(
                    media_path, sample_rate=sample_rate, channels=1
                )
                raw = chunk.raw_pcm if chunk else b""
                if not raw:
                    from claynext.adapters.ffmpeg_service import run_ffmpeg

                    with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as tmp:
                        tmp_path = tmp.name
                    proc = run_ffmpeg(
                        [
                            "-y",
                            "-i",
                            str(media_path),
                            "-vn",
                            "-ac",
                            "1",
                            "-ar",
                            str(int(sample_rate)),
                            "-f",
                            "f32le",
                            "-acodec",
                            "pcm_f32le",
                            tmp_path,
                        ],
                        timeout=300,
                    )
                    if proc.returncode == 0 and tmp_path and Path(tmp_path).is_file():
                        raw = Path(tmp_path).read_bytes()
                if raw:
                    if not tmp_path:
                        with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as tmp:
                            tmp.write(raw)
                            tmp_path = tmp.name
                    res = cls._ai(
                        "energy-vad",
                        tmp_path,
                        str(int(sample_rate)),
                        str(float(threshold)),
                    )
                    if res and res.stdout.strip():
                        data = json.loads(res.stdout.strip())
                        if isinstance(data, list):
                            return data
            except Exception as e:
                logger.debug(f"Rust energy-vad failed: {e}")
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
            return []
        try:
            res = cls._ai("vad-sim")
            if res:
                return json.loads(res.stdout)
        except Exception as e:
            logger.warning(f"Rust AI vad-sim failed: {e}")
        return []

    @classmethod
    def fit_speech(
        cls, lines: list[dict[str, Any]], turns: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Snap line times onto soundtrack turns via Rust ``fit-speech``."""
        if not lines or not turns:
            return list(lines or [])
        payload = {
            "lines": [
                {
                    "start_sec": float(item.get("start_sec") or 0),
                    "end_sec": float(item.get("end_sec") or 0),
                    "text": str(item.get("text") or ""),
                }
                for item in lines
            ],
            "turns": [
                {
                    "start_sec": float(item.get("start_sec") or 0),
                    "end_sec": float(item.get("end_sec") or 0),
                    "confidence": float(item.get("confidence") or 0.85),
                }
                for item in turns
            ],
        }
        tmp_path: str | None = None
        try:
            import tempfile

            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(payload, tmp, ensure_ascii=False)
                tmp_path = tmp.name
            res = cls._ai("fit-speech", tmp_path, check=False)
            if res and res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.strip())
                if isinstance(data, list):
                    return data
        except Exception as exc:
            logger.debug(f"Rust fit-speech failed: {exc}")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        return None

    @classmethod
    def _json_file_call(cls, command: str, payload: Any, *head: str) -> Any:
        """Run ``claynext-ai <command> *head <json file>``; None when Rust cannot answer."""
        if not _find_binary("claynext-ai"):
            return None
        tmp_path: str | None = None
        try:
            import tempfile

            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(payload, tmp, ensure_ascii=False)
                tmp_path = tmp.name
            res = cls._ai(command, *head, tmp_path, check=False)
            if res and res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout.strip())
            if res is not None and res.returncode != 0:
                logger.debug("Rust %s: %s", command, (res.stderr or "").strip())
        except Exception as exc:
            logger.debug(f"Rust {command} failed: {exc}")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        return None

    @classmethod
    def analyze_prosody_pcm(
        cls, pcm_path: str | Path, sample_rate: int, spans: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Per-span energy / pitch / voicing via ``analyze-prosody`` on mono f32 PCM."""
        payload = [
            {
                "index": int(item.get("index") or 0),
                "start_sec": float(item.get("start_sec") or 0),
                "end_sec": float(item.get("end_sec") or 0),
            }
            for item in spans
        ]
        data = cls._json_file_call("analyze-prosody", payload, str(pcm_path), str(int(sample_rate)))
        return data if isinstance(data, list) else None

    @classmethod
    def plan_performance(cls, request: dict[str, Any]) -> dict[str, Any] | None:
        """Dialogue performance plan via ``plan-performance``."""
        data = cls._json_file_call("plan-performance", request)
        if isinstance(data, dict) and isinstance(data.get("lines"), list):
            return data
        return None

    @classmethod
    def parse_retry_after(cls, status: int, header: str | None = None, body: str = "") -> tuple[bool, float]:
        try:
            res = cls._ai("llm-parse-retry", str(status), header or "", body or "")
            if res:
                data = json.loads(res.stdout.strip())
                return bool(data.get("is_rate_limit", False)), float(data.get("retry_after_secs", 20.0))
        except Exception as e:
            logger.debug(f"Rust parse-retry failed, falling back: {e}")
        # Python fallback
        limited = status == 429 or "rate limit" in body.lower() or "resource_exhausted" in body.lower()
        return limited, 20.0

    @classmethod
    def acquire_llm_key(cls, keys: list[dict[str, Any]], provider: str) -> dict[str, Any] | None:
        try:
            res = cls._ai("llm-acquire", json.dumps(keys), provider)
            if res:
                raw = res.stdout.strip()
                if raw and raw != "null":
                    return json.loads(raw)
        except Exception as e:
            logger.debug(f"Rust acquire-key failed, falling back: {e}")
        return None

    @classmethod
    def soonest_cooldown(cls, keys: list[dict[str, Any]], provider: str) -> float:
        try:
            res = cls._ai("llm-soonest-cooldown", json.dumps(keys), provider)
            if res:
                data = json.loads(res.stdout.strip())
                return float(data.get("soonest_cooldown_secs", 0.0))
        except Exception as e:
            logger.debug(f"Rust soonest-cooldown failed, falling back: {e}")
        return 0.0

    @classmethod
    def parse_expression_tags(cls, text: str) -> list[dict[str, Any]]:
        try:
            res = cls._ai("parse-expression-tags", text)
            if res:
                return json.loads(res.stdout.strip())
        except Exception as e:
            logger.debug(f"Rust parse-expression-tags failed: {e}")
        return []

    @classmethod
    def chunk_subtitles(cls, text: str, max_chars: int = 1500) -> list[dict[str, Any]]:
        try:
            res = cls._ai("chunk-subtitles", text, str(max_chars))
            if res:
                return json.loads(res.stdout.strip())
        except Exception as e:
            logger.debug(f"Rust chunk-subtitles failed: {e}")
        return []

    @classmethod
    def scan_burned_captions(
        cls,
        video_path: str,
        roi: dict[str, Any],
        *,
        sample_interval: float = 0.4,
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        min_confidence: float = 0.5,
        lang: str = "Auto",
        progress_callback=None,
    ) -> list[dict[str, Any]] | None:
        """Burned-in caption lines via ``claynext-ai scan-captions``. None if Rust cannot run."""
        binary = _find_binary("claynext-ai")
        if not binary:
            return None
        from claynext.adapters.vision_reader import ensure_reader

        reader = ensure_reader()
        if not reader:
            return None
        request = {
            "video": str(video_path),
            "roi": {
                "x": float(roi.get("x", 0.0)),
                "y": float(roi.get("y", 0.72)),
                "w": float(roi.get("w", 0.9)),
                "h": float(roi.get("h", 0.2)),
            },
            "sample_interval": float(sample_interval),
            "start_sec": float(start_sec),
            "end_sec": float(end_sec),
            "lang": lang or "Auto",
            "min_confidence": float(min_confidence),
            "reader": reader,
        }
        found: list[dict[str, Any]] | None = None

        def _on_line(line: str) -> None:
            nonlocal found
            raw = (line or "").strip()
            if not raw.startswith("{"):
                return
            try:
                payload = json.loads(raw)
            except Exception:
                return
            kind = payload.get("kind")
            if kind == "progress" and progress_callback:
                progress_callback(int(payload.get("pct") or 0), str(payload.get("message") or ""))
            elif kind == "result":
                found = list(payload.get("segments") or [])

        try:
            res = _run_rust_stream(binary, ["scan-captions", json.dumps(request)], _on_line)
        except Exception as exc:
            logger.warning("Rust scan-captions failed: %s", exc)
            return None
        if res.returncode != 0:
            logger.warning("Rust scan-captions: %s", (res.stderr or "").strip())
            return None
        return found if found is not None else []

    @classmethod
    def filter_ocr(cls, boxes: list[dict[str, Any]], min_confidence: float = 0.5) -> list[dict[str, Any]]:
        try:
            res = cls._ai("filter-ocr", json.dumps(boxes), str(min_confidence))
            if res:
                return json.loads(res.stdout.strip())
        except Exception as e:
            logger.debug(f"Rust filter-ocr failed: {e}")
        return [b for b in boxes if float(b.get("confidence", 0.0)) >= min_confidence]

    @classmethod
    def is_available(cls) -> bool:
        return _find_binary("claynext-ai") is not None

    @classmethod
    def estimate_speech_quota(
        cls, duration_sec: float, target_lang: str = ""
    ) -> dict[str, int] | None:
        """Speech unit budget (min/target/max) via claynext-ai. None if Rust unavailable."""
        try:
            res = cls._ai("speech-quota", str(float(duration_sec or 0.0)), target_lang or "")
            if not res:
                return None
            data = json.loads(res.stdout.strip())
            return {
                "min": int(data["min"]),
                "target": int(data["target"]),
                "max": int(data["max"]),
            }
        except Exception as e:
            logger.debug(f"Rust speech-quota failed: {e}")
            return None

    @classmethod
    def build_dub_prompt(
        cls,
        payload: list[dict[str, Any]] | dict[str, Any],
        target_lang: str,
        source_lang: str = "auto",
        *,
        fit_duration: bool = True,
        use_slang: bool = True,
        use_expression: bool = True,
        style: dict[str, Any] | None = None,
    ) -> str | None:
        """Build cinematic dubbing LLM prompt in Rust. None if binary unavailable."""
        style = style or {}
        req = {
            "payload": payload,
            "target_lang": target_lang,
            "source_lang": source_lang or "auto",
            "style": {
                "fit_duration": bool(style.get("fit_duration", fit_duration)),
                "use_slang": bool(style.get("use_slang", use_slang)),
                "use_expression": bool(style.get("use_expression", use_expression)),
            },
        }
        try:
            res = cls._ai("build-dub-prompt", json.dumps(req, ensure_ascii=False))
            if not res:
                return None
            prompt = (res.stdout or "").strip()
            return prompt or None
        except Exception as e:
            logger.debug(f"Rust build-dub-prompt failed: {e}")
            return None

    @classmethod
    def spoken_units(cls, text: str, target_lang: str = "") -> int | None:
        """Spoken beats for one line. None if the binary has no spoken-units command."""
        try:
            res = cls._ai(
                "spoken-units",
                json.dumps({"lang": target_lang or "", "text": text or ""}, ensure_ascii=False),
                check=False,
            )
            if not res or res.returncode != 0:
                return None
            raw = (res.stdout or "").strip()
            if not raw:
                return None
            return int(raw)
        except Exception as e:
            logger.debug(f"Rust spoken-units failed: {e}")
            return None

    @classmethod
    def spoken_units_many(cls, texts: list[str], target_lang: str = "") -> list[int] | None:
        try:
            res = cls._ai(
                "spoken-units",
                json.dumps({"lang": target_lang or "", "texts": texts}, ensure_ascii=False),
                check=False,
            )
            if not res or res.returncode != 0:
                return None
            data = json.loads((res.stdout or "").strip() or "[]")
            if not isinstance(data, list):
                return None
            return [int(n) for n in data]
        except Exception as e:
            logger.debug(f"Rust spoken-units failed: {e}")
            return None

    @classmethod
    def build_fit_prompt(cls, lines: list[dict[str, Any]], target_lang: str) -> str | None:
        """Rewrite prompt for lines that run past the speech slot."""
        try:
            res = cls._ai(
                "build-fit-prompt",
                json.dumps(
                    {"target_lang": target_lang or "", "lines": lines},
                    ensure_ascii=False,
                ),
                check=False,
            )
            if not res or res.returncode != 0:
                return None
            prompt = (res.stdout or "").strip()
            return prompt or None
        except Exception as e:
            logger.debug(f"Rust build-fit-prompt failed: {e}")
            return None

    @classmethod
    def build_translate_prompt(
        cls, source_lang: str, target_lang: str, text: str
    ) -> str | None:
        try:
            res = cls._ai(
                "build-translate-prompt",
                source_lang or "auto",
                target_lang or "en",
                text or "",
            )
            if not res:
                return None
            return (res.stdout or "").strip() or None
        except Exception as e:
            logger.debug(f"Rust build-translate-prompt failed: {e}")
            return None

    @classmethod
    def ducked_volume(cls, base_volume: float = 1.0, attenuation_db: float = -12.0) -> float | None:
        """Linear background volume after dB attenuation (Rust). None if unavailable."""
        try:
            res = cls._ai("ducked-volume", str(float(base_volume)), str(float(attenuation_db)))
            if not res:
                return None
            data = json.loads(res.stdout.strip())
            return float(data["volume"])
        except Exception as e:
            logger.debug(f"Rust ducked-volume failed: {e}")
            return None

    @classmethod
    def align_speech_speed(
        cls,
        audio_dur: float,
        slot_dur: float,
        *,
        min_speed: float = 0.65,
        max_speed: float = 1.85,
    ) -> float | None:
        """Tempo factor to fit audio into slot (Rust SegmentAligner equivalent)."""
        try:
            res = cls._ai(
                "align-speed",
                str(float(audio_dur)),
                str(float(slot_dur)),
                str(float(min_speed)),
                str(float(max_speed)),
            )
            if not res:
                return None
            data = json.loads(res.stdout.strip())
            return float(data["speech_speed"])
        except Exception as e:
            logger.debug(f"Rust align-speed failed: {e}")
            return None



