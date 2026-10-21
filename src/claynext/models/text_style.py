"""Text overlay styling shared by the preview painter and the subtitle burn-in."""
from __future__ import annotations

import math
import re

REF_H = 360  # font sizes, strokes and shadows are pixels on a canvas this tall
DEFAULT_FONT = "Arial"
ASS_SIZE = 1.12  # libass sizes a font by ascent + descent, Qt by the em square
SLIDE = 0.12  # slide distance as a fraction of the canvas height
BOX_PAD = (0.28, 0.14)  # background padding (x, y) relative to the font size

FONT_RANGE = (6, 120)
SCALE_RANGE = (10, 400)
LETTER_RANGE = (-5, 30)
STROKE_RANGE = (1, 12)
SHADOW_RANGE = (1, 12)
IN_OUT_MS_RANGE = (100, 3000)
LOOP_MS_RANGE = (300, 4000)
CAPTION_WIDTH_RANGE = (40, 95)

CASES = (("none", "Aa", "As typed"), ("upper", "TT", "UPPERCASE"), ("lower", "tt", "lowercase"), ("title", "Tt", "Title Case"))
ALIGNS = ("left", "center", "right")
CAPTION_ANIMS = (
    ("none", "Static"),
    ("words", "Word by word"),
    ("highlight", "Highlight karaoke"),
    ("typewriter", "Typewriter"),
    ("fade", "Fade in"),
)

TEXT_DEFAULTS: dict = {
    "font": DEFAULT_FONT,
    "font_size": 20,
    "scale": 100,
    "color": "#ffffff",
    "opacity": 100,
    "bold": False,
    "italic": False,
    "underline": False,
    "case": "none",
    "align": "center",
    "letter": 0,
    "stroke_on": False,
    "stroke_color": "#000000",
    "stroke_width": 3,
    "bg_on": False,
    "bg_color": "#000000",
    "bg_opacity": 70,
    "shadow_on": False,
    "shadow_color": "#000000",
    "shadow_dist": 2,
    "anim_in": "none",
    "anim_in_ms": 500,
    "anim_out": "none",
    "anim_out_ms": 500,
    "anim_loop": "none",
    "anim_loop_ms": 1200,
    "highlight_color": "#facc15",
    "caption_fit": True,
    "caption_width": 80,
    "preset": "",
    "blur_on": False,
    "blur_radius": 20,
}

TEXT_COLORS = (
    "#ffffff", "#000000", "#9ca3af", "#ef4444", "#f97316", "#facc15",
    "#22c55e", "#06b6d4", "#3b82f6", "#8b5cf6", "#ec4899", "#7c2d12",
)

_PLAIN = {
    "stroke_on": False, "bg_on": False, "shadow_on": False,
    "stroke_color": "#000000", "stroke_width": 3, "bg_color": "#000000", "bg_opacity": 70,
    "shadow_color": "#000000", "shadow_dist": 2,
}


def _preset(color: str, stroke: str = "", width: int = 3, bg: str = "", bg_opacity: int = 100, shadow: str = "") -> dict:
    out = dict(_PLAIN, color=color)
    if stroke:
        out.update(stroke_on=True, stroke_color=stroke, stroke_width=width)
    if bg:
        out.update(bg_on=True, bg_color=bg, bg_opacity=bg_opacity)
    if shadow:
        out.update(shadow_on=True, shadow_color=shadow, shadow_dist=2)
    return out


STYLE_PRESETS: list[tuple[str, dict]] = [
    ("none", _preset("#ffffff")),
    ("outline_black", _preset("#ffffff", "#000000", 3)),
    ("outline_heavy", _preset("#ffffff", "#000000", 6)),
    ("shadow", _preset("#ffffff", shadow="#000000")),
    # Opaque plate so “Boxed” / live captions read clearly on any footage.
    ("box_dark", _preset("#ffffff", bg="#000000", bg_opacity=100)),
    ("yellow_outline", _preset("#facc15", "#000000", 3)),
    ("red_outline", _preset("#ef4444", "#ffffff", 3)),
    ("orange_outline", _preset("#f97316", "#ffffff", 3)),
    ("blue_outline", _preset("#3b82f6", "#ffffff", 3)),
    ("green_outline", _preset("#22c55e", "#000000", 3)),
    ("box_grey", _preset("#000000", bg="#9ca3af")),
    ("box_light", _preset("#000000", bg="#e5e7eb")),
    ("box_yellow", _preset("#000000", bg="#facc15")),
    ("box_purple", _preset("#ffffff", bg="#7c3aed")),
    ("purple_on_white", _preset("#7c3aed", bg="#ffffff")),
    ("box_white", _preset("#000000", bg="#ffffff")),
    ("white_on_black", _preset("#ffffff", bg="#000000")),
    ("green_on_black", _preset("#22c55e", bg="#000000")),
    ("dark_green_outline", _preset("#000000", "#22c55e", 3)),
    ("gold_outline", _preset("#f59e0b", "#3b1d00", 4)),
    ("pink_outline", _preset("#f472b6", "#ffffff", 3)),
    ("cream_shadow", _preset("#fef3c7", "#000000", 2, shadow="#f59e0b")),
    ("mint_shadow", _preset("#bbf7d0", "#14532d", 3, shadow="#22c55e")),
]
STYLE_PRESET_KEYS = {key for key, _ in STYLE_PRESETS}

ANIM_IN: list[tuple[str, str]] = [
    ("none", "None"), ("fade", "Fade in"), ("slide_up", "Slide up"), ("slide_down", "Slide down"),
    ("slide_left", "Slide left"), ("slide_right", "Slide right"), ("zoom_in", "Zoom in"),
    ("zoom_out", "Zoom out"), ("pop", "Pop"), ("spin", "Spin in"), ("typewriter", "Typewriter"),
    ("words", "Word by word"), ("highlight", "Highlight"),
]
ANIM_OUT: list[tuple[str, str]] = [
    ("none", "None"), ("fade", "Fade out"), ("slide_up", "Slide up"), ("slide_down", "Slide down"),
    ("slide_left", "Slide left"), ("slide_right", "Slide right"), ("zoom_in", "Zoom in"),
    ("zoom_out", "Zoom out"), ("pop", "Pop"), ("spin", "Spin out"), ("typewriter", "Erase"),
    ("words", "Word erase"),
]
ANIM_LOOP: list[tuple[str, str]] = [
    ("none", "None"), ("pulse", "Pulse"), ("blink", "Blink"), ("float", "Float"), ("wiggle", "Wiggle"),
    ("highlight", "Highlight pulse"),
]
# Watermark travel. Kept off the text inspector; the style window offers these.
WATERMARK_LOOPS: list[tuple[str, str]] = [
    ("slide_bottom", "Slide from bottom"),
    ("slide_top", "Slide from top"),
    ("slide_left", "Slide from left"),
    ("slide_right", "Slide from right"),
    ("curve", "Curve bound"),
]
_BOUND_LOOPS = {key for key, _ in WATERMARK_LOOPS}
_ANIM_KEYS = {
    "anim_in": {key for key, _ in ANIM_IN},
    "anim_out": {key for key, _ in ANIM_OUT},
    "anim_loop": {key for key, _ in ANIM_LOOP} | _BOUND_LOOPS,
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _hex(value, fallback: str) -> str:
    raw = str(value or "").strip().lower()
    if len(raw) == 7 and raw.startswith("#"):
        try:
            int(raw[1:], 16)
            return raw
        except ValueError:
            pass
    return fallback


def clean_text_style(data: dict | None) -> dict:
    """Every style field present, typed and in range."""
    src = dict(data or {})
    out = dict(TEXT_DEFAULTS)
    for key, default in TEXT_DEFAULTS.items():
        if key not in src or src[key] is None:
            continue
        value = src[key]
        try:
            if isinstance(default, bool):
                out[key] = bool(value)
            elif isinstance(default, int):
                out[key] = int(round(float(value)))
            else:
                out[key] = str(value)
        except (TypeError, ValueError):
            continue
    out["font_size"] = _clamp(out["font_size"], *FONT_RANGE)
    out["scale"] = _clamp(out["scale"], *SCALE_RANGE)
    out["opacity"] = _clamp(out["opacity"], 0, 100)
    out["letter"] = _clamp(out["letter"], *LETTER_RANGE)
    out["stroke_width"] = _clamp(out["stroke_width"], *STROKE_RANGE)
    out["shadow_dist"] = _clamp(out["shadow_dist"], *SHADOW_RANGE)
    out["bg_opacity"] = _clamp(out["bg_opacity"], 0, 100)
    out["anim_in_ms"] = _clamp(out["anim_in_ms"], *IN_OUT_MS_RANGE)
    out["anim_out_ms"] = _clamp(out["anim_out_ms"], *IN_OUT_MS_RANGE)
    out["anim_loop_ms"] = _clamp(out["anim_loop_ms"], *LOOP_MS_RANGE)
    out["caption_width"] = _clamp(out["caption_width"], *CAPTION_WIDTH_RANGE)
    out["caption_fit"] = bool(out.get("caption_fit", True))
    out["blur_on"] = bool(out.get("blur_on", False))
    out["blur_radius"] = _clamp(int(round(float(out.get("blur_radius", 20)))), 1, 100)
    for key in ("color", "stroke_color", "bg_color", "shadow_color", "highlight_color"):
        out[key] = _hex(out[key], TEXT_DEFAULTS[key])
    if out["case"] not in {key for key, _a, _b in CASES}:
        out["case"] = "none"
    if out["align"] not in ALIGNS:
        out["align"] = "center"
    for key, allowed in _ANIM_KEYS.items():
        if out[key] not in allowed:
            out[key] = "none"
    out["font"] = out["font"].strip() or DEFAULT_FONT
    return out


def word_spans(text: str) -> list[tuple[int, int]]:
    """Inclusive character ranges (into `text`) for each visible word token."""
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text or "")]


def word_count(text: str) -> int:
    return max(1, len(word_spans(text or "")))


def chars_for_words(text: str, words: float) -> int:
    """How many non-newline characters to show for the first `words` word tokens."""
    spans = word_spans(text or "")
    if not spans:
        return 0
    n = max(0, min(len(spans), int(math.ceil(max(0.0, float(words))))))
    if n <= 0:
        return 0
    end = spans[n - 1][1]
    return sum(1 for ch in (text or "")[:end] if ch != "\n")


def preset_values(key: str) -> dict:
    return dict(next((values for name, values in STYLE_PRESETS if name == key), _PLAIN))


def apply_case(text: str, case: str) -> str:
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "title":
        return text.title()
    return text


def anim_spans(style: dict, dur_ms: int) -> tuple[int, int]:
    """In / out lengths, shrunk together when the clip is shorter than both."""
    if style.get("anim_loop", "none") != "none":
        return 0, 0
    a = int(style.get("anim_in_ms") or 0) if style.get("anim_in", "none") != "none" else 0
    b = int(style.get("anim_out_ms") or 0) if style.get("anim_out", "none") != "none" else 0
    if dur_ms > 0 and a + b > dur_ms:
        k = dur_ms / float(a + b)
        a, b = int(a * k), int(b * k)
    return a, b


def is_animated(style: dict) -> bool:
    return any(style.get(key, "none") != "none" for key in ("anim_in", "anim_out", "anim_loop"))


def _identity() -> dict:
    return {
        "alpha": 1.0, "dx": 0.0, "dy": 0.0, "scale": 1.0, "rot": 0.0,
        "reveal": 1.0, "reveal_mode": "chars", "highlight": -1.0,
    }


def _away(kind: str, leaving: bool) -> dict:
    s = -1.0 if leaving else 1.0
    return {
        "slide_up": {"dy": SLIDE * s},
        "slide_down": {"dy": -SLIDE * s},
        "slide_left": {"dx": SLIDE * s},
        "slide_right": {"dx": -SLIDE * s},
        "zoom_in": {"scale": 1.6 if leaving else 0.4},
        "zoom_out": {"scale": 0.4 if leaving else 1.6},
        "spin": {"rot": 90.0 if leaving else -90.0},
    }.get(kind, {})


def _shape(frame: dict, kind: str, presence: float, leaving: bool):
    p = _clamp(presence, 0.0, 1.0)
    if kind == "typewriter":
        frame["reveal"] = p
        frame["reveal_mode"] = "chars"
        return
    if kind == "words":
        frame["reveal"] = p
        frame["reveal_mode"] = "words"
        return
    if kind == "highlight":
        frame["reveal"] = 1.0
        frame["highlight"] = p
        return
    if kind == "pop":
        frame["scale"] = 1.15 * p / 0.6 if p < 0.6 else 1.15 - 0.15 * (p - 0.6) / 0.4
        frame["alpha"] = min(1.0, p * 3.0)
        return
    frame["alpha"] = p
    for key, away in _away(kind, leaving).items():
        base = 1.0 if key == "scale" else 0.0
        frame[key] = away + (base - away) * p


def _bound_point(loop: str, u: float) -> tuple[float, float]:
    """A point on the frame edge, in canvas-height units from the centre."""
    aspect = 16 / 9
    inset_x, inset_y = 0.12, 0.14
    left, right = inset_x, 1.0 - inset_x
    top, bottom = inset_y, 1.0 - inset_y
    t = u % 1.0
    if loop == "slide_bottom":
        nx, ny = left + (right - left) * t, bottom
    elif loop == "slide_top":
        nx, ny = left + (right - left) * t, top
    elif loop == "slide_left":
        nx, ny = left, bottom + (top - bottom) * t
    elif loop == "slide_right":
        nx, ny = right, top + (bottom - top) * t
    else:
        nx, ny = _curve_norm(t, left, right, top, bottom)
    return (nx - 0.5) * aspect, ny - 0.5


def _curve_norm(u: float, left: float, right: float, top: float, bottom: float) -> tuple[float, float]:
    """Rounded rectangle around the frame, starting at the bottom and running clockwise on screen."""
    aspect = 16 / 9
    hw = (0.5 - left) * aspect
    hh = bottom - 0.5
    rad = min(0.10, hw * 0.45, hh * 0.45)
    horiz = max(0.04, 2 * (hw - rad))
    vert = max(0.04, 2 * (hh - rad))
    arc = math.pi * rad / 2
    lengths = (horiz, arc, vert, arc, horiz, arc, vert, arc)
    total = sum(lengths)
    dist = (u % 1.0) * total
    # Bottom straight, left to right, then the bottom-right curve, and so on.
    samples = (
        lambda f: (-hw + rad + horiz * f, hh),
        lambda f: _arc(hw - rad, hh - rad, rad, math.pi / 2, 0.0, f),
        lambda f: (hw, hh - rad - vert * f),
        lambda f: _arc(hw - rad, -hh + rad, rad, 0.0, -math.pi / 2, f),
        lambda f: (hw - rad - horiz * f, -hh),
        lambda f: _arc(-hw + rad, -hh + rad, rad, -math.pi / 2, -math.pi, f),
        lambda f: (-hw, -hh + rad + vert * f),
        lambda f: _arc(-hw + rad, hh - rad, rad, math.pi, math.pi / 2, f),
    )
    for index, (length, sample) in enumerate(zip(lengths, samples)):
        if dist <= length or index == len(samples) - 1:
            x, y = sample(0.0 if length <= 0 else _clamp(dist / length, 0.0, 1.0))
            return 0.5 + x / aspect, 0.5 + y
        dist -= length
    return 0.5, bottom


def _arc(cx: float, cy: float, rad: float, a0: float, a1: float, f: float) -> tuple[float, float]:
    ang = a0 + (a1 - a0) * f
    return cx + rad * math.cos(ang), cy + rad * math.sin(ang)


def anim_frame(style: dict, t_ms: float, dur_ms: float) -> dict:
    """Animated offsets at `t_ms` into a clip of `dur_ms`: alpha, dx/dy (canvas heights), scale, rot, reveal."""
    frame = _identity()
    if dur_ms <= 0 or not is_animated(style):
        return frame
    t = _clamp(float(t_ms), 0.0, float(dur_ms))
    loop = style.get("anim_loop", "none")
    if loop != "none":
        period = max(100, int(style.get("anim_loop_ms") or 1200))
        u = (t % period) / period
        if loop in _BOUND_LOOPS:
            home_x = float(style.get("x", 0.5) or 0.5)
            home_y = float(style.get("y", 0.5) or 0.5)
            px, py = _bound_point(loop, u)
            frame["dx"] = px - (home_x - 0.5) * (16 / 9)
            frame["dy"] = py - (home_y - 0.5)
            return frame
        wave = math.sin(2 * math.pi * u)
        if loop == "pulse":
            frame["scale"] = 1.0 + 0.08 * wave
        elif loop == "blink":
            frame["alpha"] = 0.3 + 0.7 * (0.5 + 0.5 * math.cos(2 * math.pi * u))
        elif loop == "float":
            frame["dy"] = -0.025 * wave
        elif loop == "wiggle":
            frame["rot"] = 6.0 * wave
        elif loop == "highlight":
            # Sweep highlight across the line for the whole clip (karaoke pulse).
            frame["highlight"] = t / max(1.0, float(dur_ms))
        return frame
    anim_in = style.get("anim_in", "none")
    # Word / highlight karaoke runs across the full line duration (not just the in-ramp).
    if anim_in in {"words", "highlight"} and float(dur_ms) > 0:
        p = t / float(dur_ms)
        if anim_in == "words":
            frame["reveal"] = _clamp(p, 0.0, 1.0)
            frame["reveal_mode"] = "words"
        else:
            frame["highlight"] = _clamp(p, 0.0, 1.0)
        return frame
    a, b = anim_spans(style, int(dur_ms))
    if a and t < a:
        p = t / a
        _shape(frame, anim_in, 1 - (1 - p) ** 3, leaving=False)
    elif b and t > dur_ms - b:
        p = (dur_ms - t) / b
        _shape(frame, style.get("anim_out", "none"), 1 - (1 - p) ** 3, leaving=True)
    return frame


def _ass_colour(hex_color: str) -> str:
    raw = _hex(hex_color, "#ffffff")[1:].upper()
    return f"&H{raw[4:6]}{raw[2:4]}{raw[0:2]}&"


def _ass_alpha(visible: float) -> str:
    return f"&H{int(round(255 * (1.0 - _clamp(visible, 0.0, 1.0)))):02X}&"


def _ass_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", r"\N")


def ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    cs = int(round(sec * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


ASS_STYLES = (
    "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1\n"
    "Style: Box,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,3,0,0,5,0,0,0,1\n"
)


def _pieces(style: dict, dur_ms: int, text_len: int, words: int = 1) -> list[tuple[int, int]]:
    """Time slices whose ends are joined linearly; enough of them to follow eased and looping motion."""
    if dur_ms <= 0:
        return []
    loop = style.get("anim_loop", "none")
    anim_in = style.get("anim_in", "none")
    if loop == "highlight" or anim_in in {"words", "highlight"}:
        count = max(1, min(80, words if anim_in in {"words", "highlight"} or loop == "highlight" else 8))
        step = max(40, dur_ms // count)
        cuts = list(range(0, dur_ms, step))[:4000]
        return [(c, min(dur_ms, c + step)) for c in cuts]
    if loop != "none":
        period = max(100, int(style.get("anim_loop_ms") or 1200))
        step = max(40, period // 8)
        cuts = list(range(0, dur_ms, step))[:4000]
        return [(c, min(dur_ms, c + step)) for c in cuts]
    a, b = anim_spans(style, dur_ms)
    edges = {0, dur_ms}
    for start, length, kind in ((0, a, style.get("anim_in")), (dur_ms - b, b, style.get("anim_out"))):
        if not length:
            continue
        count = max(1, min(60, text_len)) if kind == "typewriter" else max(2, min(8, length // 40))
        if kind == "words":
            count = max(1, min(60, words))
        edges.update(start + round(length * i / count) for i in range(count + 1))
    ordered = sorted(e for e in edges if 0 <= e <= dur_ms)
    return [(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)]


def _rounded_box(w: float, h: float, r: float) -> str:
    r = max(0.0, min(r, w / 2, h / 2))
    v = lambda n: f"{n:.0f}"  # noqa: E731
    return (
        f"m {v(r)} 0 l {v(w - r)} 0 b {v(w)} 0 {v(w)} 0 {v(w)} {v(r)} l {v(w)} {v(h - r)} "
        f"b {v(w)} {v(h)} {v(w)} {v(h)} {v(w - r)} {v(h)} l {v(r)} {v(h)} b 0 {v(h)} 0 {v(h)} 0 {v(h - r)} "
        f"l 0 {v(r)} b 0 0 0 0 {v(r)} 0"
    )


def ass_events(item: dict, text: str, start_s: float, end_s: float, width: int, height: int) -> list[str]:
    """Dialogue lines (background box + text) that burn one styled, animated text item into the video."""
    style = clean_text_style(item)
    style["x"] = float(item.get("x", 0.5) or 0.5)
    style["y"] = float(item.get("y", 0.5) or 0.5)
    text = apply_case(str(text or ""), style["case"])
    if not text.strip() or end_s <= start_s:
        return []
    k = height / float(REF_H)
    px = style["font_size"] * style["scale"] / 100.0 * k
    lines = text.split("\n")
    box_w = float(item.get("box_w") or 0) * height or max(len(line) for line in lines) * 0.55 * px
    box_h = float(item.get("box_h") or 0) * height or len(lines) * 1.2 * px
    cx = float(item.get("x", 0.5)) * width
    cy = float(item.get("y", 0.5)) * height
    an = {"left": 4, "right": 6}.get(style["align"], 5)
    side = {"left": -0.5, "right": 0.5}.get(style["align"], 0.0) * box_w
    base_rot = -float(item.get("rotation") or 0.0)
    opacity = style["opacity"] / 100.0
    metrics = item.get("metrics") or {}
    if metrics:
        rows = _line_rows(lines, metrics, px, an - 3, side)
        size = float(metrics["win_asc"]) + float(metrics["win_desc"])
    else:
        rows = [(text, an, side, 0.0)]
        size = ASS_SIZE

    measured = bool(item.get("box_w"))
    head_base = (
        rf"\q2\fn{style['font']}\fs{px * size:.1f}\b{int(style['bold'])}\i{int(style['italic'])}"
        rf"\u{int(style['underline'])}\fsp{style['letter'] * k:.1f}\1c{_ass_colour(style['color'])}"
    )
    head = head_base
    head += rf"\bord{style['stroke_width'] * k:.1f}\3c{_ass_colour(style['stroke_color'])}" if style["stroke_on"] else r"\bord0"
    head += rf"\shad{style['shadow_dist'] * k:.1f}\4c{_ass_colour(style['shadow_color'])}" if style["shadow_on"] else r"\shad0"
    pad_x, pad_y = BOX_PAD[0] * px, BOX_PAD[1] * px
    fitted_box = head_base + rf"\bord{pad_y * 1.6:.1f}\shad0\3c{_ass_colour(style['bg_color'])}"
    box_draw = _rounded_box(box_w + 2 * pad_x, box_h + 2 * pad_y, 0.22 * px)
    box_head = rf"\an5\bord0\shad0\1c{_ass_colour(style['bg_color'])}\p1"
    box_vis = opacity * style["bg_opacity"] / 100.0

    def text_alpha(mult: float) -> str:
        vis = _ass_alpha(opacity * mult)
        return rf"\1a{vis}\3a{vis}\4a{_ass_alpha(opacity * mult * 0.8)}"

    def motion(fa: dict, fb: dict, off_x: float, off_y: float, alpha_fn) -> str:
        flip = (-1.0 if item.get("flip_h") else 1.0, -1.0 if item.get("flip_v") else 1.0)
        return _motion(cx, cy, height, base_rot, fa, fb, off_x, off_y, alpha_fn, flip)

    dur_ms = int(round((end_s - start_s) * 1000))
    chars = len(text.replace("\n", ""))
    words = word_count(text)
    events: list[str] = []
    for a_ms, b_ms in _pieces(style, dur_ms, chars, words):
        fa = anim_frame(style, a_ms, dur_ms)
        fb = anim_frame(style, b_ms if b_ms < dur_ms else dur_ms - 1, dur_ms)
        t0, t1 = ass_time(start_s + a_ms / 1000.0), ass_time(start_s + b_ms / 1000.0)
        if t0 == t1:
            continue
        if style["bg_on"] and box_vis > 0 and measured:
            body = motion(fa, fb, 0.0, 0.0, lambda m: rf"\1a{_ass_alpha(box_vis * m)}")
            events.append(f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,{{{box_head}{body}}}{box_draw}{{\\p0}}")
        elif style["bg_on"] and box_vis > 0:
            body = motion(fa, fb, side, 0.0, lambda m: rf"\1a&HFF&\3a{_ass_alpha(box_vis * m)}\4a&HFF&")
            events.append(f"Dialogue: 0,{t0},{t1},Box,,0,0,0,,{{\\an{an}{fitted_box}{body}}}{_ass_escape(text)}")
        mode = str(fa.get("reveal_mode") or "chars")
        hl = float(fa.get("highlight", -1.0))
        if mode == "words":
            left = chars_for_words(text, fa["reveal"] * words)
        else:
            left = round(fa["reveal"] * chars)
        for row_text, row_an, off_x, off_y in rows:
            count = len(row_text.replace("\n", ""))
            shown, left = min(count, left), left - count
            if not row_text.strip():
                continue
            tags = rf"\an{row_an}" + head + motion(fa, fb, off_x, off_y, text_alpha)
            if hl >= 0.0:
                events.append(
                    f"Dialogue: 1,{t0},{t1},Default,,0,0,0,,{{{tags}}}{_karaoke_ass(row_text, hl, style)}"
                )
            elif shown <= 0:
                continue
            else:
                events.append(f"Dialogue: 1,{t0},{t1},Default,,0,0,0,,{{{tags}}}{_revealed(row_text, shown)}")
    return events


def _motion(cx: float, cy: float, height: int, base_rot: float, fa: dict, fb: dict,
            off_x: float, off_y: float, alpha_fn, flip: tuple[float, float] = (1.0, 1.0)) -> str:
    """Position (offset from the centre, which grows with the scale), origin, scale, angle, alpha."""
    xa, ya = cx + fa["dx"] * height + off_x * fa["scale"], cy + fa["dy"] * height + off_y * fa["scale"]
    xb, yb = cx + fb["dx"] * height + off_x * fb["scale"], cy + fb["dy"] * height + off_y * fb["scale"]
    out = rf"\move({xa:.0f},{ya:.0f},{xb:.0f},{yb:.0f})" if (abs(xa - xb) > 0.5 or abs(ya - yb) > 0.5) else rf"\pos({xa:.0f},{ya:.0f})"
    out += rf"\org({cx + fa['dx'] * height:.0f},{cy + fa['dy'] * height:.0f})"
    fx, fy = flip
    out += rf"\fscx{fa['scale'] * 100 * fx:.1f}\fscy{fa['scale'] * 100 * fy:.1f}\frz{base_rot - fa['rot']:.1f}" + alpha_fn(fa["alpha"])
    change = ""
    if abs(fa["scale"] - fb["scale"]) > 1e-3:
        change += rf"\fscx{fb['scale'] * 100 * fx:.1f}\fscy{fb['scale'] * 100 * fy:.1f}"
    if abs(fa["rot"] - fb["rot"]) > 1e-3:
        change += rf"\frz{base_rot - fb['rot']:.1f}"
    if abs(fa["alpha"] - fb["alpha"]) > 1e-3:
        change += alpha_fn(fb["alpha"])
    return out + (rf"\t({change})" if change else "")


def shape_events(item: dict, start_s: float, end_s: float, width: int, height: int) -> list[str]:
    """Dialogue lines that burn one vector shape. `item["drawing"]` holds ["m"|"l"|"b", x, y, ...]
    commands in canvas heights centred on (0, 0); `w` / `h` are its size before the style scale."""
    drawing = item.get("drawing") or []
    if not drawing or end_s <= start_s:
        return []
    style = clean_text_style(item)
    k = height / float(REF_H)
    unit = style["scale"] / 100.0 * height
    half_w = float(item.get("w") or 0.3) * unit / 2
    half_h = float(item.get("h") or 0.3) * unit / 2
    sx = -1.0 if item.get("flip_h") else 1.0
    sy = -1.0 if item.get("flip_v") else 1.0
    parts = []
    for cmd in drawing:
        pts = cmd[1:]
        coords = " ".join(
            f"{(pts[i] * sx * unit + half_w) * 4:.0f} {(pts[i + 1] * sy * unit + half_h) * 4:.0f}" for i in range(0, len(pts) - 1, 2)
        )
        parts.append(f"{cmd[0]} {coords}")
    shape = " ".join(parts)
    cx = float(item.get("x", 0.5)) * width
    cy = float(item.get("y", 0.5)) * height
    base_rot = -float(item.get("rotation") or 0.0)
    opacity = style["opacity"] / 100.0
    head = rf"\an5\1c{_ass_colour(style['color'])}"
    head += rf"\bord{style['stroke_width'] * k:.1f}\3c{_ass_colour(style['stroke_color'])}" if style["stroke_on"] else r"\bord0"
    head += rf"\shad{style['shadow_dist'] * k:.1f}\4c{_ass_colour(style['shadow_color'])}" if style["shadow_on"] else r"\shad0"

    def alpha(mult: float) -> str:
        vis = _ass_alpha(opacity * mult)
        return rf"\1a{vis}\3a{vis}\4a{_ass_alpha(opacity * mult * 0.8)}"

    dur_ms = int(round((end_s - start_s) * 1000))
    events: list[str] = []
    for a_ms, b_ms in _pieces(style, dur_ms, 1):
        fa = anim_frame(style, a_ms, dur_ms)
        fb = anim_frame(style, b_ms if b_ms < dur_ms else dur_ms - 1, dur_ms)
        t0, t1 = ass_time(start_s + a_ms / 1000.0), ass_time(start_s + b_ms / 1000.0)
        if t0 == t1 or fa["reveal"] <= 0:
            continue
        tags = head + _motion(cx, cy, height, base_rot, fa, fb, 0.0, 0.0, alpha, (sx, sy)) + r"\p3"
        events.append(f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,{{{tags}}}{shape}{{\\p0}}")
    return events


def _line_rows(lines: list[str], metrics: dict, px: float, an: int, off_x: float) -> list[tuple]:
    """One bottom-anchored row per line, at the baseline the preview painter uses.
    libass would otherwise stack lines by the font's win ascent + descent, which crowds scripts like Khmer."""
    asc, desc, step = float(metrics["asc"]), float(metrics["desc"]), float(metrics["line"])
    half = ((len(lines) - 1) * step + asc + desc) / 2
    win_desc = float(metrics["win_desc"])
    return [(line, an, off_x, (i * step + asc - half + win_desc) * px) for i, line in enumerate(lines)]


def _revealed(text: str, shown: int) -> str:
    """`text` with everything after the first `shown` characters (newlines not counted) made invisible."""
    if shown >= len(text.replace("\n", "")):
        return _ass_escape(text)
    cut, seen = 0, 0
    while cut < len(text) and seen < shown:
        seen += text[cut] != "\n"
        cut += 1
    return _ass_escape(text[:cut]) + r"{\alpha&HFF&}" + _ass_escape(text[cut:])


def _karaoke_ass(text: str, progress: float, style: dict) -> str:
    """ASS body with sung words tinted `highlight_color` and the rest at base colour."""
    spans = word_spans(text)
    if not spans:
        return _ass_escape(text)
    n = len(spans)
    active = max(0, min(n, int(math.ceil(max(0.0, float(progress)) * n))))
    hi = _ass_colour(style.get("highlight_color") or "#facc15")
    base = _ass_colour(style.get("color") or "#ffffff")
    cut = spans[active - 1][1] if active else 0
    return rf"{{\1c{hi}}}{_ass_escape(text[:cut])}{{\1c{base}}}{_ass_escape(text[cut:])}"

