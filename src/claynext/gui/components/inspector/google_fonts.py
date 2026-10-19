"""Load the shared Google Fonts into Qt for the text inspector and preview."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase

from claynext.models.google_fonts import CATALOG, fetch_google_fonts, font_file, google_font_names
from claynext.utils.paths import FONT_DIR

_registered: dict[str, str] = {}
_loaded: set[str] = set()


def register_google_fonts(paths: list[str] | None = None) -> dict[str, str]:
    """Load downloaded files into Qt. Call this on the UI thread."""
    files = paths if paths is not None else [str(path) for path in FONT_DIR.glob("*.ttf")]
    added = False
    for file in files:
        if file in _loaded:
            continue
        font_id = QFontDatabase.addApplicationFont(file)
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            continue
        for name, slug, _filename in CATALOG:
            if font_file(slug) == Path(file) or font_file(slug).name == Path(file).name:
                _registered[name] = families[0]
                break
        else:
            _registered[families[0]] = families[0]
        _loaded.add(file)
        added = True
    if added:
        from claynext.gui.components.render.text import drop_measure_cache
        drop_measure_cache()
    return dict(_registered)


def family_for(name: str) -> str:
    """Qt family for a menu name, once that file has been registered."""
    return _registered.get(name, name)


__all__ = [
    "family_for",
    "fetch_google_fonts",
    "google_font_names",
    "register_google_fonts",
]
