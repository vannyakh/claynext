"""QSS section: Project Home (Premiere-style start screen)."""
from __future__ import annotations

from jela.constants.theme_constants import (
    COLOR_ACCENT_EMERALD,
    COLOR_ACCENT_PURPLE,
    COLOR_BG_CARD,
    COLOR_BG_CARD_HOVER,
    COLOR_BG_DARK,
    COLOR_BG_INPUT,
    COLOR_BG_SIDEBAR,
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SUB,
)


def home_qss(accent: str, wash: str) -> str:
    return f"""
/* ─── Project Home ───────────────────────────────────────────────── */
QFrame#home_body {{
    background: {COLOR_BG_DARK};
}}
QFrame#home_rail {{
    background: {COLOR_BG_SIDEBAR};
    border-right: 1px solid {COLOR_BORDER};
}}
QLabel#home_brand {{
    color: {COLOR_TEXT_MAIN};
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -0.3px;
    background: transparent;
}}
QLabel#home_kicker {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
    background: transparent;
}}
QLabel#home_section {{
    color: {COLOR_TEXT_MAIN};
    font-size: 17px;
    font-weight: 700;
    background: transparent;
    padding-top: 4px;
    margin-top: 4px;
}}
QLabel#home_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    background: transparent;
}}
QLabel#home_empty {{
    color: {COLOR_TEXT_MUTED};
    font-size: 13px;
    background: {COLOR_BG_CARD};
    border: 1px dashed {COLOR_BORDER};
    border-radius: 12px;
    padding: 28px;
}}

QLineEdit#home_search {{
    background: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 0 12px;
    font-size: 12px;
    min-height: 32px;
    max-height: 32px;
    selection-background-color: {accent};
}}
QLineEdit#home_search:focus {{
    border-color: {accent};
}}

/* Compact list/grid mode group — width fixed in widget code (70×34) */
QFrame#home_mode_wrap {{
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QToolButton#home_mode_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    margin: 0px;
    padding: 0px;
}}
QToolButton#home_mode_btn:hover {{
    background: {COLOR_BG_CARD_HOVER};
}}
QToolButton#home_mode_btn:checked {{
    background: {wash};
    border: 1px solid {accent};
}}
QToolButton#home_mode_btn:checked:hover {{
    background: {wash};
    border: 1px solid {accent};
}}
QToolButton#home_mode_btn:pressed {{
    background: {COLOR_BG_CARD_HOVER};
}}
QToolButton#home_mode_btn:focus {{
    outline: none;
}}

QPushButton#home_action {{
    background: {COLOR_BG_CARD};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 9px;
    padding: 0 14px;
    text-align: left;
    font-size: 12px;
    font-weight: 600;
    min-height: 40px;
}}
QPushButton#home_action:hover {{
    background: {COLOR_BG_CARD_HOVER};
    border-color: {accent};
}}
QPushButton#home_primary {{
    background: {accent};
    color: #ffffff;
    border: none;
    border-radius: 9px;
    padding: 0 14px;
    text-align: left;
    font-size: 12px;
    font-weight: 700;
    min-height: 40px;
}}
QPushButton#home_primary:hover {{
    background: {COLOR_PRIMARY};
}}

QLabel#home_card_thumb_list {{
    background: #1a222e;
    border: 1px solid {COLOR_BORDER};
    border-radius: 9px;
}}
QLabel#home_card_thumb_grid {{
    background: #1a222e;
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QLabel#home_card_name {{
    color: {COLOR_TEXT_MAIN};
    font-size: 13px;
    font-weight: 700;
    background: transparent;
    margin-top: 4px;
    padding-top: 2px;
}}
QLabel#home_card_name_grid {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 700;
    background: transparent;
    margin-top: 6px;
    padding-top: 2px;
}}
QLabel#home_card_meta {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    background: transparent;
}}

QPushButton#home_card_open {{
    background: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 7px;
    padding: 0 12px;
    font-size: 11px;
    font-weight: 600;
    min-height: 28px;
    max-height: 28px;
}}
QPushButton#home_card_open:hover {{
    background: {accent};
    color: #ffffff;
    border-color: {accent};
}}

QListWidget#home_recent {{
    background: transparent;
    border: none;
    outline: none;
    padding: 2px;
    show-decoration-selected: 0;
    selection-background-color: transparent;
    selection-color: {COLOR_TEXT_MAIN};
}}
QListWidget#home_recent::item {{
    background: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    margin: 0px;
    padding: 0px;
    color: {COLOR_TEXT_SUB};
    outline: none;
}}
QListWidget#home_recent::item:hover {{
    background: {COLOR_BG_CARD_HOVER};
    border: 1px solid #3d4f66;
}}
QListWidget#home_recent::item:selected,
QListWidget#home_recent::item:selected:hover,
QListWidget#home_recent::item:selected:active,
QListWidget#home_recent::item:focus {{
    background: {COLOR_BG_CARD_HOVER};
    border: 1px solid #4b5c73;
    outline: none;
}}

/* ─── New Project dialog ─────────────────────────────────────────── */
QDialog#new_project_dialog {{
    background: {COLOR_BG_DARK};
}}
QFrame#new_project_header {{
    background: {COLOR_BG_SIDEBAR};
    border-bottom: 1px solid {COLOR_BORDER};
}}
QLabel#new_project_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 19px;
    font-weight: 800;
    letter-spacing: -0.3px;
    background: transparent;
}}
QLabel#new_project_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
    background: transparent;
}}
QFrame#new_project_drop_zone {{
    background: {COLOR_BG_INPUT};
    border: 1.5px dashed {COLOR_BORDER};
    border-radius: 8px;
}}
QFrame#new_project_drop_zone:hover {{
    background: {COLOR_BG_CARD_HOVER};
    border-color: {accent};
}}
QFrame#new_project_media_card {{
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QLabel#new_project_kicker {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    background: transparent;
}}
QLabel#new_project_field_lbl {{
    color: {COLOR_TEXT_SUB};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}
QLabel#new_project_path_preview {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
    background: transparent;
}}
QLabel#new_project_summary_val {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}}
QLabel#new_project_pill_ready {{
    color: {COLOR_ACCENT_EMERALD};
    background: #064e3b33;
    border: 1px solid #05966955;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#new_project_pill_warn {{
    color: #f59e0b;
    background: #78350f33;
    border: 1px solid #d9770655;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#new_project_pill_error {{
    color: #ef4444;
    background: #7f1d1d33;
    border: 1px solid #dc262655;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QToolButton#new_project_template {{
    background: transparent;
    color: {COLOR_TEXT_SUB};
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 600;
    text-align: left;
}}
QToolButton#new_project_template:hover {{
    background: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
}}
QToolButton#new_project_template:checked {{
    background: {wash};
    color: {COLOR_TEXT_MAIN};
}}
"""
