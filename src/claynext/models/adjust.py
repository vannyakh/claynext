"""Color grading, brightness, contrast, and saturation presentation models."""
from __future__ import annotations

from typing import Any

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
    # Shelf FILTER_LOOKS aliases
    "bleach": ("Bleach Bypass", {"contrast": 40, "saturation": -55, "brightness": 6, "sharpen": 25}),
    "teal_orange": ("Teal & Orange", {"temperature": -20, "tint": -10, "contrast": 22, "saturation": 18, "vignette": 25}),
    "clean": ("Clean", {}),
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


def grade_rgb(r: Any, g: Any = None, b: Any = None, adjust: dict | None = None) -> Any:
    """
    Grade either a single RGB triple or an HxWx3 uint8 array.
    Call forms: ``grade_rgb(r, g, b, adjust)`` or ``grade_rgb(rgb_array, adjust)``.
    """
    if hasattr(r, "ndim") and getattr(r, "ndim", 0) == 3:
        if isinstance(g, dict):
            return _grade_array(r, g)
        if isinstance(adjust, dict):
            return _grade_array(r, adjust)
        return r
    adj = adjust if isinstance(adjust, dict) else (b if isinstance(b, dict) else {})
    br = adj.get("brightness", 0) * 1.2
    ct = 1.0 + (adj.get("contrast", 0) / 100.0)

    def _c(val: int) -> int:
        return max(0, min(255, int(round((val - 128) * ct + 128 + br))))

    return (_c(int(r)), _c(int(g)), _c(int(b)))


def _grade_array(rgb: Any, adjust: dict | None) -> Any:
    """Apply colour adjust dict to an HxWx3 uint8 numpy array."""
    import numpy as np

    adj = clean_adjust(adjust)
    if not adj or rgb is None:
        return rgb
    out = rgb.astype(np.float32)

    br = adj.get("brightness", 0) * 1.2
    ct = 1.0 + (adj.get("contrast", 0) / 100.0)
    out = (out - 128.0) * ct + 128.0 + br

    temp = adj.get("temperature", 0) / 100.0
    tint = adj.get("tint", 0) / 100.0
    if temp:
        out[:, :, 0] += 28.0 * temp
        out[:, :, 2] -= 28.0 * temp
    if tint:
        out[:, :, 1] += 22.0 * tint

    sat = 1.0 + (adj.get("saturation", 0) / 100.0)
    if abs(sat - 1.0) > 1e-3:
        gray = out[:, :, 0] * 0.299 + out[:, :, 1] * 0.587 + out[:, :, 2] * 0.114
        out = gray[:, :, None] + (out - gray[:, :, None]) * sat

    hue = adj.get("hue", 0)
    if hue:
        # Approximate hue rotate around luma axis (degrees).
        ang = np.deg2rad(float(hue))
        cos_a, sin_a = float(np.cos(ang)), float(np.sin(ang))
        r, g, b = out[:, :, 0], out[:, :, 1], out[:, :, 2]
        out[:, :, 0] = r * (0.299 + 0.701 * cos_a + 0.168 * sin_a) + g * (0.587 - 0.587 * cos_a + 0.330 * sin_a) + b * (0.114 - 0.114 * cos_a - 0.497 * sin_a)
        out[:, :, 1] = r * (0.299 - 0.299 * cos_a - 0.328 * sin_a) + g * (0.587 + 0.413 * cos_a + 0.035 * sin_a) + b * (0.114 - 0.114 * cos_a + 0.292 * sin_a)
        out[:, :, 2] = r * (0.299 - 0.300 * cos_a + 1.250 * sin_a) + g * (0.587 - 0.588 * cos_a - 1.050 * sin_a) + b * (0.114 + 0.886 * cos_a - 0.203 * sin_a)

    vig = adj.get("vignette", 0)
    if vig:
        h, w = out.shape[:2]
        y, x = np.ogrid[:h, :w]
        cx, cy = w / 2.0, h / 2.0
        max_dist = max(1.0, float(np.sqrt(cx**2 + cy**2)))
        dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / max_dist
        strength = max(0.0, min(1.0, vig / 100.0))
        mask = np.clip(1.0 - (dist**1.4) * strength, 0.15, 1.0)[:, :, np.newaxis]
        out = out * mask

    return np.clip(out, 0, 255).astype(np.uint8)


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
    if key not in FILTER_PRESETS or key in ("none", "clean") or rgb is None:
        return rgb
    _label, adj = FILTER_PRESETS[key]
    return grade_rgb(rgb, adj)
