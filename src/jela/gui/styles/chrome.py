"""QSS section: Window chrome, menus, and global reset."""
from __future__ import annotations

from pathlib import Path

from jela.constants.theme_constants import (
    COLOR_BG_DARK, COLOR_BG_SIDEBAR, COLOR_BG_HEADER, COLOR_BG_TITLEBAR,
    COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_INPUT, COLOR_BG_STATUSBAR,
    COLOR_BORDER, COLOR_PRIMARY, COLOR_PRIMARY_HOVER,
    COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
    COLOR_ACCENT_EMERALD, COLOR_ACCENT_PURPLE,
)
from jela.core.icons import ICONS_DIR

_MENU_ARROW = Path(ICONS_DIR, "chevron-right.svg").as_posix()


def chrome_qss(accent: str, wash: str) -> str:
    return f"""
/* ─── Global Reset ───────────────────────────────────────────────── */
QMainWindow, QDialog {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_MAIN};
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 12px;
}}
QWidget {{ outline: none; }}

/* ─── Custom Title Bar ───────────────────────────────────────────── */
#custom_title_bar {{
    background-color: {COLOR_BG_TITLEBAR};
    border-bottom: 1px solid {COLOR_BORDER};
}}
#title_tool_name {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: -0.1px;
    padding-right: 2px;
}}
#title_settings_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
}}
#title_settings_btn:hover {{
    background: #1a2230;
    border: 1px solid #2b3a4d;
}}

QWidget#winControls QToolButton {{
    background: transparent;
    border: 0;
    border-radius: 0;
    padding: 3px 12px;
}}
QWidget#winControls QToolButton:hover {{ background: #243044; }}
QWidget#winControls QToolButton#winClose:hover {{ background: #e81123; }}

/* ─── Top Menu Bar & Context Menus ───────────────────────────────── */
QMenuBar, #titleMenuBar {{
    background-color: transparent;
    color: {COLOR_TEXT_SUB};
    border: none;
    font-size: 12px;
    font-weight: 500;
    spacing: 2px;
}}
QMenuBar::item, #titleMenuBar::item {{
    background: transparent;
    padding: 5px 11px;
    border-radius: 6px;
    margin: 4px 1px;
}}
QMenuBar::item:selected, QMenuBar::item:pressed,
#titleMenuBar::item:selected, #titleMenuBar::item:pressed {{
    background-color: #1e2a3a;
    color: #ffffff;
}}

QMenu {{
    background-color: #151d28;
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 6px 4px;
    font-size: 12px;
}}
QMenu::item {{
    padding: 6px 24px 6px 24px;
    border-radius: 5px;
    margin: 1px 4px;
}}
QMenu::indicator {{
    width: 14px;
    height: 14px;
    margin-left: 6px;
}}
QMenu::right-arrow, QMenu::right-arrow:selected {{
    image: url({_MENU_ARROW});
    width: 8px;
    height: 8px;
    margin-right: 8px;
}}
QMenu::item:selected {{
    background-color: {wash};
    color: {COLOR_TEXT_MAIN};
}}
QMenu::item:checked {{
    color: {accent};
    font-weight: 700;
}}
QMenu::separator {{
    height: 1px;
    background-color: {COLOR_BORDER};
    margin: 5px 10px;
}}
QMenu::shortcut {{
    color: {COLOR_TEXT_MUTED};
    padding-left: 24px;
}}
QMenu::item:selected QMenu::shortcut {{
    color: {COLOR_TEXT_SUB};
}}

"""
