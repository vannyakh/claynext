"""Jela QSS. Sections live beside this module."""
from __future__ import annotations

from jela.constants.theme_constants import accent_rgba, primary_color
from jela.gui.styles.chrome import chrome_qss
from jela.gui.styles.controls import controls_qss
from jela.gui.styles.home import home_qss
from jela.gui.styles.studio import studio_qss
from jela.gui.styles.launcher import launcher_qss
from jela.gui.styles.media import media_qss
from jela.gui.styles.settings import settings_qss
from jela.gui.styles.shell import shell_qss
from jela.gui.styles.widgets import widgets_qss


def build_stylesheet(primary=None):
    """Build the full QSS stylesheet with accent color substitution."""
    accent = primary or primary_color()
    wash = accent_rgba(accent)
    parts = [
        chrome_qss(accent, wash),
        shell_qss(accent, wash),
        media_qss(accent, wash),
        controls_qss(accent, wash),
        widgets_qss(accent, wash),
        launcher_qss(accent, wash),
        home_qss(accent, wash),
        studio_qss(accent, wash),
        settings_qss(accent, wash),
    ]
    text = parts[0]
    for part in parts[1:]:
        text += part[1:] if part.startswith("\n") else part
    return text


MAIN_STYLESHEET = build_stylesheet()
