"""QSS section: Log, forms, tables, and buttons."""
from __future__ import annotations

from claynext.constants.theme_constants import (
    COLOR_BG_DARK, COLOR_BG_SIDEBAR, COLOR_BG_HEADER, COLOR_BG_TITLEBAR,
    COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_INPUT, COLOR_BG_STATUSBAR,
    COLOR_BORDER, COLOR_BORDER_FOCUS, COLOR_PRIMARY, COLOR_PRIMARY_HOVER,
    COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
    COLOR_ACCENT_EMERALD, COLOR_ACCENT_PURPLE, COLOR_ACCENT_ROSE,
)


def controls_qss(accent: str, wash: str) -> str:
    return f"""
/* ─── Log Panel ──────────────────────────────────────────────────── */
#log_panel {{
    background-color: {COLOR_BG_CARD};
}}
#log_toolbar {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}55;
}}
#log_toolbar_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 800;
}}
#log_toolbar_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
#log_action_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
}}
#log_action_btn:hover {{
    background: {COLOR_BG_CARD_HOVER};
    border: 1px solid {COLOR_BORDER};
}}
#log_action_clear:hover {{
    background: #3f1d1d;
    border: 1px solid #7f1d1d;
}}
#log_view {{
    background-color: {COLOR_BG_INPUT};
    border: none;
    border-radius: 0;
    color: {COLOR_TEXT_SUB};
    font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    padding: 8px;
}}


/* ─── Status Bar ─────────────────────────────────────────────────── */
#custom_status_bar {{
    background-color: {COLOR_BG_STATUSBAR};
    border-top: 1px solid {COLOR_BORDER};
}}
#status_elapsed {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
    font-weight: 600;
    font-family: "Menlo", "SF Mono", monospace;
    background: transparent;
    padding-right: 4px;
}}
#status_message {{
    color: {COLOR_TEXT_SUB};
    font-size: 11px;
    background: transparent;
}}
#status_tool {{
    color: {COLOR_PRIMARY};
    font-weight: 700;
    font-size: 11px;
    background: transparent;
}}
#status_version {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 3px;
    background: rgba(255,255,255,0.04);
}}
#status_progress {{
    border: none;
    border-radius: 3px;
    background-color: rgba(255,255,255,0.08);
    padding: 0px;
    margin: 0px;
    min-height: 4px;
    max-height: 8px;
    font-size: 1px;
}}
#status_progress::chunk {{
    background-color: {COLOR_ACCENT_PURPLE};
    border-radius: 3px;
    margin: 0px;
}}

/* ─── Export progress ────────────────────────────────────────────── */
#export_thumb {{
    background: transparent;
    border: none;
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
}}
#export_filename {{
    color: {COLOR_TEXT_MAIN};
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}
#export_status {{
    color: {COLOR_TEXT_SUB};
    font-size: 12px;
    background: transparent;
}}
#export_status[error="true"] {{
    color: {COLOR_ACCENT_ROSE};
}}
#export_percent {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}}
QDialog#exportDialog, QDialog#exportProgressDialog {{
    background: transparent;
}}
#export_shell {{
    background-color: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
}}
#export_title_bar {{
    background: transparent;
    border: none;
}}
#export_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 15px;
    font-weight: 600;
    background: transparent;
    padding: 0;
}}
#export_close {{
    background: transparent;
    border: none;
    border-radius: 6px;
}}
#export_close:hover {{
    background-color: rgba(244, 63, 94, 0.22);
}}
#export_preview_card {{
    background: transparent;
    border: none;
    border-radius: 0;
}}
QProgressBar#export_progress {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    background-color: rgba(255,255,255,0.05);
    min-height: 16px;
    max-height: 18px;
    padding: 0px;
    text-align: center;
}}
QProgressBar#export_progress::chunk {{
    background-color: {COLOR_ACCENT_PURPLE};
    border-radius: 4px;
    margin: 2px;
}}

/* ─── Cards ──────────────────────────────────────────────────────── */
QFrame[class="card"] {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    padding: 14px;
}}
QFrame[class="card"]:hover {{
    border: 1px solid #2b3a4d;
}}
QFrame[class="action_bar"] {{
    background-color: #121821;
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
}}

/* ─── Section Labels ─────────────────────────────────────────────── */
QLabel[class="section_title"] {{
    color: {COLOR_TEXT_MAIN};
    font-size: 13px;
    font-weight: 700;
}}
QLabel[class="label_muted"] {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
}}
QLabel[class="form_label"] {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 700;
}}
QLabel[class="field_hint"] {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 500;
}}

/* ─── Primary Buttons ────────────────────────────────────────────── */
QPushButton[class="btn_primary"], #btn_primary {{
    background-color: {COLOR_PRIMARY};
    color: #ffffff;
    font-weight: 600;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 12px;
    min-height: 32px;
}}
QPushButton[class="btn_primary"]:hover, #btn_primary:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
}}
QPushButton[class="btn_primary"]:pressed, #btn_primary:pressed {{
    background-color: #4338ca;
}}
QPushButton[class="btn_primary"]:disabled, #btn_primary:disabled {{
    background-color: #2a3350;
    color: #8b93a7;
}}

QPushButton[class="btn_secondary"], #btn_secondary {{
    background-color: #1a2230;
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 600;
    min-height: 32px;
}}
QPushButton[class="btn_secondary"]:hover, #btn_secondary:hover {{
    background-color: #243044;
    color: #ffffff;
    border-color: #3d4f66;
}}
QPushButton[class="btn_secondary"]:disabled, #btn_secondary:disabled {{
    color: #6b7785;
    border-color: #1e2a3a;
}}

QPushButton[class="btn_accent"], #btn_accent {{
    background-color: {COLOR_ACCENT_EMERALD};
    color: #ffffff;
    font-weight: 600;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    min-height: 32px;
}}
QPushButton[class="btn_accent"]:hover, #btn_accent:hover {{
    background-color: #059669;
}}
QPushButton[class="btn_accent"]:disabled, #btn_accent:disabled {{
    background-color: #1f3d34;
    color: #8b93a7;
}}

/* ─── Input Controls ─────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    color: {COLOR_TEXT_MAIN};
    padding: 6px 10px;
    min-height: 22px;
}}
QLineEdit:hover, QTextEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border: 1px solid {COLOR_BORDER};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    selection-background-color: {wash};
    selection-color: {COLOR_TEXT_MAIN};
    color: {COLOR_TEXT_MAIN};
    padding: 4px;
    outline: 0;
}}

/* ─── Tables ─────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {COLOR_BG_CARD};
    alternate-background-color: {COLOR_BG_SIDEBAR};
    border: 1px solid {COLOR_BORDER}66;
    border-radius: 6px;
    gridline-color: transparent;
    color: {COLOR_TEXT_MAIN};
    selection-background-color: {wash};
    selection-color: {COLOR_TEXT_MAIN};
}}
QTableWidget::item {{
    padding: 6px 10px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {wash};
    color: #ffffff;
}}
QHeaderView::section {{
    background-color: {COLOR_BG_SIDEBAR};
    color: {COLOR_TEXT_SUB};
    padding: 7px 10px;
    border: 0;
    border-right: none;
    border-bottom: 1px solid {COLOR_BORDER}44;
    font-weight: 700;
    font-size: 11px;
}}

/* Transcript / script filter strip sits on panel body */
#transcript_tools {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}44;
    border-top-left-radius: 0;
    border-top-right-radius: 0;
}}
#transcript_panel_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 13px;
    font-weight: 400;
    background: transparent;
    border: none;
    padding: 0;
}}
#transcript_count {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 400;
    min-width: 0;
    max-width: 160px;
    padding: 0;
    margin: 0;
    background: transparent;
    border: none;
}}
/* Shared search / select — size property: sm=24 · md=30 · lg=34 */
QLineEdit#claynext_search, QLineEdit#transcript_search {{
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 0 10px;
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    max-width: none;
}}
QLineEdit#claynext_search[size="sm"], QLineEdit#transcript_search[size="sm"] {{
    border-radius: 6px;
    padding: 0 8px;
    font-size: 11px;
}}
QLineEdit#claynext_search[size="lg"], QLineEdit#transcript_search[size="lg"] {{
    border-radius: 9px;
    padding: 0 12px;
    font-size: 13px;
}}
QLineEdit#claynext_search:focus, QLineEdit#transcript_search:focus {{
    border-color: {accent}88;
}}
QComboBox#claynext_select, QComboBox#transcript_speaker_filter {{
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 0 6px 0 8px;
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
}}
QComboBox#claynext_select[size="md"], QComboBox#transcript_speaker_filter[size="md"] {{
    border-radius: 8px;
    font-size: 12px;
}}
QComboBox#claynext_select[size="lg"], QComboBox#transcript_speaker_filter[size="lg"] {{
    border-radius: 9px;
    font-size: 13px;
}}
QComboBox#claynext_select:hover, QComboBox#transcript_speaker_filter:hover {{
    border-color: {COLOR_BORDER_FOCUS};
}}
QComboBox#claynext_select::drop-down, QComboBox#transcript_speaker_filter::drop-down {{
    width: 20px;
    border: none;
}}
QComboBox#claynext_select::down-arrow, QComboBox#transcript_speaker_filter::down-arrow {{
    width: 10px;
    height: 10px;
}}
/* Script toolbar selects — no chevron; whole control opens the menu */
QComboBox#script_character_filter,
QComboBox#script_view_filter {{
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 0 10px 0 8px;
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
}}
QComboBox#script_character_filter:hover,
QComboBox#script_view_filter:hover {{
    border-color: {COLOR_BORDER_FOCUS};
}}
QComboBox#script_character_filter::drop-down,
QComboBox#script_view_filter::drop-down {{
    width: 0;
    border: none;
}}
QComboBox#script_character_filter::down-arrow,
QComboBox#script_view_filter::down-arrow {{
    image: none;
    width: 0;
    height: 0;
}}
#transcript_dur_spin {{
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 2px 4px;
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    min-height: 26px;
}}
#transcript_dur_sep {{
    color: {COLOR_TEXT_MUTED};
    background: transparent;
    border: none;
    padding: 0 2px;
}}
#transcript_stack {{
    background: transparent;
    border: none;
}}
#transcript_empty {{
    background: transparent;
}}
#transcript_empty_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 14px;
    font-weight: 700;
    background: transparent;
    border: none;
    padding: 0 8px;
}}
#transcript_empty_title[error="true"] {{
    color: #f87171;
}}
#transcript_empty_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11.5px;
    font-weight: 500;
    background: transparent;
    border: none;
    padding: 0 12px;
}}
#transcript_empty_hint[error="true"] {{
    color: #fca5a5;
}}
QPushButton#transcript_empty_btn,
QPushButton#transcript_empty_btn_primary {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
    font-weight: 600;
    padding: 0 10px;
    min-height: 24px;
    max-height: 24px;
}}
QPushButton#transcript_empty_btn:hover {{
    border-color: {COLOR_BORDER_FOCUS};
    background: rgba(255, 255, 255, 0.04);
}}
QPushButton#transcript_empty_btn_primary {{
    background: {wash};
    border-color: {accent}66;
}}
QPushButton#transcript_empty_btn_primary:hover {{
    border-color: {accent};
}}
#transcript_table {{
    background-color: {COLOR_BG_CARD};
    alternate-background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-radius: 0;
    outline: none;
}}
#transcript_table::item {{
    padding: 6px 10px;
    border: none;
}}
#transcript_table::item:selected {{
    background-color: {wash};
    color: {COLOR_TEXT_MAIN};
    border: none;
}}
#transcript_table::item:hover {{
    background-color: rgba(255, 255, 255, 0.03);
}}
#transcript_table QHeaderView::section {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_MUTED};
    padding: 7px 10px;
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}66;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-transform: uppercase;
}}

/* ASR options / controls — flat inside panel card */
#asr_field_label {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 400;
    padding-top: 2px;
}}
#asr_option_combo {{
    min-height: 28px;
}}
#asr_export_btn {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 700;
    min-height: 28px;
}}
#asr_export_btn:hover {{
    background-color: {COLOR_BG_HEADER};
    border-color: {COLOR_BORDER};
}}
#asr_export_btn:disabled {{
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER}66;
}}
#ui_spinner {{
    background: transparent;
    border: none;
}}

"""

