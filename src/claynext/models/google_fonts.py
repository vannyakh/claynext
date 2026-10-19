"""Khmer-first Google Fonts shared by the preview and the export burn-in."""
from __future__ import annotations

import urllib.request
from pathlib import Path
from urllib.parse import quote

from claynext.utils.paths import FONT_DIR

# (menu name, github folder, file). Khmer faces come first.
CATALOG: tuple[tuple[str, str, str], ...] = (
    ("Kantumruy Pro", "kantumruypro", "KantumruyPro[wght].ttf"),
    ("Kdam Thmor Pro", "kdamthmorpro", "KdamThmorPro-Regular.ttf"),
    ("Noto Sans Khmer", "notosanskhmer", "NotoSansKhmer[wdth,wght].ttf"),
    ("Noto Serif Khmer", "notoserifkhmer", "NotoSerifKhmer[wdth,wght].ttf"),
    ("Battambang", "battambang", "Battambang-Regular.ttf"),
    ("Hanuman", "hanuman", "Hanuman[wght].ttf"),
    ("Koulen", "koulen", "Koulen-Regular.ttf"),
    ("Moul", "moul", "Moul-Regular.ttf"),
    ("Bayon", "bayon", "Bayon-Regular.ttf"),
    ("Bokor", "bokor", "Bokor-Regular.ttf"),
    ("Content", "content", "Content-Regular.ttf"),
    ("Dangrek", "dangrek", "Dangrek-Regular.ttf"),
    ("Fasthand", "fasthand", "Fasthand-Regular.ttf"),
    ("Freehand", "freehand", "Freehand-Regular.ttf"),
    ("Khmer", "khmer", "Khmer.ttf"),
    ("Metal", "metal", "Metal-Regular.ttf"),
    ("Odor Mean Chey", "odormeanchey", "OdorMeanChey-Regular.ttf"),
    ("Preahvihear", "preahvihear", "Preahvihear-Regular.ttf"),
    ("Siemreap", "siemreap", "Siemreap.ttf"),
    ("Suwannaphum", "suwannaphum", "Suwannaphum-Regular.ttf"),
    ("Taprom", "taprom", "Taprom-Regular.ttf"),
    ("Koh Santepheap", "kohsantepheap", "KohSantepheap-Regular.ttf"),
    ("Chenla", "chenla", "Chenla.ttf"),
    ("Inter", "inter", "Inter[opsz,wght].ttf"),
    ("Roboto", "roboto", "Roboto[wdth,wght].ttf"),
    ("Noto Sans", "notosans", "NotoSans[wdth,wght].ttf"),
    ("Noto Serif", "notoserif", "NotoSerif[wdth,wght].ttf"),
)

_RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl/{slug}/{filename}"
_NAMES = {name for name, _slug, _file in CATALOG}


def google_font_names() -> list[str]:
    """Menu order: Khmer Google Fonts, then a few Latin Google Fonts."""
    return [name for name, _slug, _file in CATALOG]


def is_google_font(name: str) -> bool:
    return name in _NAMES


def font_file(slug: str) -> Path:
    return FONT_DIR / f"{slug}.ttf"


def fetch_google_fonts(progress_callback=None) -> list[str]:
    """Download any missing faces. Safe to call off the UI thread."""
    del progress_callback
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for _name, slug, filename in CATALOG:
        dest = font_file(slug)
        if dest.is_file() and dest.stat().st_size > 1000:
            saved.append(str(dest))
            continue
        url = _RAW.format(slug=slug, filename=quote(filename))
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "claynext"})
            with urllib.request.urlopen(request, timeout=30) as response:
                dest.write_bytes(response.read())
        except Exception:
            dest.unlink(missing_ok=True)
            continue
        if dest.is_file() and dest.stat().st_size > 1000:
            saved.append(str(dest))
        else:
            dest.unlink(missing_ok=True)
    return saved
