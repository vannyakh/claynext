"""Color grading, brightness, contrast, and saturation presentation models."""
from __future__ import annotations

from pathlib import Path
from claynext.utils.paths import BASE_DIR

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


def clean_adjust(data: dict | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, _label, low, high in ADJUST_FIELDS:
        try:
            value = int((data or {}).get(key, 0))
        except (TypeError, ValueError):
            value = 0
        if value:
            out[key] = max(low, min(high, value))
    return out


def scaled_adjust(adjust: dict | None, intensity: int) -> dict[str, int]:
    k = max(0, min(100, int(intensity))) / 100.0
    return clean_adjust({key: round(value * k) for key, value in clean_adjust(adjust).items()})


def grade_rgb(r: int, g: int, b: int, adjust: dict) -> tuple[int, int, int]:
    br = adjust.get("brightness", 0) * 1.2
    ct = 1.0 + (adjust.get("contrast", 0) / 100.0)

    def _c(val: int) -> int:
        return max(0, min(255, int(round((val - 128) * ct + 128 + br))))

    return (_c(r), _c(g), _c(b))


def adjust_filter(adjust: dict | None) -> str | None:
    if not adjust:
        return None
    c = clean_adjust(adjust)
    if all(v == 0 for v in c.values()):
        return None
    br = c.get("brightness", 0) / 100.0
    ct = 1.0 + (c.get("contrast", 0) / 100.0)
    sat = 1.0 + (c.get("saturation", 0) / 100.0)
    return f"eq=brightness={br:.2f}:contrast={ct:.2f}:saturation={sat:.2f}"


def filter_sample_rgb(w: int = 160, h: int = 90):
    try:
        import numpy as np
        img_path = BASE_DIR / "assets" / "images" / "fx_preview_base.jpg"
        if img_path.is_file():
            from PIL import Image
            im = Image.open(img_path).convert("RGB")
            scale = max(w / im.width, h / im.height)
            nw, nh = int(round(im.width * scale)), int(round(im.height * scale))
            im = im.resize((nw, nh), Image.Resampling.LANCZOS)
            left = max(0, (nw - w) // 2)
            top = max(0, (nh - h) // 2)
            im = im.crop((left, top, left + w, top + h))
            return np.array(im, dtype=np.uint8)
        return np.zeros((h, w, 3), dtype=np.uint8)
    except Exception:
        return None


def grade_filter_preview(rgb, key: str):
    if key not in FILTER_PRESETS or key == "none" or rgb is None:
        return rgb
    return rgb

