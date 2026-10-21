"""Visual effects and LUT look presentation models."""
from __future__ import annotations

from typing import Any
import numpy as np

DEFAULT_INTENSITY = {"effect": 80, "filter": 80}

EFFECTS = (
    ("none", "None", "No effect"),
    ("vignette", "Vignette", "Darken video edges"),
    ("glow", "Glow", "Soft radiant highlights"),
    ("grayscale", "Grayscale", "Classic monochrome"),
    ("sepia", "Sepia", "Warm vintage tone"),
    ("blur", "Blur", "Gaussian smoothing"),
    ("sharpen", "Sharpen", "Crisp edge boost"),
    ("invert", "Invert", "Negative colors"),
)

TIMED_EFFECTS = ("zoom_in", "zoom_out", "shake", "flash")

FILTER_LOOKS = (
    ("clean", "Clean"),
    ("cinematic", "Cinematic"),
    ("bleach", "Bleach Bypass"),
    ("teal_orange", "Teal & Orange"),
    ("noir", "Film Noir"),
)

EFFECT_LABELS = {k: label for k, label, *_ in EFFECTS}


def clean_fx(kind_or_data: Any = None, data: dict | None = None) -> dict:
    if data is not None:
        kind = str(kind_or_data or "effect")
        src = data if isinstance(data, dict) else {}
    elif isinstance(kind_or_data, str):
        kind = kind_or_data
        src = {}
    elif isinstance(kind_or_data, dict):
        src = kind_or_data
        kind = src.get("kind", "effect")
    else:
        src = {}
        kind = "effect"

    def_intensity = DEFAULT_INTENSITY.get(kind, 80) if isinstance(DEFAULT_INTENSITY, dict) else DEFAULT_INTENSITY
    # Shelf tiles store the look under ``filter``; keep both keys in sync.
    look = str(src.get("look") or src.get("filter") or "clean").strip() or "clean"
    # Heal older clips that only kept the display name after a prior clean wiped ``filter``.
    if kind == "filter" and look in ("", "clean"):
        name = str(src.get("name") or "").strip().lower()
        for lid, label in FILTER_LOOKS:
            if name == label.lower() or name == lid.replace("_", " "):
                look = lid
                break
    effect = str(src.get("effect") or "none").strip() or "none"
    return {
        "kind": kind,
        "effect": effect,
        "filter": look if kind == "filter" else str(src.get("filter") or ""),
        "intensity": max(0, min(100, int(src.get("intensity", def_intensity)))),
        "look": look,
        "duration": float(src.get("duration", 1.0)),
    }


def fx_label(kind_or_data: Any = None, data: dict | None = None) -> str:
    """Human label for an FX clip — accepts ``fx_label(style)`` or ``fx_label(kind, style)``."""
    c = clean_fx(kind_or_data, data)
    if data is not None and isinstance(data, dict):
        src = data
    elif isinstance(kind_or_data, dict):
        src = kind_or_data
    else:
        src = {}
    name = str(src.get("name") or src.get("text") or "").strip()
    key = str(c.get("effect") or "none")
    if key != "none":
        return EFFECT_LABELS.get(key, key.replace("_", " ").title())
    look = str(c.get("look") or "")
    if look and look != "clean":
        for lid, label in FILTER_LOOKS:
            if lid == look:
                return label
        return look.replace("_", " ").title()
    if name:
        return name
    kind = str(c.get("kind") or "effect")
    return kind.replace("_", " ").title()


def _split_chain(chain: str) -> list[str]:
    """Split an ffmpeg chain on commas that are not inside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    quote = False
    i = 0
    while i < len(chain):
        ch = chain[i]
        if ch == "\\" and i + 1 < len(chain):
            buf.append(ch)
            buf.append(chain[i + 1])
            i += 2
            continue
        if ch == "'":
            quote = not quote
        if ch == "," and not quote:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf))
    return [part for part in parts if part]


def _window(chain: str, item: dict) -> str:
    """Keep an effect on only while its timeline clip is active."""
    if not chain:
        return ""
    try:
        start = int(item.get("start_ms"))
        end = int(item.get("end_ms"))
    except (TypeError, ValueError):
        return chain
    if end <= start:
        return chain
    tag = f":enable='between(t,{start / 1000.0:.3f},{end / 1000.0:.3f})'"
    return ",".join(part + tag for part in _split_chain(chain))


def _look_chain(look: str, intensity: int) -> str:
    from claynext.models.adjust import FILTER_PRESETS, adjust_filter, scaled_adjust

    preset = FILTER_PRESETS.get(look)
    if not preset or not preset[1]:
        return ""
    return adjust_filter(scaled_adjust(preset[1], intensity)) or ""


def _effect_chain(effect: str, intensity: int) -> str:
    from claynext.models.adjust import _vignette_filter

    amount = max(0, min(100, int(intensity))) / 100.0
    if effect == "vignette":
        return _vignette_filter(amount)
    if effect in ("grayscale", "noir", "mono"):
        return f"eq=saturation={1.0 - amount:.3f}"
    if effect == "sepia":
        return "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"
    if effect == "invert":
        if amount >= 0.99:
            return "negate"
        keep = 1.0 - amount
        return (
            "lutrgb="
            f"r='clip(val*{keep:.3f}+(255-val)*{amount:.3f},0,255)':"
            f"g='clip(val*{keep:.3f}+(255-val)*{amount:.3f},0,255)':"
            f"b='clip(val*{keep:.3f}+(255-val)*{amount:.3f},0,255)'"
        )
    if effect == "fade_black":
        gain = max(0.0, 1.0 - amount)
        return (
            "lutrgb="
            f"r='clip(val*{gain:.3f},0,255)':g='clip(val*{gain:.3f},0,255)':b='clip(val*{gain:.3f},0,255)'"
        )
    if effect == "flash":
        add = int(round(255 * amount * 0.5))
        return f"lutrgb=r='clip(val+{add},0,255)':g='clip(val+{add},0,255)':b='clip(val+{add},0,255)'"
    return ""


def fx_filters(fx_data: dict | list | None, src_w: int = 1920, src_h: int = 1080) -> list[str]:
    """Encode the same looks the preview paints, active only on each clip's span."""
    _ = (src_w, src_h)
    if isinstance(fx_data, list):
        out: list[str] = []
        for item in fx_data:
            out.extend(fx_filters(item, src_w, src_h))
        return out
    src = fx_data if isinstance(fx_data, dict) else {}
    c = clean_fx(fx_data)
    filters: list[str] = []
    kind = str(c.get("kind") or src.get("kind") or "")
    look = str(c.get("look") or "")
    if kind == "filter" and look not in ("", "none", "clean"):
        chain = _look_chain(look, int(c["intensity"]))
        if chain:
            filters.append(_window(chain, src))
    effect = str(c.get("effect") or "none")
    if effect not in ("", "none"):
        chain = _effect_chain(effect, int(c["intensity"]))
        if chain:
            filters.append(_window(chain, src))
    transition = str(src.get("transition") or "")
    if kind == "transition" and transition not in ("", "none"):
        chain = _effect_chain(transition, int(src.get("intensity") or c.get("intensity") or 80))
        if chain:
            filters.append(_window(chain, src))
    return [part for part in filters if part]


def apply_fx(rgb: Any, spans: list[dict] | dict | None = None, now_ms: int = 0) -> Any:
    """Apply visual effects/filters to an RGB image array or bytes."""
    if rgb is None or not spans:
        return rgb
    if not isinstance(rgb, np.ndarray):
        return rgb
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        return rgb

    from claynext.models.adjust import FILTER_PRESETS, grade_rgb, scaled_adjust

    span_list = [spans] if isinstance(spans, dict) else list(spans)
    out = rgb.copy()
    _ = now_ms  # reserved for timed progress (flash/zoom/transitions)

    for item in span_list:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "effect")
        key = (
            item.get(kind)
            or item.get("effect")
            or item.get("filter")
            or item.get("look")
            or item.get("transition")
            or "none"
        )
        key = str(key or "none")
        intensity_pct = max(0, min(100, int(item.get("intensity", 80))))
        intensity = intensity_pct / 100.0

        # Filter shelf looks → colour grade presets (Film Noir, Cinematic, …).
        if kind == "filter" or key in FILTER_PRESETS:
            look = key if key not in ("none", "") else str(item.get("look") or "clean")
            if look in ("none", "clean", ""):
                continue
            _label, preset = FILTER_PRESETS.get(look, ("", {}))
            if not preset:
                # Legacy: treat unknown noir-like keys as mono.
                if look in ("grayscale", "mono"):
                    preset = FILTER_PRESETS["mono"][1]
                else:
                    continue
            out = grade_rgb(out, scaled_adjust(preset, intensity_pct))
            continue

        if key in ("none", ""):
            continue
        if key in ("grayscale", "noir", "mono"):
            gray = (out[:, :, 0] * 0.299 + out[:, :, 1] * 0.587 + out[:, :, 2] * 0.114).astype(np.uint8)
            for ch in range(3):
                out[:, :, ch] = (out[:, :, ch] * (1.0 - intensity) + gray * intensity).astype(np.uint8)
        elif key == "invert":
            inv = 255 - out
            out = (out * (1.0 - intensity) + inv * intensity).astype(np.uint8)
        elif key == "sepia":
            r = out[:, :, 0] * 0.393 + out[:, :, 1] * 0.769 + out[:, :, 2] * 0.189
            g = out[:, :, 0] * 0.349 + out[:, :, 1] * 0.686 + out[:, :, 2] * 0.168
            b = out[:, :, 0] * 0.272 + out[:, :, 1] * 0.534 + out[:, :, 2] * 0.131
            sep = np.clip(np.stack([r, g, b], axis=2), 0, 255).astype(np.uint8)
            out = (out * (1.0 - intensity) + sep * intensity).astype(np.uint8)
        elif key == "vignette":
            h, w = out.shape[:2]
            y, x = np.ogrid[:h, :w]
            cx, cy = w / 2.0, h / 2.0
            max_dist = max(1.0, float(np.sqrt(cx**2 + cy**2)))
            dist = np.sqrt((x - cx)**2 + (y - cy)**2) / max_dist
            mask = np.clip(1.0 - (dist ** 1.5) * intensity, 0.0, 1.0)[:, :, np.newaxis]
            out = np.clip(out * mask, 0, 255).astype(np.uint8)
        elif key == "flash":
            out = np.clip(out.astype(np.float32) + 255 * intensity * 0.5, 0, 255).astype(np.uint8)
        elif key == "fade_black":
            ratio = max(0.0, min(1.0, 1.0 - intensity))
            out = (out * ratio).astype(np.uint8)

    return out

