"""Colour adjustments for footage: FFmpeg filter graph and graded preview frames."""
from __future__ import annotations

import hashlib
import json
import math
import os
from functools import lru_cache

from jela.core.ffmpeg_tools import run_ffmpeg
from jela.utils.paths import BASE_DIR, CACHE_DIR

ADJUST_DIR = CACHE_DIR / "adjust_preview"

# key, label, low, high
ADJUST_FIELDS: tuple[tuple[str, str, int, int], ...] = (
    ("brightness", "Brightness", -100, 100),
    ("contrast", "Contrast", -100, 100),
    ("saturation", "Saturation", -100, 100),
    ("temperature", "Temperature", -100, 100),
    ("tint", "Tint", -100, 100),
    ("hue", "Hue", -180, 180),
    ("sharpen", "Sharpen", 0, 100),
    ("vignette", "Vignette", 0, 100),
)

FILTER_PRESETS: dict[str, tuple[str, dict[str, int]]] = {
    "none": ("None", {}),
    "vivid": ("Vivid", {"contrast": 15, "saturation": 35, "sharpen": 20}),
    "warm": ("Warm", {"temperature": 40, "saturation": 10}),
    "cool": ("Cool", {"temperature": -40, "tint": -5}),
    "cinematic": ("Cinematic", {"contrast": 20, "saturation": -15, "temperature": 10, "vignette": 40}),
    "fade": ("Faded", {"brightness": 8, "contrast": -25, "saturation": -20}),
    "mono": ("Mono", {"saturation": -100}),
    "noir": ("Noir", {"saturation": -100, "contrast": 35, "vignette": 50}),
    "golden": ("Golden", {"temperature": 50, "saturation": 25, "contrast": 10, "vignette": 20}),
    "teal": ("Teal", {"temperature": -30, "tint": -15, "contrast": 15, "saturation": 10}),
    "pink": ("Cool Pink", {"tint": 35, "temperature": 15, "brightness": 6, "saturation": 10}),
    "moody": ("Moody", {"brightness": -10, "contrast": 25, "saturation": -30, "temperature": -15, "vignette": 30}),
    "pastel": ("Pastel", {"brightness": 12, "contrast": -22, "saturation": -12, "tint": 10}),
    "sunset": ("Sunset", {"temperature": 65, "saturation": 20, "contrast": 12, "hue": -8}),
    "film": ("Film", {"contrast": 12, "saturation": -10, "temperature": 18, "sharpen": 15, "vignette": 25}),
}


def scaled_adjust(adjust: dict | None, intensity: int) -> dict[str, int]:
    """Adjustments faded toward neutral by `intensity` (0..100)."""
    k = max(0, min(100, int(intensity))) / 100.0
    return clean_adjust({key: round(value * k) for key, value in clean_adjust(adjust).items()})


def clean_adjust(adjust: dict | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, _label, low, high in ADJUST_FIELDS:
        try:
            value = int((adjust or {}).get(key, 0))
        except (TypeError, ValueError):
            value = 0
        if value:
            out[key] = max(low, min(high, value))
    return out


def adjust_filter(adjust: dict | None) -> str:
    """FFmpeg -vf chain for the adjustments, or "" when neutral."""
    return ",".join(adjust_parts(adjust))


def adjust_parts(adjust: dict | None) -> list[str]:
    """The adjustment filters one by one (each supports FFmpeg timeline `enable`)."""
    a = clean_adjust(adjust)
    if not a:
        return []
    parts: list[str] = []
    bright, contrast, sat = a.get("brightness", 0), a.get("contrast", 0), a.get("saturation", 0)
    if bright or contrast or sat:
        parts.append(
            f"eq=brightness={bright / 100 * 0.3:.3f}"
            f":contrast={max(0.1, 1 + contrast / 100):.3f}"
            f":saturation={max(0.0, 1 + sat / 100):.3f}"
        )
    if a.get("temperature"):
        parts.append(f"colortemperature=temperature={int(6500 - a['temperature'] * 30)}")
    if a.get("tint"):
        shift = -a["tint"] / 100 * 0.3
        parts.append(f"colorbalance=gm={shift:.3f}:rm={-shift / 2:.3f}:bm={-shift / 2:.3f}")
    if a.get("hue"):
        parts.append(f"hue=h={a['hue']}")
    if a.get("sharpen"):
        parts.append(f"unsharp=5:5:{a['sharpen'] / 100 * 1.5:.2f}")
    if a.get("vignette"):
        parts.append(f"vignette=angle={a['vignette'] / 100 * 1.2:.3f}")
    return parts


def grade_rgb(rgb, adjust: dict | None):
    """Approximate adjust_filter() on an HxWx3 uint8 RGB array, for live preview frames."""
    import numpy as np

    a = clean_adjust(adjust)
    if not a:
        return rgb
    stages = _colour_affine(tuple(sorted(a.items())))
    planes = [rgb[..., i].astype(np.float32) for i in range(3)]
    for matrix, offset in stages[:-1]:
        planes = [_mix(planes, matrix[c], offset[c]) for c in range(3)]
        for v in planes:
            np.clip(v, 0, 255, out=v)
    matrix, offset = stages[-1]
    mask = _vignette_mask(rgb.shape[0], rgb.shape[1], a["vignette"]) if a.get("vignette") else None
    amount = a.get("sharpen", 0) / 100 * 1.5
    out = np.empty_like(rgb)
    for c in range(3):
        v = _mix(planes, matrix[c], offset[c])
        if amount:
            blur = v.copy()
            blur[1:-1, 1:-1] = (v[:-2, 1:-1] + v[2:, 1:-1] + v[1:-1, :-2] + v[1:-1, 2:]) * 0.25
            v += (v - blur) * amount
        if mask is not None:
            v *= mask
        np.clip(v, 0, 255, out=v)
        v += 0.5
        out[..., c] = v
    return out


def _mix(planes, row, offset):
    v = planes[0] * row[0]
    v += planes[1] * row[1]
    v += planes[2] * row[2]
    v += offset
    return v


# Per-channel RGB gains of FFmpeg colortemperature at the slider values used by adjust_filter().
_TEMP_STEPS = (-100, -75, -50, -25, 0, 25, 50, 75, 100)
_TEMP_GAINS = (
    (0.801, 0.858, 1.0), (0.826, 0.878, 1.0), (0.862, 0.900, 1.0), (0.917, 0.930, 1.0), (1.0, 1.0, 1.0),
    (1.0, 0.941, 0.900), (1.0, 0.888, 0.803), (1.0, 0.826, 0.689), (1.0, 0.750, 0.548),
)


@lru_cache(maxsize=32)
def _colour_affine(items: tuple):
    """Per-pixel steps as (3x3 matrix, offset) stages on 0..255 RGB, clipped between stages like FFmpeg.

    Stage one is eq; temperature, tint, and hue fold into a second stage when present.
    """
    import numpy as np

    a = dict(items)
    luma = np.array([[0.299, 0.587, 0.114]], dtype=np.float32)
    ones = np.ones((3, 1), dtype=np.float32)
    contrast = max(0.1, 1 + a.get("contrast", 0) / 100)
    sat = max(0.0, 1 + a.get("saturation", 0) / 100)
    # eq: contrast/brightness act on luma only, saturation on chroma
    eq_m = sat * np.eye(3, dtype=np.float32) + (contrast - sat) * (ones @ luma)
    eq_b = np.full(3, (0.5 - 0.5 * contrast + a.get("brightness", 0) / 100 * 0.3) * 255, dtype=np.float32)
    m = np.eye(3, dtype=np.float32)
    b = np.zeros(3, dtype=np.float32)

    def then(step_m, step_b):
        nonlocal m, b
        m = step_m @ m
        b = step_m @ b + step_b

    if a.get("temperature"):
        gains = [np.interp(a["temperature"], _TEMP_STEPS, column) for column in zip(*_TEMP_GAINS)]
        then(np.diag(gains).astype(np.float32), np.zeros(3, np.float32))
    if a.get("tint"):
        shift = -a["tint"] / 100 * 0.3 * 255
        then(np.eye(3, dtype=np.float32), np.array([-shift / 4, shift / 2, -shift / 4], dtype=np.float32))
    if a.get("hue"):
        # FFmpeg hue rotates the chroma (U, V) plane of BT.601 YUV
        c, s = math.cos(math.radians(a["hue"])), math.sin(math.radians(a["hue"]))
        to_yuv = np.array([[0.299, 0.587, 0.114], [-0.169, -0.331, 0.5], [0.5, -0.419, -0.081]], dtype=np.float32)
        rotate = np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float32)
        then(np.linalg.inv(to_yuv) @ rotate @ to_yuv, np.zeros(3, np.float32))
    eq = (eq_m.astype(np.float32), eq_b.astype(np.float32))
    if not any(a.get(key) for key in ("temperature", "tint", "hue")):
        return (eq,)
    return eq, (m.astype(np.float32), b.astype(np.float32))


@lru_cache(maxsize=8)
def _vignette_mask(h: int, w: int, amount: int):
    """FFmpeg vignette falloff: cos(angle * d)^4 with d the distance to centre over the half-diagonal."""
    import numpy as np

    angle = amount / 100 * 1.2
    yy = (np.arange(h, dtype=np.float32) - (h - 1) / 2)[:, None]
    xx = (np.arange(w, dtype=np.float32) - (w - 1) / 2)[None, :]
    d = np.sqrt(xx * xx + yy * yy) / max(1.0, math.hypot(w / 2, h / 2))
    return np.cos(angle * np.minimum(d, 1.0)) ** 4


@lru_cache(maxsize=4)
def filter_sample_rgb(h: int = 48, w: int = 72):
    """Realistic cinematic preview plate (with procedural fallback) so filter presets read without open footage."""
    import numpy as np

    img_path = BASE_DIR / "assets" / "images" / "fx_preview_base.jpg"
    if img_path.is_file():
        try:
            from PIL import Image

            im = Image.open(img_path).convert("RGB")
            scale = max(w / im.width, h / im.height)
            nw, nh = int(round(im.width * scale)), int(round(im.height * scale))
            im = im.resize((nw, nh), Image.Resampling.LANCZOS)
            left = max(0, (nw - w) // 2)
            top = max(0, (nh - h) // 2)
            im = im.crop((left, top, left + w, top + h))
            return np.array(im, dtype=np.uint8)
        except Exception:
            pass

    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    yy, xx = np.broadcast_arrays(yy, xx)
    sky = np.stack([
        0.35 + 0.25 * xx,
        0.55 + 0.15 * (1.0 - yy),
        0.85 - 0.25 * yy,
    ], axis=-1)
    ground = np.stack([
        0.25 + 0.45 * xx,
        0.45 - 0.15 * xx,
        0.20 + 0.10 * yy,
    ], axis=-1)
    mix = np.clip((yy - 0.42) * 8.0, 0.0, 1.0)[..., None]
    rgb = sky * (1.0 - mix) + ground * mix
    cy, cx = 0.55 * h, 0.52 * w
    rr = ((np.arange(h)[:, None] - cy) ** 2 + (np.arange(w)[None, :] - cx) ** 2) / max(1.0, (0.18 * min(h, w)) ** 2)
    subject = np.exp(-rr)[..., None]
    tone = np.array([0.95, 0.72, 0.45], dtype=np.float32)
    rgb = rgb * (1.0 - 0.55 * subject) + tone * (0.55 * subject)
    return np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)


def grade_filter_preview(rgb, key: str):
    """Apply a named filter preset to an HxWx3 uint8 RGB array."""
    if key not in FILTER_PRESETS or key == "none":
        return rgb
    return grade_rgb(rgb, FILTER_PRESETS[key][1])


def render_adjust_frame(
    media_path: str,
    ms: int,
    adjust: dict | None,
    *,
    width: int = 640,
    progress_callback=None,
) -> dict:
    """Grab the frame at `ms` as an original and a graded JPEG."""
    ADJUST_DIR.mkdir(parents=True, exist_ok=True)
    sec = max(0.0, ms / 1000.0)
    stamp = f"{media_path}|{os.path.getmtime(media_path) if os.path.isfile(media_path) else 0}|{int(ms)}|{width}"
    base = hashlib.sha1(stamp.encode()).hexdigest()[:16]
    vf = adjust_filter(adjust)
    graded_key = hashlib.sha1(f"{base}|{json.dumps(clean_adjust(adjust), sort_keys=True)}".encode()).hexdigest()[:16]
    original = str(ADJUST_DIR / f"{base}_src.jpg")
    graded = str(ADJUST_DIR / f"{graded_key}_fx.jpg")
    if not os.path.isfile(original):
        _grab(media_path, sec, f"scale={width}:-2", original)
    if not vf:
        graded = original
    elif not os.path.isfile(graded):
        _grab(original, 0.0, vf, graded, seek=False)
    return {"original": original, "graded": graded, "ms": int(ms)}


def _grab(src: str, sec: float, vf: str, dst: str, *, seek: bool = True):
    args = ["-y"]
    if seek:
        args += ["-ss", f"{sec:.3f}"]
    args += ["-i", src, "-frames:v", "1", "-vf", vf, "-q:v", "3", dst]
    proc = run_ffmpeg(args, timeout=60)
    if proc.returncode != 0 or not os.path.isfile(dst):
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip().splitlines()
        raise RuntimeError(err[-1] if err else "Could not grab a preview frame")
