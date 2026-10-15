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
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    background: {COLOR_BG_CARD};
    top: -1px;
    padding: 0;
}}
QTabWidget#settingsTabs QTabBar::tab {{
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    padding: 6px 12px;
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
    font-size: 12.5px;
    font-weight: 700;
}}
QLabel#settings_section_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10.5px;
}}
QLabel#settings_field_label {{
    color: {COLOR_TEXT_SUB};
    font-size: 10.5px;
    font-weight: 600;
}}

QFrame#settings_divider {{
    background-color: {COLOR_BORDER};
    border: none;
    height: 1px;
    max-height: 1px;
    margin: 6px 0;
}}

QWidget#settings_section {{
    background: transparent;
    border: none;
}}

QFrame#settings_feature_row {{
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}}
QFrame#settings_feature_row:hover {{
    background: rgba(255, 255, 255, 0.03);
    border-radius: 4px;
}}

QLabel#settings_feature_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11.5px;
    font-weight: 700;
}}
QLabel#settings_feature_meta {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10.5px;
}}
QLabel#settings_status_pill {{
    border-radius: 6px;
    padding: 2px 7px;
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
    padding: 1px 5px;
    font-size: 9.5px;
    font-weight: 700;
}}

QPushButton#settings_copy_btn {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    color: {COLOR_TEXT_SUB};
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
    height: 20px;
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

QTableWidget#settings_models_table {{
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: transparent;
}}
QTableWidget#settings_models_table::item {{
    padding: 2px 6px;
    font-size: 11.5px;
    color: {COLOR_TEXT_MAIN};
}}
QTableWidget#settings_models_table QHeaderView::section {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER};
    padding: 4px 6px;
    font-size: 10.5px;
    font-weight: 600;
}}
QTableWidget#settings_models_table QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px 0;
}}
QTableWidget#settings_models_table QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QTableWidget#settings_models_table QScrollBar::handle:vertical:hover {{
    background: {COLOR_TEXT_MUTED};
}}
QTableWidget#settings_models_table QScrollBar::add-line:vertical,
QTableWidget#settings_models_table QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""
