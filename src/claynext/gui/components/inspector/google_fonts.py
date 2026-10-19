"""Khmer-first Google Fonts used by the text inspector."""
from __future__ import annotations

import urllib.request
from pathlib import Path
from urllib.parse import quote

from PySide6.QtGui import QFontDatabase

from claynext.utils.paths import FONT_DIR

# (menu name, github folder, file). Khmer faces come first.
_CATALOG: tuple[tuple[str, str, str], ...] = (
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
_registered: dict[str, str] = {}
_loaded: set[str] = set()


def google_font_names() -> list[str]:
    """Menu order: Khmer Google Fonts, then a few Latin Google Fonts."""
    return [name for name, _slug, _file in _CATALOG]


def _dest(slug: str) -> Path:
    return FONT_DIR / f"{slug}.ttf"


def fetch_google_fonts(progress_callback=None) -> list[str]:
    """Download any missing faces. Safe to call off the UI thread."""
    del progress_callback
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for _name, slug, filename in _CATALOG:
        dest = _dest(slug)
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


def register_google_fonts(paths: list[str] | None = None) -> dict[str, str]:
    """Load downloaded files into Qt. Call this on the UI thread."""
    files = paths if paths is not None else [str(path) for path in FONT_DIR.glob("*.ttf")]
    for file in files:
        if file in _loaded:
            continue
        font_id = QFontDatabase.addApplicationFont(file)
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            continue
        for name, slug, _filename in _CATALOG:
            if _dest(slug) == Path(file) or _dest(slug).name == Path(file).name:
                _registered[name] = families[0]
                break
        else:
            _registered[families[0]] = families[0]
        _loaded.add(file)
    return dict(_registered)


def family_for(name: str) -> str:
    """Qt family for a menu name, once that file has been registered."""
    return _registered.get(name, name)
