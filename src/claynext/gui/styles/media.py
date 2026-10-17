"""QSS section: Media preview and library."""
from __future__ import annotations

from claynext.constants.theme_constants import (
    COLOR_BG_DARK, COLOR_BG_SIDEBAR, COLOR_BG_HEADER, COLOR_BG_TITLEBAR,
    COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_INPUT, COLOR_BG_STATUSBAR,
    COLOR_BORDER, COLOR_PRIMARY, COLOR_PRIMARY_HOVER,
    COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
    COLOR_ACCENT_EMERALD, COLOR_ACCENT_PURPLE,
)


def media_qss(accent: str, wash: str) -> str:
    return f"""
/* ─── Media Preview & Playback Panel (Dedicated Styling) ─────────────── */
#media_preview {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
}}
#media_playback {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-radius: 0;
}}
#media_stage {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
}}
#media_video, #media_poster {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
}}
#media_placeholder {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
    font-weight: 600;
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
}}
#media_controls {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-top: 1px solid {COLOR_BORDER}66;
    border-radius: 0;
}}
#media_time_lbl {{
    color: {COLOR_TEXT_SUB};
    font-size: 11px;
    font-weight: 600;
}}
#media_time_now {{
    color: {accent};
    font-size: 11px;
    font-weight: 700;
}}
#media_time_badge {{
    background-color: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 2px 7px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 11px;
    font-weight: 600;
    color: {COLOR_TEXT_MAIN};
    min-height: 20px;
    max-height: 22px;
}}
#media_zoom_lbl {{
    color: {COLOR_TEXT_SUB};
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 6px;
    background: transparent;
}}
#media_zoom_lbl[zoomed="true"] {{
    color: {accent};
    background: {COLOR_BG_CARD_HOVER};
}}
#media_zoom_lbl:hover {{
    color: {COLOR_TEXT_MAIN};
    background: {COLOR_BG_CARD_HOVER};
}}
#media_ctrl_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
}}
#media_ctrl_btn:hover {{
    background: {COLOR_BG_CARD_HOVER};
}}
#media_ctrl_btn:disabled {{
    background: transparent;
}}
#media_tool_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: {COLOR_TEXT_SUB};
    font-size: 11px;
    font-weight: 700;
    padding: 0;
}}
#media_tool_btn:hover {{
    background: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
}}
#media_tool_btn:checked {{
    background: {COLOR_BG_CARD_HOVER};
    border: 1px solid {COLOR_BORDER};
    color: {accent};
}}
#media_tool_btn:disabled {{
    color: {COLOR_TEXT_MUTED};
}}
#media_play_btn {{
    background: {accent};
    border: 1px solid {accent};
    border-radius: 6px;
}}
#media_play_btn:hover {{
    background: {COLOR_PRIMARY_HOVER};
    border-color: {COLOR_PRIMARY_HOVER};
}}
#media_play_btn:disabled {{
    background: #2a3350;
    border-color: #2a3350;
}}
QSlider#media_seek::groove:horizontal {{
    border: none;
    height: 4px;
    background: #1e2a3a;
    border-radius: 2px;
}}
QSlider#media_seek::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}
QSlider#media_seek::add-page:horizontal {{
    background: #1e2a3a;
    border-radius: 2px;
}}
QSlider#media_seek::handle:horizontal {{
    background: #ffffff;
    border: none;
    width: 10px;
    height: 10px;
    margin: -3px 0;
    border-radius: 5px;
}}
QSlider#media_seek::handle:horizontal:hover {{
    background: {accent};
}}

/* ─── Media Library (list / grid) ────────────────────────────────── */
#media_library {{
    background-color: {COLOR_BG_CARD};
    border: none;
}}
#media_lib_tools {{
    background-color: {COLOR_BG_CARD};
    border: none;
}}
#media_lib_count {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 700;
    min-width: 18px;
    padding: 0 2px;
}}
#media_lib_add_btn {{
    background: transparent;
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: 600;
    min-height: 22px;
    max-height: 22px;
}}
#media_lib_add_btn:hover {{
    background: rgba(255, 255, 255, 0.05);
    border-color: {COLOR_PRIMARY};
    color: #ffffff;
}}
#media_lib_add_btn:pressed {{
    background: rgba(99, 102, 241, 0.16);
}}
#media_lib_search {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 1px 8px;
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
    min-height: 22px;
    max-height: 22px;
}}
#media_lib_search:focus {{
    border-color: {COLOR_PRIMARY};
    background: rgba(255, 255, 255, 0.03);
}}
#media_lib_filter_chip {{
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 0px 8px;
    font-size: 10px;
    font-weight: 600;
    min-height: 18px;
    max-height: 18px;
}}
#media_lib_filter_chip:hover {{
    color: {COLOR_TEXT_MAIN};
    background: rgba(255, 255, 255, 0.04);
}}
#media_lib_filter_chip:checked {{
    background: transparent;
    color: #c4b5fd;
    border: 1px solid rgba(139, 92, 246, 0.55);
    font-weight: 700;
}}
#media_lib_browse_btn {{
    background: transparent;
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 2px 12px;
    font-size: 11px;
    font-weight: 600;
    min-height: 24px;
    max-height: 24px;
}}
#media_lib_browse_btn:hover {{
    border-color: {COLOR_PRIMARY};
    color: #ffffff;
    background: rgba(255, 255, 255, 0.04);
}}
#media_lib_detail_card {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
}}
#media_lib_footer_thumb {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
}}
#media_lib_footer_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
    font-weight: 600;
}}
#media_lib_footer_meta {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: 500;
}}
#media_lib_btn_localize {{
    background: transparent;
    color: #c4b5fd;
    border: 1px solid rgba(139, 92, 246, 0.55);
    border-radius: 5px;
    padding: 1px 10px;
    font-size: 11px;
    font-weight: 600;
    min-height: 22px;
    max-height: 22px;
}}
#media_lib_btn_localize:hover {{
    background: rgba(139, 92, 246, 0.14);
    border-color: {COLOR_PRIMARY};
    color: #ffffff;
}}
#media_lib_btn_localize:disabled {{
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    border: 1px solid {COLOR_BORDER};
}}
#media_lib_footer_progress {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10.5px;
    font-weight: 500;
    background: transparent;
    border: none;
    padding: 0 2px;
}}
#media_lib_footer_btn {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 2px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}}
#media_lib_footer_btn:hover {{
    background: rgba(255, 255, 255, 0.05);
    border-color: {COLOR_PRIMARY};
}}
#media_lib_icon_btn, #media_lib_menu_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 2px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}}
#media_lib_icon_btn:hover, #media_lib_menu_btn:hover {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid {COLOR_BORDER};
}}
#media_lib_icon_btn:checked {{
    background: transparent;
    border: 1px solid rgba(139, 92, 246, 0.55);
}}
#media_lib_menu_btn::menu-indicator,
#media_lib_icon_btn::menu-indicator {{
    image: none;
    width: 0;
    height: 0;
}}
#media_lib_menu, #timeline_context_menu {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 4px;
}}
#media_lib_menu::item, #timeline_context_menu::item {{
    padding: 5px 12px 5px 8px;
    border-radius: 6px;
    color: {COLOR_TEXT_MAIN};
    icon-size: 14px;
    font-size: 12px;
}}
#media_lib_menu::item:selected, #timeline_context_menu::item:selected {{
    background-color: {wash};
}}
#media_lib_menu::icon, #timeline_context_menu::icon {{
    padding-left: 4px;
}}
#timeline_context_menu::item:disabled {{
    color: {COLOR_TEXT_MUTED};
}}
#media_lib_empty_wrap {{
    background: transparent;
}}
#media_lib_empty {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
    font-weight: 600;
    padding: 0;
    background-color: transparent;
}}
#media_lib_empty_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    background: transparent;
}}
#media_lib_list, #media_lib_grid {{
    background-color: {COLOR_BG_CARD};
    alternate-background-color: {COLOR_BG_CARD};
    border: none;
    outline: none;
    color: {COLOR_TEXT_MAIN};
    selection-background-color: transparent;
    selection-color: {COLOR_TEXT_MAIN};
    padding: 0;
}}
#media_lib_list::item {{
    padding: 2px 6px;
    border: none;
    background: transparent;
}}
#media_lib_list::item:selected, #media_lib_grid::item:selected {{
    background-color: {wash};
    color: {COLOR_TEXT_MAIN};
    border: none;
}}
#media_lib_list::item:hover, #media_lib_grid::item:hover {{
    background-color: rgba(255, 255, 255, 0.04);
}}
#media_lib_list QHeaderView::section {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_MUTED};
    padding: 6px 4px;
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}66;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
#media_lib_check_wrap {{
    background: transparent;
}}
#media_lib_row_check {{
    background: transparent;
    spacing: 0;
    margin: 0;
    padding: 0;
}}
#media_lib_row_check::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid {COLOR_BORDER};
    background: {COLOR_BG_INPUT};
}}
#media_lib_row_check::indicator:hover {{
    border-color: {COLOR_PRIMARY};
}}
#media_lib_row_check::indicator:checked,
#media_lib_row_check::indicator:indeterminate {{
    border-color: {COLOR_PRIMARY};
    background: {COLOR_PRIMARY};
}}
#media_lib_grid::item {{
    padding: 6px 4px;
    border-radius: 8px;
    border: 1px solid transparent;
    background: #0f1622;
}}
#media_lib_grid::item:hover {{
    background-color: #162030;
    border: 1px solid {COLOR_BORDER};
}}
#media_lib_grid::item:selected {{
    background-color: rgba(99, 102, 241, 0.18);
    border: 1px solid {COLOR_PRIMARY};
    color: #ffffff;
}}

#asr_toolbar {{
    background: transparent;
    border: none;
}}


"""

