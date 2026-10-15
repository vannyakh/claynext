"""Paint styled text overlays (fill, stroke, shadow, box) exactly as the preview and thumbnails show them."""
from __future__ import annotations

import struct
import unicodedata
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt, QTextBoundaryFinder
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QIcon, QRawFont, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient, QTransform

from claynext.constants.theme_constants import COLOR_BORDER, COLOR_TEXT_MUTED
from claynext.models.text_style import (
    BOX_PAD, REF_H, anim_frame, apply_case, chars_for_words, clean_text_style,
    word_count, word_spans,
)

_BASE_PX = 100.0
_FALLBACK_FONTS = (
    "Khmer Sangam MN", "Khmer MN", "Noto Sans Khmer", "Khmer OS", "Khmer UI", "Leelawadee UI",
    "Noto Sans", "Arial Unicode MS",
)


_SCRIPTS = {
    "GREEK": "Greek", "CYRILLIC": "Cyrillic", "ARMENIAN": "Armenian", "HEBREW": "Hebrew", "ARABIC": "Arabic",
    "DEVANAGARI": "Devanagari", "BENGALI": "Bengali", "GURMUKHI": "Gurmukhi", "GUJARATI": "Gujarati",
    "ORIYA": "Oriya", "TAMIL": "Tamil", "TELUGU": "Telugu", "KANNADA": "Kannada", "MALAYALAM": "Malayalam",
    "SINHALA": "Sinhala", "THAI": "Thai", "LAO": "Lao", "TIBETAN": "Tibetan", "MYANMAR": "Myanmar",
    "GEORGIAN": "Georgian", "KHMER": "Khmer", "HANGUL": "Korean", "HIRAGANA": "Japanese", "KATAKANA": "Japanese",
    "CJK": "SimplifiedChinese",
}


def _scripts(text: str) -> frozenset:
    found = set()
    for ch in set(text):
        if ord(ch) < 0x370:
            continue
        head = unicodedata.name(ch, "").split(" ", 1)[0]
        system = getattr(QFontDatabase.WritingSystem, _SCRIPTS.get(head, ""), None)
        if system is not None:
            found.add(system)
    return frozenset(found)


@lru_cache(maxsize=256)
def _covering(family: str, needed: frozenset) -> str:
    def covers(name: str) -> bool:
        return needed <= set(QFontDatabase.writingSystems(name))

    if covers(family):
        return family
    pool = [name for name in _FALLBACK_FONTS if QFontDatabase.hasFamily(name)]
    pool += QFontDatabase.families(next(iter(needed)))
    return next((name for name in pool if covers(name)), family)


@lru_cache(maxsize=128)
def burn_metrics(family: str, bold: bool = False, italic: bool = False) -> dict:
    """Per-em metrics the subtitle writer needs to draw `family` where the preview does.
    `asc` / `desc` / `line` are Qt's layout; `win_asc` / `win_desc` are what libass sizes the font by."""
    font = QFont(family)
    font.setPixelSize(int(_BASE_PX))
    font.setBold(bold)
    font.setItalic(italic)
    fm = QFontMetricsF(font)
    asc, desc = fm.ascent() / _BASE_PX, fm.descent() / _BASE_PX
    win_asc, win_desc = asc, desc
    raw = QRawFont.fromFont(font)
    os2, head = bytes(raw.fontTable("OS/2")), bytes(raw.fontTable("head"))
    if len(os2) >= 78 and len(head) >= 20:
        upem = struct.unpack(">H", head[18:20])[0]
        typo_asc, typo_desc = struct.unpack(">hh", os2[68:72])
        up, down = struct.unpack(">hh", os2[74:78])
        if not up + down:
            up, down = typo_asc, -typo_desc
        if upem and up + down:
            win_asc, win_desc = up / upem, down / upem
    return {"asc": asc, "desc": desc, "line": asc + desc, "win_asc": win_asc, "win_desc": win_desc}


def font_for(family: str, text: str) -> str:
    """`family` when it supports every script in `text`; otherwise an installed font that does.
    libass falls back differently from Qt, so naming the font keeps the burn-in the same size as the preview."""
    needed = _scripts(text or "")
    return _covering(family, needed) if needed else family


def text_px(style: dict, canvas_h: float) -> float:
    return style["font_size"] * style["scale"] / 100.0 * canvas_h / REF_H


@lru_cache(maxsize=256)
def _base_path(family: str, bold: bool, italic: bool, underline: bool, letter: float, align: str,
               text: str, shown: int) -> tuple[QPainterPath, QRectF]:
    font = QFont(family)
    font.setPixelSize(int(_BASE_PX))
    font.setBold(bold)
    font.setItalic(italic)
    if letter:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter)
    fm = QFontMetricsF(font)
    lines = text.split("\n")
    widths = [fm.horizontalAdvance(line) for line in lines]
    block_w = max(max(widths, default=0.0), _BASE_PX * 0.3)
    line_h = fm.ascent() + fm.descent()
    block_h = (len(lines) - 1) * line_h + fm.ascent() + fm.descent()
    path = QPainterPath()
    left = shown
    for index, (line, width) in enumerate(zip(lines, widths)):
        x = {"left": 0.0, "right": block_w - width}.get(align, (block_w - width) / 2)
        baseline = index * line_h + fm.ascent()
        part = line[: max(0, left)]
        left -= len(line)
        if part:
            path.addText(QPointF(x, baseline), font, part)
            if underline:
                path.addRect(QRectF(x, baseline + fm.underlinePos(), fm.horizontalAdvance(part), max(1.0, fm.lineWidth())))
    path.translate(-block_w / 2, -block_h / 2)
    return path, QRectF(-block_w / 2, -block_h / 2, block_w, block_h)


def text_path(
    style: dict, text: str, px: float, reveal: float = 1.0, reveal_mode: str = "chars",
) -> tuple[QPainterPath, QRectF]:
    """Glyph outlines centred on (0, 0) at `px`, plus the block bounds (without box padding)."""
    shown_text = apply_case(text or "", style["case"])
    chars = len(shown_text.replace("\n", ""))
    if reveal_mode == "words":
        shown = chars if reveal >= 1.0 else chars_for_words(shown_text, reveal * word_count(shown_text))
    else:
        shown = chars if reveal >= 1.0 else round(max(0.0, reveal) * chars)
    letter = style["letter"] * _BASE_PX / max(1e-6, style["font_size"] * style["scale"] / 100.0)
    path, bounds = _base_path(font_for(style["font"], shown_text), style["bold"], style["italic"], style["underline"],
                              round(letter, 2), style["align"], shown_text, shown)
    k = px / _BASE_PX
    scale = QTransform.fromScale(k, k)
    return scale.map(path), scale.mapRect(bounds)


def caption_width(x: float, aspect: float, style: dict | None = None) -> float:
    """Widest a caption centred at `x` may get without leaving the picture, in canvas heights."""
    if style and style.get("caption_fit"):
        frac = max(0.4, min(0.95, float(style.get("caption_width") or 80) / 100.0))
        return frac * max(0.2, float(aspect))
    room = max(0.3, min(0.9, 2 * min(float(x), 1 - float(x)) - 0.04))
    return room * max(0.2, float(aspect))


def _atoms(text: str, fits) -> list[str]:
    """Pieces between line-break opportunities; a piece too wide on its own is cut between characters."""
    cuts = [0]
    finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Line, text)
    while (pos := finder.toNextBoundary()) not in (-1, cuts[-1]):
        cuts.append(pos)
    if cuts[-1] != len(text):
        cuts.append(len(text))
    atoms: list[str] = []
    for a, b in zip(cuts, cuts[1:]):
        piece = text[a:b]
        if fits(piece.rstrip()):
            atoms.append(piece)
            continue
        chars = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Grapheme, piece)
        start = 0
        while (pos := chars.toNextBoundary()) not in (-1, start):
            atoms.append(piece[start:pos])
            start = pos
    return atoms


_GAPS = " \t\u200b"


def _pack(atoms: list[str], fits) -> list[str]:
    lines, current = [], ""
    for atom in atoms:
        if current and not fits((current + atom).rstrip(_GAPS)):
            lines.append(current.rstrip(_GAPS))
            current = atom.lstrip(_GAPS)
        else:
            current += atom
    if current.strip(_GAPS):
        lines.append(current.rstrip(_GAPS))
    return lines


@lru_cache(maxsize=1024)
def _wrap(family: str, bold: bool, italic: bool, letter: float, case: str, text: str, limit: int) -> str:
    font = QFont(family)
    font.setPixelSize(int(_BASE_PX))
    font.setBold(bold)
    font.setItalic(italic)
    if letter:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter)
    fm = QFontMetricsF(font)

    def width(s: str) -> float:
        return fm.horizontalAdvance(apply_case(s, case))

    out: list[str] = []
    for para in text.split("\n"):
        para = " ".join(para.split())
        if width(para) <= limit:
            out.append(para)
            continue
        atoms = _atoms(para, lambda s: width(s) <= limit)
        lines = _pack(atoms, lambda s: width(s) <= limit)
        lo, hi = width(para) / max(1, len(lines)), float(limit)
        for _ in range(8):
            mid = (lo + hi) / 2
            if len(_pack(atoms, lambda s, m=mid: width(s) <= m)) <= len(lines):
                hi = mid
            else:
                lo = mid
        out += _pack(atoms, lambda s: width(s) <= hi)
    return "\n".join(out)


def wrap_text(style: dict, text: str, max_w: float) -> str:
    """Break `text` into balanced lines no wider than `max_w` canvas heights."""
    size = max(1e-6, style["font_size"] * style["scale"] / 100.0)
    letter = style["letter"] * _BASE_PX / size
    limit = int(max_w * REF_H * _BASE_PX / size)
    family = font_for(style["font"], apply_case(text or "", style["case"]))
    return _wrap(family, style["bold"], style["italic"], round(letter, 2), style["case"], text or "", limit)


def _caption_inner_w(style: dict, max_w: float) -> float:
    """Wrap width that leaves room for background padding inside `max_w`."""
    if not style.get("bg_on"):
        return max_w
    size = max(1.0, float(style["font_size"]) * float(style["scale"]) / 100.0)
    pad = 2.0 * BOX_PAD[0] * size / REF_H
    return max(0.05, max_w - pad)


# Auto caption size ignores the stored font_size and fills the dub width frame.
_CAPTION_AUTO_MIN = 12
_CAPTION_AUTO_MAX = 48
_CAPTION_AUTO_MAX_H = 0.24  # tallest caption block as a fraction of canvas height


def fit_caption(style: dict, text: str, max_w: float, max_h: float | None = None) -> tuple[dict, str]:
    """Auto-size + wrap so the caption fills the dub width frame without overflowing.

    Stored ``font_size`` is ignored — the largest size that fits ``max_w`` (and
    ``max_h``) wins. Returns ``(fitted_style, wrapped_text)``.
    """
    style = clean_text_style(dict(style))
    raw = text or ""
    if not raw.strip() or max_w <= 0:
        return style, raw

    slack = 0.002
    height_cap = _CAPTION_AUTO_MAX_H if max_h is None else max(0.08, float(max_h))

    def layout(size: int) -> tuple[dict, str, float, float]:
        st = dict(style, font_size=int(size))
        lines = wrap_text(st, raw, _caption_inner_w(st, max_w))
        box = item_box(st, lines or " ", 1000.0)
        return st, lines, box.width() / 1000.0, box.height() / 1000.0

    def fits(width: float, height: float) -> bool:
        return width <= max_w + slack and height <= height_cap + slack

    lo, hi = _CAPTION_AUTO_MIN, _CAPTION_AUTO_MAX
    best_st, best_lines, _, _ = layout(lo)
    while lo <= hi:
        mid = (lo + hi) // 2
        st, lines, width, height = layout(mid)
        if fits(width, height):
            best_st, best_lines = st, lines
            lo = mid + 1
        else:
            hi = mid - 1
    return best_st, best_lines


def box_rect(style: dict, bounds: QRectF, px: float) -> QRectF:
    """The visible box: block bounds plus the background padding (a hair of slack when there is no box)."""
    if style["bg_on"]:
        return bounds.adjusted(-BOX_PAD[0] * px, -BOX_PAD[1] * px, BOX_PAD[0] * px, BOX_PAD[1] * px)
    pad = 0.08 * px
    return bounds.adjusted(-pad, -pad, pad, pad)


def item_box(style: dict, text: str, canvas_h: float) -> QRectF:
    px = text_px(style, canvas_h)
    _path, bounds = text_path(style, text, px)
    return box_rect(style, bounds, px)


def measure_box(style: dict, text: str) -> tuple[float, float]:
    """Text block size as fractions of the canvas height (the subtitle writer anchors on it)."""
    style = clean_text_style(style)
    px = text_px(style, 1000.0)
    _path, bounds = text_path(style, text, px)
    return bounds.width() / 1000.0, bounds.height() / 1000.0


def _paint_fill(p: QPainter, path: QPainterPath, style: dict, k: float, color: QColor, stroke_pen: QPen | None):
    if style["shadow_on"]:
        d = style["shadow_dist"] * k
        shade = QColor(style["shadow_color"])
        shade.setAlphaF(0.8)
        shadow = path.translated(d, d)
        if stroke_pen is not None:
            p.strokePath(shadow, QPen(shade, stroke_pen.widthF(), Qt.PenStyle.SolidLine,
                                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.fillPath(shadow, shade)
    if stroke_pen is not None:
        p.strokePath(path, stroke_pen)
    p.fillPath(path, color)


def paint_text(p: QPainter, style: dict, text: str, center: QPointF, canvas_h: float,
               rotation: float = 0.0, frame: dict | None = None):
    frame = frame or anim_frame(style, 0, 0)
    if frame["alpha"] <= 0.001:
        return
    k = canvas_h / REF_H
    px = text_px(style, canvas_h)
    mode = str(frame.get("reveal_mode") or "chars")
    path, bounds = text_path(style, text, px, frame["reveal"], mode)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(center.x() + frame["dx"] * canvas_h, center.y() + frame["dy"] * canvas_h)
    p.rotate(rotation + frame["rot"])
    p.scale(frame["scale"], frame["scale"])
    p.setOpacity(p.opacity() * style["opacity"] / 100.0 * frame["alpha"])
    p.setPen(Qt.PenStyle.NoPen)
    if style["bg_on"] and style["bg_opacity"] > 0:
        bg = QColor(style["bg_color"])
        bg.setAlphaF(style["bg_opacity"] / 100.0)
        p.setBrush(bg)
        radius = 0.22 * px
        # Full-line bounds for the box even while words are still revealing.
        _full, full_bounds = text_path(style, text, px, 1.0, "chars")
        p.drawRoundedRect(box_rect(style, full_bounds, px), radius, radius)
    stroke_pen = None
    if style["stroke_on"]:
        stroke_pen = QPen(QColor(style["stroke_color"]), 2 * style["stroke_width"] * k,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    hl = float(frame.get("highlight", -1.0))
    if hl >= 0.0 and (text or "").strip():
        # Base (upcoming) pass, then highlighted words on top.
        dim = QColor(style["color"])
        dim.setAlphaF(0.55)
        _paint_fill(p, path, style, k, dim, stroke_pen)
        n = word_count(apply_case(text or "", style["case"]))
        shown_words = max(0.0, min(float(n), hl * n + 1e-6))
        hi_path, _ = text_path(style, text, px, shown_words / n, "words")
        _paint_fill(p, hi_path, style, k, QColor(style.get("highlight_color") or "#facc15"), stroke_pen)
    else:
        _paint_fill(p, path, style, k, QColor(style["color"]), stroke_pen)
    p.restore()


def _tile(w: int, h: int, *, plate: bool = True) -> tuple[QPixmap, QPainter]:
    """Clear source plate behind caption samples (matches shelf look tiles)."""
    pix = QPixmap(w * 2, h * 2)
    pix.setDevicePixelRatio(2.0)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if plate:
        rad = QRadialGradient(w / 2, h / 2, max(w, h) * 0.75)
        rad.setColorAt(0.0, QColor("#1e293b"))
        rad.setColorAt(0.65, QColor("#101724"))
        rad.setColorAt(1.0, QColor("#0a0f17"))
        p.setBrush(rad)
        p.setPen(QPen(QColor(255, 255, 255, 24), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 7, 7)
    return pix, p


def _none_mark(p: QPainter, w: int, h: int):
    side = min(w, h) * 0.42
    rect = QRectF((w - side) / 2, (h - side) / 2, side, side)
    p.setPen(QPen(QColor(COLOR_TEXT_MUTED), 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(rect)
    p.drawLine(rect.topRight() + QPointF(-side * 0.15, side * 0.15), rect.bottomLeft() + QPointF(side * 0.15, -side * 0.15))


def _fit_paint(p: QPainter, style: dict, text: str, w: int, h: int, frame: dict | None = None, fill: float = 0.78):
    canvas_h = float(REF_H)
    box = item_box(style, text, canvas_h)
    fit = min(w * fill / max(1.0, box.width()), h * 0.62 / max(1.0, box.height()))
    paint_text(p, style, text, QPointF(w / 2, h / 2), canvas_h * fit, frame=frame)


def template_pixmap(style: dict, text: str, w: int, h: int, fill: float = 0.78, *, plate: bool = True, frame: dict | None = None) -> QPixmap:
    pix, p = _tile(w, h, plate=plate)
    _fit_paint(p, clean_text_style(style), text, w, h, frame=frame, fill=fill)
    p.end()
    return pix


def preset_icon(key: str, values: dict, side: int = 34) -> QIcon:
    pix, p = _tile(side, side)
    if key == "none":
        _none_mark(p, side, side)
    else:
        style = clean_text_style(dict(values, bold=True, font_size=40))
        _fit_paint(p, style, "Aa", side, side, fill=0.66)
    p.end()
    return QIcon(pix)


def anim_icon(slot: str, kind: str, w: int = 56, h: int = 44) -> QIcon:
    """"ABC" with faint ghosts along its path, so each tile shows the direction of the motion."""
    pix, p = _tile(w, h)
    if kind == "none":
        _none_mark(p, w, h)
        p.end()
        return QIcon(pix)
    style = clean_text_style({"bold": True, "font_size": 40, slot: kind, "anim_in_ms": 1000,
                              "anim_out_ms": 1000, "anim_loop_ms": 1000})
    dur = 3000
    if kind in {"fade", "blink"}:
        shots = [(1500, 0.45)]
    elif kind == "typewriter":
        shots = [(600 if slot == "anim_in" else 2400, 1.0)]
    elif kind in {"words", "highlight"}:
        shots = [(400, 1.0), (1200, 1.0), (2200, 1.0)]
    elif slot == "anim_in":
        shots = [(60, 0.18), (200, 0.35), (1000, 1.0)]
    elif slot == "anim_out":
        shots = [(2000, 1.0), (2800, 0.35), (2940, 0.18)]
    else:
        shots = [(250, 0.3), (750, 0.3), (0, 1.0)]
    for t, ghost in shots:
        frame = anim_frame(style, t, dur)
        frame["alpha"] = ghost
        _fit_paint(p, style, "ABC", w, h, frame=frame, fill=0.5)
    p.end()
    return QIcon(pix)


def anim_loop_ms(kind: str) -> int:
    """Preview loop length for a caption / text animation kind."""
    if kind in {"words", "highlight"}:
        return 2200
    if kind == "typewriter":
        return 1800
    if kind == "fade":
        return 1400
    if kind == "none":
        return 0
    return 1600


def anim_preview_pixmap(
    kind: str,
    t_ms: int,
    w: int = 72,
    h: int = 44,
    *,
    highlight_color: str = "#facc15",
    sample: str | None = None,
    plate: bool = True,
) -> QPixmap:
    """One frame of a looping motion preview for caption / text tiles."""
    pix, p = _tile(w, h, plate=plate)
    if kind == "none":
        _none_mark(p, w, h)
        p.end()
        return pix
    # Multi-word sample so word / karaoke reveal steps are visible in the tile.
    text = sample or ("One two three" if kind in {"words", "highlight"} else "ABC")
    dur = max(400, anim_loop_ms(kind))
    if t_ms == 0:
        if kind == "fade":
            t = int(dur * 0.65)
        elif kind == "typewriter":
            t = int(dur * 0.85)
        elif kind in {"words", "highlight"}:
            t = int(dur * 0.35)
        else:
            t = int(dur * 0.5)
    else:
        t = int(t_ms) % dur
    style = clean_text_style({
        "bold": True,
        "font_size": 28 if kind in {"words", "highlight"} else 40,
        "anim_in": kind,
        "anim_in_ms": 900 if kind == "fade" else 1200,
        "anim_out": "none",
        "anim_loop": "none",
        "highlight_color": highlight_color or "#facc15",
        "bg_on": True,
        "bg_opacity": 36,
        "color": "#f8fafc",
    })
    frame = anim_frame(style, t, dur)
    _fit_paint(p, style, text, w, h, frame=frame, fill=0.58)
    p.end()
    return pix

