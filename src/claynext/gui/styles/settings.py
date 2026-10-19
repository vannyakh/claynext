"""QSS for Settings dialog — Features cards, status pills, section panels."""
from __future__ import annotations

from pathlib import Path
from claynext.constants.theme_constants import (
    COLOR_BG_CARD,
    COLOR_BG_CARD_HOVER,
    COLOR_BG_DARK,
    COLOR_BG_INPUT,
    COLOR_BORDER,
    COLOR_BORDER_FOCUS,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SUB,
    COLOR_ACCENT_EMERALD,
    COLOR_ACCENT_CYAN,
)
from claynext.gui.icons import ICONS_DIR

_CHECK_ICON = Path(ICONS_DIR, "check_on.svg").as_posix()


def settings_qss(primary: str, wash: str) -> str:
    return f"""
QDialog {{
    background: {COLOR_BG_DARK};
}}
QDialog QPushButton#btn_secondary,
QDialog QPushButton#btn_primary {{
    min-height: 26px;
    padding: 0 14px;
    font-size: 11.5px;
    font-weight: 600;
}}
QTabWidget#settingsTabs QPushButton#btn_secondary,
QTabWidget#settingsTabs QPushButton#btn_primary {{
    min-height: 24px;
    padding: 0 8px;
    font-size: 11px;
}}
QTabWidget#settingsTabs::pane {{
    border: none;
    border-top: 1px solid {COLOR_BORDER}66;
    border-radius: 0;
    background: transparent;
    top: -1px;
    padding: 0;
    margin-top: 2px;
}}
QTabWidget#settingsTabs QTabBar::tab {{
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    padding: 7px 12px;
    margin-right: 2px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 11px;
    font-weight: 600;
}}
QTabWidget#settingsTabs QTabBar::tab:selected {{
    color: {COLOR_TEXT_MAIN};
    border-bottom: 2px solid {primary};
}}
QTabWidget#settingsTabs QTabBar::tab:hover:!selected {{
    color: {COLOR_TEXT_SUB};
}}

QTabWidget#settingsTabs QScrollArea,
QTabWidget#settingsTabs QScrollArea > QWidget,
QTabWidget#settingsTabs QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

QTabWidget#settingsTabs QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px 0;
}}
QTabWidget#settingsTabs QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QTabWidget#settingsTabs QScrollBar::handle:vertical:hover {{
    background: {COLOR_TEXT_MUTED};
}}
QTabWidget#settingsTabs QScrollBar::add-line:vertical,
QTabWidget#settingsTabs QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QTabWidget#settingsTabs QCheckBox {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
    spacing: 8px;
    background: transparent;
}}
QTabWidget#settingsTabs QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    background-color: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
}}
QTabWidget#settingsTabs QCheckBox::indicator:hover {{
    border-color: {primary};
    background-color: {COLOR_BG_CARD_HOVER};
}}
QTabWidget#settingsTabs QCheckBox::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
    image: url({_CHECK_ICON});
}}

QTabWidget#settingsTabs QLineEdit {{
    background: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    color: {COLOR_TEXT_MAIN};
    padding: 0 8px;
    font-size: 11px;
}}
QTabWidget#settingsTabs QLineEdit:focus {{
    border-color: {primary};
}}
QTabWidget#settingsTabs QComboBox {{
    background: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    color: {COLOR_TEXT_MAIN};
    padding: 0 8px;
    font-size: 11px;
}}
QTabWidget#settingsTabs QComboBox:hover {{
    border-color: {primary};
}}
QTabWidget#settingsTabs QSpinBox {{
    background: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    color: {COLOR_TEXT_MAIN};
    padding: 0 8px;
    font-size: 11px;
}}
QTabWidget#settingsTabs QSpinBox:focus {{
    border-color: {primary};
}}

QLabel#settings_section_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.2px;
    padding: 0;
    margin: 0;
}}
QLabel#settings_section_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10.5px;
    line-height: 1.35;
    padding: 0;
    margin: 0;
}}
QLabel#settings_field_label {{
    color: {COLOR_TEXT_SUB};
    font-size: 10.5px;
    font-weight: 600;
}}

QWidget#settings_divider_wrap {{
    background: transparent;
    border: none;
    min-height: 18px;
}}
QFrame#settings_divider {{
    background-color: {COLOR_BORDER}66;
    border: none;
    height: 1px;
    max-height: 1px;
    margin: 0;
}}

QWidget#settings_section {{
    background: transparent;
    border: none;
}}

QWidget#settings_feature_list {{
    background: transparent;
    border: none;
}}
QFrame#settings_feature_row {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}33;
}}
QFrame#settings_feature_row[last="true"] {{
    border-bottom: none;
}}
QFrame#settings_feature_row:hover {{
    background: rgba(255, 255, 255, 0.025);
}}

QLabel#settings_feature_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11.5px;
    font-weight: 650;
    min-width: 108px;
}}
QLabel#settings_feature_meta {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10.5px;
}}
QLabel#settings_feature_pct {{
    color: {primary};
    font-size: 11px;
    font-weight: 700;
    background: transparent;
}}
QLabel#settings_feature_active {{
    color: {COLOR_ACCENT_EMERALD};
    font-size: 10.5px;
    font-weight: 600;
}}
QLabel#settings_status_pill {{
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 9.5px;
    font-weight: 700;
}}
QLabel#settings_status_pill[tone="ready"] {{
    color: {COLOR_ACCENT_EMERALD};
    background: rgba(16, 185, 129, 0.14);
}}
QLabel#settings_status_pill[tone="missing"] {{
    color: {COLOR_TEXT_MUTED};
    background: rgba(107, 119, 133, 0.14);
}}
QLabel#settings_status_pill[tone="unsupported"] {{
    color: #f59e0b;
    background: rgba(245, 158, 11, 0.14);
}}
QLabel#settings_cat_pill {{
    color: {COLOR_ACCENT_CYAN};
    background: rgba(6, 182, 212, 0.12);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 9px;
    font-weight: 700;
}}

QPushButton#settings_copy_btn {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    color: {COLOR_TEXT_SUB};
    padding: 2px 10px;
    font-size: 10px;
    font-weight: 600;
    min-height: 22px;
}}
QPushButton#settings_copy_btn:hover {{
    border-color: {primary};
    color: {COLOR_TEXT_MAIN};
    background: {wash};
}}

QComboBox#settings_filter_combo {{
    min-width: 100px;
    height: 24px;
    font-size: 11px;
}}

QTableWidget#settings_models_table,
QTableWidget#settings_api_keys_table {{
    background: transparent;
    alternate-background-color: rgba(255, 255, 255, 0.02);
    border: none;
    border-top: 1px solid {COLOR_BORDER}44;
    border-bottom: 1px solid {COLOR_BORDER}33;
    border-radius: 0;
    gridline-color: transparent;
    selection-background-color: transparent;
    outline: none;
}}
QTableWidget#settings_models_table::item,
QTableWidget#settings_api_keys_table::item {{
    padding: 4px 8px;
    font-size: 11.5px;
    color: {COLOR_TEXT_MAIN};
    border: none;
}}
QTableWidget#settings_api_keys_table::item:selected {{
    background: {wash};
    color: {COLOR_TEXT_MAIN};
}}
QTableWidget#settings_models_table QHeaderView::section,
QTableWidget#settings_api_keys_table QHeaderView::section {{
    background-color: transparent;
    color: {COLOR_TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}55;
    padding: 6px 8px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}}
QLabel#settings_api_keys_empty {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11.5px;
    background: transparent;
    border: none;
}}
QTableWidget#settings_models_table QScrollBar:vertical,
QTableWidget#settings_api_keys_table QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px 0;
}}
QTableWidget#settings_models_table QScrollBar::handle:vertical,
QTableWidget#settings_api_keys_table QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QTableWidget#settings_models_table QScrollBar::handle:vertical:hover,
QTableWidget#settings_api_keys_table QScrollBar::handle:vertical:hover {{
    background: {COLOR_TEXT_MUTED};
}}
QTableWidget#settings_models_table QScrollBar::add-line:vertical,
QTableWidget#settings_models_table QScrollBar::sub-line:vertical,
QTableWidget#settings_api_keys_table QScrollBar::add-line:vertical,
QTableWidget#settings_api_keys_table QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ─── Project settings (card layout) ─────────────────────────────── */
QDialog#project_settings_dialog {{
    background: {COLOR_BG_DARK};
}}
QFrame#project_settings_card {{
    background: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER}66;
    border-radius: 10px;
}}
QPushButton#project_settings_browse {{
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    color: {COLOR_TEXT_SUB};
    font-size: 14px;
    font-weight: 700;
    padding: 0;
}}
QPushButton#project_settings_browse:hover {{
    border-color: {primary};
    color: {COLOR_TEXT_MAIN};
    background: {COLOR_BG_CARD_HOVER};
}}
QLineEdit#project_settings_readonly {{
    background: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_MUTED};
}}
QLabel#project_settings_warn {{
    color: #f59e0b;
    font-size: 10.5px;
    font-weight: 500;
    padding: 0 0 0 22px;
}}

/* ─── New Project (compact Settings-sized controls) ──────────────── */
QDialog#new_project_dialog {{
    background: {COLOR_BG_DARK};
}}
QDialog#new_project_dialog QPushButton#btn_secondary,
QDialog#new_project_dialog QPushButton#btn_primary {{
    min-height: 26px;
    max-height: 28px;
    padding: 0 12px;
    font-size: 11px;
    font-weight: 600;
}}
QDialog#new_project_dialog QLineEdit#home_search,
QDialog#new_project_dialog QComboBox#asr_option_combo {{
    min-height: 26px;
    max-height: 28px;
    padding: 2px 8px;
    font-size: 11.5px;
}}
QLabel#new_project_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#new_project_kicker {{
    color: {COLOR_TEXT_MUTED};
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QLabel#new_project_field_lbl {{
    color: {COLOR_TEXT_SUB};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#new_project_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10.5px;
}}
QLabel#new_project_summary_val {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11.5px;
    font-weight: 600;
}}
QLabel#new_project_path_preview {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10.5px;
}}
QToolButton#new_project_template {{
    background: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 0 8px;
    font-size: 12px;
    font-weight: 600;
    text-align: center;
}}
QToolButton#new_project_template:hover {{
    border-color: {primary};
}}
QToolButton#new_project_template:checked {{
    background: {wash};
    border-color: {primary};
    color: {COLOR_TEXT_MAIN};
}}
QFrame#new_project_drop_zone {{
    background: {COLOR_BG_INPUT};
    border: 1px dashed {COLOR_BORDER};
    border-radius: 8px;
}}
QLabel#new_project_pill_ready {{
    background: rgba(16, 185, 129, 0.12);
    color: {COLOR_ACCENT_EMERALD};
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 10.5px;
    font-weight: 650;
}}
QLabel#new_project_pill_warn {{
    background: rgba(245, 158, 11, 0.12);
    color: #f59e0b;
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 10.5px;
    font-weight: 650;
}}
QLabel#new_project_pill_error {{
    background: rgba(239, 68, 68, 0.12);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 10.5px;
    font-weight: 650;
}}
"""

