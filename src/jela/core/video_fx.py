"""Timed video effects and filter looks: FFmpeg timeline filters and matching live preview frames."""
from __future__ import annotations

import math

from jela.core.video_adjust import FILTER_PRESETS, adjust_parts, grade_rgb, scaled_adjust

# key, label, hint
EFFECTS: tuple[tuple[str, str, str], ...] = (
    ("blur", "Blur", "Soft, out-of-focus picture"),
    ("shake", "Shake", "Handheld camera shake"),
    ("zoom", "Zoom in", "Slow push in over the clip"),
    ("flash", "Flash", "White flash that fades into the shot"),
    ("fade_in", "Fade in", "Rises out of black"),
    ("fade_out", "Fade out", "Sinks into black"),
    ("glitch", "RGB split", "Red and blue pulled apart"),
    ("bw", "Black & white", "Drains the colour"),
    ("sepia", "Sepia", "Old photo tone"),
    ("invert", "Invert", "Negative colours"),
    ("mirror", "Mirror", "Flips the picture left to right"),
    ("pixelate", "Pixelate", "Big blocky pixels"),
    ("grain", "Film grain", "Moving film noise"),
    ("vignette", "Vignette", "Dark edges"),
    ("bars", "Cinema bars", "Black letterbox bars"),
)
EFFECT_LABELS = {key: label for key, label, _hint in EFFECTS}
FILTER_LOOKS = tuple((key, label) for key, (label, _values) in FILTER_PRESETS.items() if key != "none")
DEFAULT_INTENSITY = {"effect": 60, "filter": 100}
TIMED_EFFECTS = frozenset({"shake", "zoom", "flash", "fade_in", "fade_out", "grain"})

_SEPIA = ((0.393, 0.769, 0.189), (0.349, 0.686, 0.168), (0.272, 0.534, 0.131))
_SHAKE_ZOOM = 1.06


def clean_fx(kind: str, data: dict | None) -> dict:
    """{"effect" | "filter" | "transition": key, "intensity": 0..100}."""
    if kind == "transition":
        from jela.core.video_transitions import clean_transition
        return clean_transition(data)
    src = dict(data or {})
    try:
        intensity = max(0, min(100, int(src.get("intensity", DEFAULT_INTENSITY.get(kind, 60)))))
    except (TypeError, ValueError):
        intensity = DEFAULT_INTENSITY.get(kind, 60)
    if kind == "filter":
        key = src.get("filter") if src.get("filter") in FILTER_PRESETS and src.get("filter") != "none" else FILTER_LOOKS[0][0]
        return {"filter": key, "intensity": intensity}
    key = src.get("effect") if src.get("effect") in EFFECT_LABELS else EFFECTS[0][0]
    return {"effect": key, "intensity": intensity}


def fx_label(kind: str, data: dict | None) -> str:
    if kind == "transition":
        from jela.core.video_transitions import transition_label
        return transition_label(data)
    fx = clean_fx(kind, data)
    if kind == "filter":
        return FILTER_PRESETS[fx["filter"]][0]
    return EFFECT_LABELS[fx["effect"]]


def _shake(t: float, amp: float) -> tuple[float, float]:
    return amp * math.sin(t * 37.0) * math.cos(t * 11.0), amp * math.cos(t * 29.0) * math.sin(t * 7.0 + 1.0)


def _zoom(span: dict, t: float) -> float:
    a, b = span["start_ms"] / 1000.0, span["end_ms"] / 1000.0
    p = max(0.0, min(1.0, (t - a) / max(1e-3, b - a)))
    return 1.0 + 0.3 * span["intensity"] / 100.0 * p


def _fade_len(key: str, k: float, dur: float) -> float:
    if key == "flash":
        return max(0.12, min(dur, 0.2 + 0.8 * k))
    return max(0.12, min(dur, 0.3 + 1.7 * k))


def fx_filters(spans: list[dict], width: int, height: int) -> list[str]:
    """FFmpeg filters for timed looks and effects, each switched on only inside its clip.

    `spans` rows: {"kind": "filter" | "effect" | "transition", …, "intensity", "start_ms", "end_ms"}.
    """
    from jela.core.video_transitions import transition_filters

    out: list[str] = []
    out += transition_filters(
        [row for row in (spans or []) if str(row.get("kind") or "") == "transition"],
        width, height,
    )
    h = max(2, int(height))
    w = max(2, int(width))
    for row in spans or []:
        kind = str(row.get("kind") or "effect")
        if kind == "transition":
            continue
        fx = clean_fx(kind, row)
        a, b = float(row.get("start_ms") or 0) / 1000.0, float(row.get("end_ms") or 0) / 1000.0
        if b <= a:
            continue
        en = f"enable='between(t,{a:.3f},{b:.3f})'"
        k = fx["intensity"] / 100.0
        if kind == "filter":
            out += [f"{part}:{en}" for part in adjust_parts(scaled_adjust(FILTER_PRESETS[fx["filter"]][1], fx["intensity"]))]
            continue
        key = fx["effect"]
        if k <= 0 and key not in {"mirror", "invert"}:
            continue
        if key == "blur":
            out.append(f"gblur=sigma={max(0.5, k * 0.02 * h):.2f}:{en}")
        elif key in {"shake", "zoom"}:
            if key == "shake":
                amp = 0.03 * k
                dx = f"{amp:.4f}*W*sin(T*37)*cos(T*11)"
                dy = f"{amp:.4f}*H*cos(T*29)*sin(T*7+1)"
                z = f"{_SHAKE_ZOOM}"
            else:
                dx = dy = "0"
                z = f"(1+{0.3 * k:.4f}*clip((T-{a:.3f})/{max(1e-3, b - a):.3f},0,1))"
            sample = f"(W/2+(X-W/2)/{z}+{dx}),(H/2+(Y-H/2)/{z}+{dy})"
            out.append(f"geq=lum='lum({sample})':cb='cb({sample})':cr='cr({sample})':{en}")
        elif key == "flash":
            out.append(f"fade=t=in:st={a:.3f}:d={_fade_len(key, k, b - a):.3f}:color=white:{en}")
        elif key == "fade_in":
            out.append(f"fade=t=in:st={a:.3f}:d={_fade_len(key, k, b - a):.3f}:{en}")
        elif key == "fade_out":
            d = _fade_len(key, k, b - a)
            out.append(f"fade=t=out:st={b - d:.3f}:d={d:.3f}:{en}")
        elif key == "glitch":
            s = max(1, round(k * 0.012 * w))
            out.append(f"rgbashift=rh={-s}:bh={s}:{en}")
        elif key == "bw":
            out.append(f"hue=s={1 - k:.3f}:{en}")
        elif key == "sepia":
            m = [[(1 - k) * (r == c) + k * _SEPIA[r][c] for c in range(3)] for r in range(3)]
            names = ("rr", "rg", "rb", "gr", "gg", "gb", "br", "bg", "bb")
            values = [m[r][c] for r in range(3) for c in range(3)]
            out.append("colorchannelmixer=" + ":".join(f"{n}={v:.3f}" for n, v in zip(names, values)) + f":{en}")
        elif key == "invert":
            out.append(f"negate={en}")
        elif key == "mirror":
            out.append(f"hflip={en}")
        elif key == "pixelate":
            block = max(2, round(k * 0.03 * h) * 2)
            out.append(f"pixelize=w={block}:h={block}:{en}")
        elif key == "grain":
            out.append(f"noise=alls={max(1, round(k * 40))}:allf=t+u:{en}")
        elif key == "vignette":
            out.append(f"vignette=angle={0.3 + k * 1.0:.3f}:{en}")
        elif key == "bars":
            bar = max(2, round(k * 0.14 * h))
            out.append(f"drawbox=x=0:y=0:w=iw:h={bar}:color=black:t=fill:{en}")
            out.append(f"drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black:t=fill:{en}")
    return out


def _box_blur(v, radius: int):
    import numpy as np

    if radius < 1:
        return v
    for axis in (0, 1):
        pad = [(0, 0)] * v.ndim
        pad[axis] = (radius + 1, radius)
        c = np.cumsum(np.pad(v, pad, mode="edge"), axis=axis, dtype=np.float32)
        n = v.shape[axis]
        hi = np.take(c, np.arange(2 * radius + 1, 2 * radius + 1 + n), axis=axis)
        lo = np.take(c, np.arange(0, n), axis=axis)
        v = (hi - lo) / (2 * radius + 1)
    return v


def _remap(rgb, z: float, dx: float, dy: float):
    import numpy as np

    h, w = rgb.shape[:2]
    xs = np.clip(np.round(w / 2 + (np.arange(w) - w / 2) / z + dx), 0, w - 1).astype(np.intp)
    ys = np.clip(np.round(h / 2 + (np.arange(h) - h / 2) / z + dy), 0, h - 1).astype(np.intp)
    return rgb[ys[:, None], xs[None, :]]


def apply_fx(rgb, spans: list[dict], now_ms: int):
    """Approximate fx_filters() on an HxWx3 uint8 RGB frame shown at timeline time `now_ms`."""
    import numpy as np

    from jela.core.video_transitions import apply_transition

    rgb = apply_transition(rgb, spans, now_ms)
    t = now_ms / 1000.0
    for row in spans or []:
        if not (row.get("start_ms", 0) <= now_ms < row.get("end_ms", 0)):
            continue
        kind = str(row.get("kind") or "effect")
        if kind == "transition":
            continue
        fx = clean_fx(kind, row)
        k = fx["intensity"] / 100.0
        if kind == "filter":
            rgb = grade_rgb(rgb, scaled_adjust(FILTER_PRESETS[fx["filter"]][1], fx["intensity"]))
            continue
        key = fx["effect"]
        h, w = rgb.shape[:2]
        a, b = row["start_ms"] / 1000.0, row["end_ms"] / 1000.0
        if key == "blur":
            sigma = max(0.5, k * 0.02 * h)
            radius = max(1, int(round(math.sqrt(12 * sigma * sigma / 3 + 1) / 2)))
            v = rgb.astype(np.float32)
            for _ in range(3):
                v = _box_blur(v, radius)
            rgb = np.clip(v + 0.5, 0, 255).astype(np.uint8)
        elif key == "shake":
            dx, dy = _shake(t, 0.03 * k)
            rgb = _remap(rgb, _SHAKE_ZOOM, dx * w, dy * h)
        elif key == "zoom":
            rgb = _remap(rgb, _zoom(dict(row, **fx), t), 0.0, 0.0)
        elif key in {"flash", "fade_in", "fade_out"}:
            d = _fade_len(key, k, b - a)
            p = (t - a) / d if key != "fade_out" else (b - t) / d
            p = max(0.0, min(1.0, p))
            target = 255.0 if key == "flash" else 0.0
            rgb = np.clip(rgb.astype(np.float32) * p + target * (1 - p) + 0.5, 0, 255).astype(np.uint8)
        elif key == "glitch":
            s = max(1, round(k * 0.012 * w))
            out = rgb.copy()
            out[:, : w - s, 0] = rgb[:, s:, 0]
            out[:, s:, 2] = rgb[:, : w - s, 2]
            rgb = out
        elif key == "bw":
            gray = rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
            v = rgb.astype(np.float32) * (1 - k) + gray[..., None] * k
            rgb = np.clip(v + 0.5, 0, 255).astype(np.uint8)
        elif key == "sepia":
            m = np.array([[(1 - k) * (r == c) + k * _SEPIA[r][c] for c in range(3)] for r in range(3)], np.float32)
            rgb = np.clip(rgb.astype(np.float32) @ m.T + 0.5, 0, 255).astype(np.uint8)
        elif key == "invert":
            rgb = 255 - rgb
        elif key == "mirror":
            rgb = np.ascontiguousarray(rgb[:, ::-1])
        elif key == "pixelate":
            block = max(2, round(k * 0.03 * h) * 2)
            hh, ww = (h // block) * block, (w // block) * block
            if hh and ww:
                cells = rgb[:hh, :ww].reshape(hh // block, block, ww // block, block, 3).mean(axis=(1, 3))
                out = rgb.copy()
                out[:hh, :ww] = np.repeat(np.repeat(cells, block, axis=0), block, axis=1).astype(np.uint8)
                rgb = out
        elif key == "grain":
            noise = np.random.default_rng().uniform(-1, 1, (h, w, 1)).astype(np.float32) * k * 40
            rgb = np.clip(rgb.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        elif key == "vignette":
            angle = 0.3 + k * 1.0
            yy = (np.arange(h, dtype=np.float32) - (h - 1) / 2)[:, None]
            xx = (np.arange(w, dtype=np.float32) - (w - 1) / 2)[None, :]
            d = np.sqrt(xx * xx + yy * yy) / max(1.0, math.hypot(w / 2, h / 2))
            mask = np.cos(angle * np.minimum(d, 1.0)) ** 4
            rgb = np.clip(rgb.astype(np.float32) * mask[..., None], 0, 255).astype(np.uint8)
        elif key == "bars":
            bar = max(1, round(k * 0.14 * h))
            rgb = rgb.copy()
            rgb[:bar] = 0
            rgb[h - bar:] = 0
    return rgb
