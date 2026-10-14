"""QSS section: Progress, sliders, scrollbars, and drop zone."""
from __future__ import annotations

from jela.constants.theme_constants import (
    COLOR_BG_DARK, COLOR_BG_SIDEBAR, COLOR_BG_HEADER, COLOR_BG_TITLEBAR,
    COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_INPUT, COLOR_BG_STATUSBAR,
    COLOR_BORDER, COLOR_PRIMARY, COLOR_PRIMARY_HOVER,
    COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
    COLOR_ACCENT_EMERALD, COLOR_ACCENT_PURPLE,
)


def widgets_qss(accent: str, wash: str) -> str:
    return f"""
/* ─── Progress Bar ───────────────────────────────────────────────── */
QProgressBar {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    background-color: #121821;
    text-align: center;
    color: {COLOR_TEXT_MAIN};
    font-weight: 600;
    font-size: 11px;
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 2px;
}}

/* ─── Sliders ────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    border: 1px solid {COLOR_BORDER};
    height: 4px;
    background: #121821;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {COLOR_ACCENT_PURPLE};
    border: 2px solid #ffffff;
    width: 10px;
    height: 10px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: 5px;
}}

/* ─── Scroll Bars ────────────────────────────────────────────────── */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 8px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: #2b3a4d;
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3d4f66;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 8px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: #2b3a4d;
    min-width: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #3d4f66;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ─── Drop Zone ──────────────────────────────────────────────────── */
#drop_zone {{
    background-color: rgba(21, 29, 40, 0.55);
    border: 1.5px dashed #2b3a4d;
    border-radius: 12px;
    padding: 28px 20px;
    min-height: 140px;
}}
#drop_zone:hover {{
    background-color: {wash};
    border: 1.5px dashed {accent};
}}
#drop_zone[loaded="true"] {{
    background-color: rgba(16, 185, 129, 0.08);
    border: 1.5px solid rgba(16, 185, 129, 0.35);
}}
#drop_zone_icon {{
    color: {COLOR_TEXT_SUB};
}}
#drop_zone_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 13px;
    font-weight: 700;
}}
#drop_zone_sub {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
}}
#drop_zone_file {{
    color: #34d399;
    font-size: 11px;
    font-weight: 700;
}}

/* ─── Badges ─────────────────────────────────────────────────────── */
QLabel[class="badge"] {{
    background-color: {wash};
    color: {accent};
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel[class="badge_success"] {{
    background-color: rgba(16, 185, 129, 0.12);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 700;
}}

/* ─── Tab Bar ────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    background-color: {COLOR_BG_DARK};
}}
QTabBar::tab {{
    background: transparent;
    color: {COLOR_TEXT_SUB};
    padding: 7px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{ background: rgba(255, 255, 255, 0.05); }}
QTabBar::tab:selected {{
    background: {wash};
    color: {COLOR_TEXT_MAIN};
    border-bottom: 2px solid {accent};
}}

/* ─── Back to Launcher Buttons ───────────────────────────────────── */
#header_back_btn, #btn_back_launcher {{
    background-color: #17202d;
    color: #cbd5e1;
    border: 1px solid #2b3a4d;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 11px;
    font-weight: 700;
    min-height: 32px;
}}
#header_back_btn:hover, #btn_back_launcher:hover {{
    background-color: #243044;
    color: #ffffff;
    border-color: {accent};
}}
#header_back_btn:focus, #btn_back_launcher:focus {{
    border-color: {accent};
}}

"""
