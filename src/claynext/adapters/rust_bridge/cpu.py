"""Bridge to backends/cpu (claynext-cpu)."""
from __future__ import annotations

import json
import logging
import os

from claynext.adapters.rust_bridge.process import _find_binary, _run_rust

logger = logging.getLogger("claynext.adapters.rust")


class RustCpuAdapter:
    """Interfaces with `backends/cpu` (claynext-cpu)."""

    @classmethod
    def is_available(cls) -> bool:
        return _find_binary("claynext-cpu") is not None

    @classmethod
    def run_benchmark(cls) -> str:
        binary = _find_binary("claynext-cpu")
        if not binary:
            return "Rust claynext-cpu binary not available"
        try:
            res = _run_rust(binary, ["benchmark"], timeout=120)
            if res.returncode != 0:
                return f"CPU benchmark failed: {res.stderr.strip()}"
            return res.stdout.strip()
        except Exception as e:
            return f"CPU benchmark failed: {e}"

    @classmethod
    def downsample_waveform(
        cls,
        raw_pcm_f32: bytes,
        target_bins: int = 2000,
    ) -> list[dict[str, float]]:
        """
        Peak/RMS bins for timeline waveform painting.
        Uses claynext-cpu when present; otherwise a fast Python downsample.
        """
        bins = max(1, int(target_bins))
        if not raw_pcm_f32:
            return [{"min": 0.0, "max": 0.0, "rms": 0.0} for _ in range(bins)]

        binary = _find_binary("claynext-cpu")
        if binary:
            try:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as tmp:
                    tmp.write(raw_pcm_f32)
                    tmp_path = tmp.name
                try:
                    res = _run_rust(
                        binary,
                        ["waveform", tmp_path, str(bins)],
                        timeout=60,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        data = json.loads(res.stdout)
                        if isinstance(data, list) and data:
                            return data
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
            except Exception as e:
                logger.debug("Rust waveform downsample failed, using Python: %s", e)

        import array
        import math

        samples = array.array("f")
        samples.frombytes(raw_pcm_f32)
        n = len(samples)
        if n == 0:
            return [{"min": 0.0, "max": 0.0, "rms": 0.0} for _ in range(bins)]
        out: list[dict[str, float]] = []
        for i in range(bins):
            a = (i * n) // bins
            b = max(a + 1, ((i + 1) * n) // bins)
            chunk = samples[a:b]
            lo = min(chunk)
            hi = max(chunk)
            acc = sum(s * s for s in chunk)
            rms = math.sqrt(acc / len(chunk)) if chunk else 0.0
            out.append({"min": float(lo), "max": float(hi), "rms": float(rms)})
        return out


