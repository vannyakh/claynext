"""Project canvas: output ratio, video transform, and background fill (preview geometry)."""
from __future__ import annotations

import re

# key, label, width / height (None = follow the source)
CANVAS_RATIOS: tuple[tuple[str, str, float | None], ...] = (
    ("original", "Original", None),
    ("16:9", "16:9", 16 / 9),
    ("9:16", "9:16", 9 / 16),
    ("1:1", "1:1", 1.0),
    ("4:3", "4:3", 4 / 3),
    ("4:5", "4:5", 4 / 5),
    ("21:9", "21:9", 21 / 9),
)
CANVAS_BACKGROUNDS: tuple[tuple[str, str], ...] = (("none", "None"), ("blur", "Blur"), ("color", "Color"))
BLUR_LEVELS = (1, 2, 3, 4)
CANVAS_COLORS = ("#000000", "#ffffff", "#1e293b", "#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981")
SCALE_RANGE = (10, 400)
POSITION_RANGE = (-100, 100)

DEFAULT_CANVAS: dict = {"ratio": "original", "scale": 100, "x": 0, "y": 0, "bg": "none", "blur": 2, "color": "#000000"}

PREVIEW_BLUR_DIV = {1: 10, 2: 18, 3: 30, 4: 48}
EXPORT_BLUR_RADIUS = {1: 5, 2: 10, 3: 18, 4: 28}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clamp(value, low: int, high: int, fallback: int) -> int:
    try:
        return max(low, min(high, int(round(float(value)))))
    except (TypeError, ValueError):
        return fallback


def clean_canvas(canvas: dict | None) -> dict:
    src = canvas if isinstance(canvas, dict) else {}
    ratios = {key for key, _label, _value in CANVAS_RATIOS}
    color = str(src.get("color") or DEFAULT_CANVAS["color"])
    return {
        "ratio": src.get("ratio") if src.get("ratio") in ratios else "original",
        "scale": _clamp(src.get("scale", 100), *SCALE_RANGE, 100),
        "x": _clamp(src.get("x", 0), *POSITION_RANGE, 0),
        "y": _clamp(src.get("y", 0), *POSITION_RANGE, 0),
        "bg": src.get("bg") if src.get("bg") in {key for key, _ in CANVAS_BACKGROUNDS} else "none",
        "blur": _clamp(src.get("blur", 2), BLUR_LEVELS[0], BLUR_LEVELS[-1], 2),
        "color": color.lower() if _HEX.match(color) else DEFAULT_CANVAS["color"],
    }


def is_neutral(canvas: dict | None) -> bool:
    """True when the output frame is exactly the source frame."""
    c = clean_canvas(canvas)
    return c["ratio"] == "original" and c["scale"] == 100 and c["x"] == 0 and c["y"] == 0


def ratio_value(key: str, source_ratio: float | None = None) -> float | None:
    for k, _label, value in CANVAS_RATIOS:
        if k == key:
            return source_ratio if value is None else value
    return source_ratio


def video_box(*args) -> tuple[float, float, float, float]:
    """Video rect (x, y, w, h) supporting both 4-argument and 7-argument signatures."""
    if len(args) == 4:
        canvas_w, canvas_h, source_ratio, canvas = args
        c = clean_canvas(canvas)
        if canvas_w <= 0 or canvas_h <= 0:
            return 0.0, 0.0, 0.0, 0.0
        ratio = source_ratio if source_ratio and source_ratio > 0 else canvas_w / canvas_h
        if canvas_w / canvas_h > ratio:
            h = canvas_h
            w = h * ratio
        else:
            w = canvas_w
            h = w / ratio
        s = c["scale"] / 100.0
        w, h = w * s, h * s
        cx = canvas_w / 2 + c["x"] / 100.0 * canvas_w
        cy = canvas_h / 2 + c["y"] / 100.0 * canvas_h
        return cx - w / 2, cy - h / 2, w, h
    elif len(args) == 7:
        out_w, out_h, src_w, src_h, scale_pct, offset_x_pct, offset_y_pct = args
        if out_w <= 0 or out_h <= 0 or src_w <= 0 or src_h <= 0:
            return (0.0, 0.0, 0.0, 0.0)
        fit_scale = min(out_w / src_w, out_h / src_h)
        zoom = max(0.1, scale_pct / 100.0)
        w = src_w * fit_scale * zoom
        h = src_h * fit_scale * zoom
        cx = out_w / 2.0 + (offset_x_pct / 100.0) * (out_w / 2.0)
        cy = out_h / 2.0 + (offset_y_pct / 100.0) * (out_h / 2.0)
        return (cx - w / 2.0, cy - h / 2.0, w, h)
    return 0.0, 0.0, 0.0, 0.0


def covers_canvas(canvas_w: float, canvas_h: float, source_ratio: float | None, canvas: dict | None) -> bool:
    x, y, w, h = video_box(canvas_w, canvas_h, source_ratio, canvas)
    return x <= 0.5 and y <= 0.5 and x + w >= canvas_w - 0.5 and y + h >= canvas_h - 0.5


def _even(value: float) -> int:
    return max(2, int(round(value / 2.0)) * 2)


def canvas_size(src_w: int, src_h: int, ratio_key: str) -> tuple[int, int]:
    """Output frame size: keeps the source's short side, reshaped to the ratio."""
    if src_w <= 0 or src_h <= 0:
        return 0, 0
    ratio = ratio_value(ratio_key, src_w / src_h)
    if ratio_key == "original" or not ratio:
        return _even(src_w), _even(src_h)
    short = min(src_w, src_h)
    if ratio >= 1:
        return _even(short * ratio), _even(short)
    return _even(short), _even(short / ratio)


def canvas_filter(canvas: dict | None, src_w: int, src_h: int, grade: str = "", fg: str = "") -> str:
    """Filter graph for the preview canvas. `grade` hits the whole frame; `fg` hits only the video."""
    c = clean_canvas(canvas)
    if is_neutral(c) or src_w <= 0 or src_h <= 0:
        return ",".join(part for part in (grade, fg) if part)
    cw, ch = canvas_size(src_w, src_h, c["ratio"])
    bx, by, bw, bh = video_box(cw, ch, src_w / src_h, c)
    fw, fh = _even(bw), _even(bh)
    ox, oy = int(round(bx + (bw - fw) / 2)), int(round(by + (bh - fh) / 2))
    if c["bg"] == "blur":
        sw, sh = _even(cw / 4), _even(ch / 4)
        radius = max(1, min(EXPORT_BLUR_RADIUS[c["blur"]], min(sw, sh) // 2 - 1))
        chroma = max(1, min(radius, min(sw, sh) // 4 - 1))
        background = (
            f"[a]scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},format=yuv420p,"
            f"boxblur=luma_radius={radius}:luma_power=2:chroma_radius={chroma}:chroma_power=2,"
            f"scale={cw}:{ch},setsar=1[bg]"
        )
    else:
        color = c["color"] if c["bg"] == "color" else "#000000"
        background = f"[a]scale={cw}:{ch},setsar=1,drawbox=x=0:y=0:w=iw:h=ih:color=0x{color[1:]}@1:t=fill[bg]"
    head = f"{grade}," if grade else ""
    front = f",{fg}" if fg else ""
    return (
        f"{head}split[a][b];{background};[b]scale={fw}:{fh},setsar=1{front}[fg];"
        f"[bg][fg]overlay=x={ox}:y={oy}:shortest=1,format=yuv420p"
    )

