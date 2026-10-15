"""Built-in video transitions: timed spans on the master footage (preview + FFmpeg)."""
from __future__ import annotations

import math

# key, label, hint
TRANSITIONS: tuple[tuple[str, str, str], ...] = (
    ("fade_black", "Fade to Black", "Sinks into black over the clip"),
    ("fade_from_black", "Fade from Black", "Rises out of black"),
    ("fade_white", "Fade to White", "Bleaches into white"),
    ("fade_from_white", "Fade from White", "Resolves from white"),
    ("flash", "Flash", "Quick white flash"),
    ("dip_black", "Dip to Black", "Brief dip to black in the middle"),
    ("dissolve", "Dissolve", "Soft blur dissolve"),
    ("cross_blur", "Blur Wipe", "Blurs then clears — soft cut feel"),
    ("wipe_left", "Wipe Left", "Reveals from right to left"),
    ("wipe_right", "Wipe Right", "Reveals from left to right"),
    ("wipe_up", "Wipe Up", "Reveals from bottom to top"),
    ("wipe_down", "Wipe Down", "Reveals from top to bottom"),
)
TRANSITION_LABELS = {key: label for key, label, _hint in TRANSITIONS}
DEFAULT_INTENSITY = 80
DEFAULT_DURATION_MS = 1200


def clean_transition(data: dict | None) -> dict:
    """{"transition": key, "intensity": 0..100}."""
    src = dict(data or {})
    try:
        intensity = max(0, min(100, int(src.get("intensity", DEFAULT_INTENSITY))))
    except (TypeError, ValueError):
        intensity = DEFAULT_INTENSITY
    key = src.get("transition") if src.get("transition") in TRANSITION_LABELS else TRANSITIONS[0][0]
    return {"transition": key, "intensity": intensity}


def transition_label(data: dict | None) -> str:
    return TRANSITION_LABELS[clean_transition(data)["transition"]]


def _progress(a: float, b: float, t: float) -> float:
    return max(0.0, min(1.0, (t - a) / max(1e-3, b - a)))


def transition_filters(spans: list[dict], width: int, height: int) -> list[str]:
    """FFmpeg filters for transition clips (`enable='between(t,…)'`)."""
    out: list[str] = []
    w = max(2, int(width))
    h = max(2, int(height))
    for row in spans or []:
        if str(row.get("kind") or "") != "transition":
            continue
        fx = clean_transition(row)
        a = float(row.get("start_ms") or 0) / 1000.0
        b = float(row.get("end_ms") or 0) / 1000.0
        if b <= a:
            continue
        en = f"enable='between(t,{a:.3f},{b:.3f})'"
        dur = b - a
        k = fx["intensity"] / 100.0
        key = fx["transition"]
        if key == "fade_black":
            out.append(f"fade=t=out:st={a:.3f}:d={dur:.3f}:{en}")
        elif key == "fade_from_black":
            out.append(f"fade=t=in:st={a:.3f}:d={dur:.3f}:{en}")
        elif key == "fade_white":
            out.append(f"fade=t=out:st={a:.3f}:d={dur:.3f}:color=white:{en}")
        elif key == "fade_from_white":
            out.append(f"fade=t=in:st={a:.3f}:d={dur:.3f}:color=white:{en}")
        elif key == "flash":
            d = max(0.08, min(dur, 0.15 + 0.55 * k))
            out.append(f"fade=t=in:st={a:.3f}:d={d:.3f}:color=white:{en}")
        elif key == "dip_black":
            half = max(0.05, dur * 0.5)
            out.append(f"fade=t=out:st={a:.3f}:d={half:.3f}:{en}")
            out.append(f"fade=t=in:st={a + half:.3f}:d={half:.3f}:{en}")
        elif key in {"dissolve", "cross_blur"}:
            sigma = max(0.8, k * 0.035 * h)
            out.append(f"gblur=sigma={sigma:.2f}:{en}")
            if key == "dissolve":
                out.append(f"fade=t=out:st={a:.3f}:d={dur:.3f}:{en}")
        elif key == "wipe_left":
            out.append(_wipe_filter("left", a, b, en))
        elif key == "wipe_right":
            out.append(_wipe_filter("right", a, b, en))
        elif key == "wipe_up":
            out.append(_wipe_filter("up", a, b, en))
        elif key == "wipe_down":
            out.append(_wipe_filter("down", a, b, en))
    return out


def _t_prog(a: float, b: float) -> str:
    return f"clip((T-{a:.3f})/{max(1e-3, b - a):.3f}\\,0\\,1)"


def _wipe_filter(direction: str, a: float, b: float, en: str) -> str:
    """Black wipe via geq — progress 0→1 over the span."""
    p = _t_prog(a, b)
    if direction == "right":
        # black from left covering toward right
        cond = f"lt(X/W\\,{p})"
    elif direction == "left":
        cond = f"gt(X/W\\,1-{p})"
    elif direction == "down":
        cond = f"lt(Y/H\\,{p})"
    else:  # up
        cond = f"gt(Y/H\\,1-{p})"
    return (
        f"geq=lum='if({cond}\\,0\\,lum(X\\,Y))':"
        f"cb='if({cond}\\,128\\,cb(X\\,Y))':"
        f"cr='if({cond}\\,128\\,cr(X\\,Y))':{en}"
    )


def apply_transition(rgb, spans: list[dict], now_ms: int):
    """Preview approximation of transition_filters on an HxWx3 uint8 RGB frame."""
    import numpy as np

    t = now_ms / 1000.0
    for row in spans or []:
        if str(row.get("kind") or "") != "transition":
            continue
        if not (row.get("start_ms", 0) <= now_ms < row.get("end_ms", 0)):
            continue
        fx = clean_transition(row)
        key = fx["transition"]
        k = fx["intensity"] / 100.0
        a = row["start_ms"] / 1000.0
        b = row["end_ms"] / 1000.0
        p = _progress(a, b, t)
        h, w = rgb.shape[:2]

        if key == "fade_black":
            rgb = np.clip(rgb.astype(np.float32) * (1.0 - p) + 0.5, 0, 255).astype(np.uint8)
        elif key == "fade_from_black":
            rgb = np.clip(rgb.astype(np.float32) * p + 0.5, 0, 255).astype(np.uint8)
        elif key == "fade_white":
            rgb = np.clip(rgb.astype(np.float32) * (1.0 - p) + 255.0 * p + 0.5, 0, 255).astype(np.uint8)
        elif key == "fade_from_white":
            rgb = np.clip(rgb.astype(np.float32) * p + 255.0 * (1.0 - p) + 0.5, 0, 255).astype(np.uint8)
        elif key == "flash":
            d = max(0.08, min(b - a, 0.15 + 0.55 * k))
            fp = max(0.0, min(1.0, (t - a) / d))
            rgb = np.clip(rgb.astype(np.float32) * fp + 255.0 * (1.0 - fp) + 0.5, 0, 255).astype(np.uint8)
        elif key == "dip_black":
            # 0→1→0 envelope (dip in the middle)
            dip = 1.0 - abs(2.0 * p - 1.0)
            rgb = np.clip(rgb.astype(np.float32) * (1.0 - dip) + 0.5, 0, 255).astype(np.uint8)
        elif key in {"dissolve", "cross_blur"}:
            sigma = max(0.8, k * 0.035 * h)
            radius = max(1, int(round(math.sqrt(12 * sigma * sigma / 3 + 1) / 2)))
            v = rgb.astype(np.float32)
            for _ in range(2):
                v = _box_blur(v, radius)
            faded = v * (1.0 - p) if key == "dissolve" else v
            if key == "dissolve":
                rgb = np.clip(faded + 0.5, 0, 255).astype(np.uint8)
            else:
                # Blur peaks mid-span then clears
                blur_amt = 1.0 - abs(2.0 * p - 1.0)
                mix = rgb.astype(np.float32) * (1.0 - blur_amt) + v * blur_amt
                rgb = np.clip(mix + 0.5, 0, 255).astype(np.uint8)
        elif key in {"wipe_left", "wipe_right", "wipe_up", "wipe_down"}:
            out = rgb.copy()
            if key == "wipe_right":
                cut = int(round(w * p))
                if cut > 0:
                    out[:, :cut] = 0
            elif key == "wipe_left":
                cut = int(round(w * (1.0 - p)))
                if cut < w:
                    out[:, cut:] = 0
            elif key == "wipe_down":
                cut = int(round(h * p))
                if cut > 0:
                    out[:cut] = 0
            else:
                cut = int(round(h * (1.0 - p)))
                if cut < h:
                    out[cut:] = 0
            rgb = out
    return rgb


def _box_blur(v, radius: int):
    import numpy as np

    if radius < 1:
        return v
    pad = radius
    # Separable box blur
    tmp = np.pad(v, ((0, 0), (pad, pad), (0, 0)), mode="edge")
    csum = np.cumsum(tmp, axis=1)
    horiz = (csum[:, 2 * pad :, :] - csum[:, : -2 * pad, :]) / (2 * pad)
    tmp2 = np.pad(horiz, ((pad, pad), (0, 0), (0, 0)), mode="edge")
    csum2 = np.cumsum(tmp2, axis=0)
    return (csum2[2 * pad :, :, :] - csum2[: -2 * pad, :, :]) / (2 * pad)
