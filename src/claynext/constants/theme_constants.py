"""
Claynext Studio Color Tokens, Theme Palette, and Accent Config.
Inspired by CamDot's theme system with palette roles and accent wash.
"""
from PySide6.QtGui import QColor, QPalette

# ─── Active Theme State ───────────────────────────────────────────────
DEFAULT_DARK = True
DEFAULT_PRIMARY = "#6366f1"     # Indigo accent
SELECTION_ALPHA = 48

_active_primary = DEFAULT_PRIMARY

# ─── Named Color Tokens ──────────────────────────────────────────────
# Chrome (sidebar, dock titles, shelf headers) — one shared dark band
COLOR_BG_DARK        = "#080c12"
COLOR_BG_SIDEBAR     = "#0b1017"
COLOR_BG_HEADER      = "#0b1017"
COLOR_BG_TITLEBAR    = "#080c12"
# Panel / dock bodies — lifted from chrome / window so panels read clearly
COLOR_BG_CARD        = "#0C0F14"
COLOR_BG_CARD_HOVER  = "#1c2838"
COLOR_BG_INPUT       = "#0a0e16"
COLOR_BG_SEGMENT     = "#181818"
COLOR_BG_STATUSBAR   = "#080c12"
COLOR_BORDER         = "#1e2d40"
COLOR_BORDER_FOCUS   = DEFAULT_PRIMARY
COLOR_PRIMARY        = DEFAULT_PRIMARY
COLOR_PRIMARY_HOVER  = "#4f46e5"
COLOR_ACCENT_PURPLE  = "#8b5cf6"
COLOR_ACCENT_EMERALD = "#10b981"
COLOR_ACCENT_CYAN    = "#06b6d4"
COLOR_ACCENT_ROSE    = "#f43f5e"

COLOR_TEXT_MAIN      = "#e7ecf3"
COLOR_TEXT_MUTED     = "#6b7785"
COLOR_TEXT_SUB       = "#9fb0c3"


# ─── Dark Palette Roles ──────────────────────────────────────────────
DARK_PALETTE = {
    QPalette.ColorRole.Window:          COLOR_BG_DARK,
    QPalette.ColorRole.WindowText:      COLOR_TEXT_MAIN,
    QPalette.ColorRole.Base:            COLOR_BG_CARD,
    QPalette.ColorRole.AlternateBase:   COLOR_BG_HEADER,
    QPalette.ColorRole.Text:            "#dbe3ec",
    QPalette.ColorRole.Button:          COLOR_BG_CARD_HOVER,
    QPalette.ColorRole.ButtonText:      COLOR_TEXT_MAIN,
    QPalette.ColorRole.ToolTipBase:     COLOR_BG_CARD_HOVER,
    QPalette.ColorRole.ToolTipText:     COLOR_TEXT_MAIN,
    QPalette.ColorRole.Highlight:       DEFAULT_PRIMARY,
    QPalette.ColorRole.HighlightedText: "#ffffff",
}

# ─── Accent Helpers ──────────────────────────────────────────────────

def set_primary(value=None):
    """Remember the accent color used across stylesheets and icon tints."""
    global _active_primary
    text = str(value or _active_primary).strip()
    if text and not text.startswith("#"):
        text = f"#{text}"
    color = QColor(text)
    if not color.isValid():
        color = QColor(DEFAULT_PRIMARY)
    _active_primary = color.name(QColor.NameFormat.HexRgb)
    return _active_primary


def primary_color():
    return _active_primary


def accent_rgba(hex_color=None, alpha=SELECTION_ALPHA):
    """CSS rgba() for a translucent accent wash — used in stylesheets."""
    color = QColor(hex_color or primary_color())
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {int(alpha)})"


def accent_wash(alpha=SELECTION_ALPHA):
    """QColor accent at selection opacity, for custom painters."""
    color = QColor(primary_color())
    color.setAlpha(int(alpha))
    return color


def build_palette(dark=True, primary=None):
    """Build a QPalette for the dark theme with accent color integration."""
    result = QPalette()
    accent = QColor(set_primary(primary) if primary else primary_color())

    if dark:
        for role, hex_val in DARK_PALETTE.items():
            result.setColor(role, QColor(hex_val))
        result.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(COLOR_TEXT_MUTED)
        )
        result.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(COLOR_TEXT_MUTED)
        )

    wash = QColor(accent)
    wash.setAlpha(SELECTION_ALPHA)
    result.setColor(QPalette.ColorRole.Highlight, wash)
    result.setColor(
        QPalette.ColorRole.HighlightedText,
        QColor(COLOR_TEXT_MAIN if dark else "#1c1e21"),
    )
    return result
