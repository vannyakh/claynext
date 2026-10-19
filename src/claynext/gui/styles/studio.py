"""QSS section: Dubbing shelf, timeline, and inspector."""
from __future__ import annotations

from pathlib import Path

from claynext.constants.theme_constants import (
    COLOR_BG_DARK, COLOR_BG_SIDEBAR, COLOR_BG_HEADER, COLOR_BG_TITLEBAR,
    COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_INPUT, COLOR_BG_SEGMENT,
    COLOR_BG_STATUSBAR,
    COLOR_BORDER, COLOR_BORDER_FOCUS, COLOR_PRIMARY, COLOR_PRIMARY_HOVER,
    COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
    COLOR_ACCENT_EMERALD, COLOR_ACCENT_PURPLE, COLOR_ACCENT_ROSE,
)
from claynext.gui.icons import ICONS_DIR

_CHECK_ICON = Path(ICONS_DIR, "check_on.svg").as_posix()
_DASH_ICON = Path(ICONS_DIR, "dash.svg").as_posix()


def studio_qss(accent: str, wash: str) -> str:
    return f"""
/* ─── Dub preview editor ─────────────────────────────────────────── */
#dub_config_panel, #properties_panel {{
    background-color: {COLOR_BG_CARD};
    border: none;
}}
#dub_shelf {{
    min-width: 160px;
    background-color: {COLOR_BG_CARD};
}}
#dub_shelf_stack {{
    min-width: 0;
    background-color: {COLOR_BG_CARD};
}}
#dub_shelf_stack > QWidget {{
    min-width: 0;
    background-color: {COLOR_BG_CARD};
}}
#prop_hero {{
    color: {COLOR_TEXT_MAIN};
    font-size: 22px;
    font-weight: 400;
    letter-spacing: 0.5px;
    padding-top: 4px;
}}
#prop_hero_sub {{
    color: {COLOR_TEXT_MUTED};
    font-size: 13px;
    font-weight: 400;
}}
#prop_details_title {{
    color: {COLOR_PRIMARY};
    font-size: 13px;
    font-weight: 400;
    padding: 2px 0 8px 0;
}}
#prop_divider {{
    color: {COLOR_BORDER}66;
    margin: 8px 0;
}}
#prop_modify_btn {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 600;
    min-height: 26px;
}}
#prop_modify_btn:hover {{
    background-color: {COLOR_BG_HEADER};
    border-color: {COLOR_PRIMARY};
}}
#prop_warn {{
    color: #facc15;
    font-size: 11px;
}}
#prop_key {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 400;
    min-width: 56px;
}}
#prop_val {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 400;
}}

#preview_editor, #preview_stage_wrap {{
    background-color: {COLOR_BG_CARD};
    border: none;
}}
#overlay_canvas {{
    background: transparent;
}}
#overlay_tools {{
    background-color: {COLOR_BG_SIDEBAR};
    border-bottom: 1px solid {COLOR_BORDER}44;
}}
#overlay_inspector, #track_props_page, #dub_props_scroll, #dub_props_scroll_body {{
    background-color: {COLOR_BG_CARD};
    border: none;
}}
#dub_props_header_card {{
    background-color: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
}}
#dub_danger_btn {{
    background-color: rgba(239, 68, 68, 0.12);
    color: #f87171;
    font-size: 11px;
    font-weight: 600;
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 28px;
}}
#dub_danger_btn:hover {{
    background-color: rgba(239, 68, 68, 0.22);
    border-color: #ef4444;
    color: #fca5a5;
}}
#dub_danger_btn:pressed {{
    background-color: rgba(239, 68, 68, 0.32);
}}
#dub_shelf_rail {{
    background-color: {COLOR_BG_SIDEBAR};
    border-right: 1px solid {COLOR_BORDER}44;
    padding-top: 2px;
}}
#dub_shelf_tab {{
    background-color: transparent;
    border: none;
    border-radius: 8px;
    margin: 0;
}}
#dub_shelf_tab:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
}}
#dub_shelf_tab:checked {{
    background-color: {COLOR_BG_CARD_HOVER};
}}
#text_styles_panel, #text_styles_body {{
    background-color: {COLOR_BG_CARD};
    border: none;
}}
QPushButton#text_cat_pill {{
    background-color: #0d1420;
    color: #94a3b8;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 3px 14px;
    min-height: 22px;
    max-height: 24px;
    font-size: 11px;
    font-weight: 500;
    outline: none;
}}
QPushButton#text_cat_pill:hover {{
    background-color: #172234;
    border-color: #334155;
    color: #e2e8f0;
}}
QPushButton#text_cat_pill:checked {{
    background-color: rgba(99, 102, 241, 0.22);
    border: 1px solid {COLOR_PRIMARY};
    color: #ffffff;
    font-weight: 600;
}}
#text_style_list {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
    outline: none;
    padding: 2px 0 0 2px;
}}
#text_style_list::item {{
    color: {COLOR_TEXT_SUB};
    font-size: 11px;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 3px 2px;
    background: transparent;
}}
#text_style_list::item:hover {{
    background-color: rgba(255, 255, 255, 0.04);
    border-color: {COLOR_BORDER};
    color: {COLOR_TEXT_MAIN};
}}
#text_style_list::item:selected {{
    background-color: rgba(99, 102, 241, 0.15);
    border: 1px solid {COLOR_PRIMARY};
    color: {COLOR_TEXT_MAIN};
}}
#dub_center_split::handle {{
    height: 4px;
    background: {COLOR_BG_CARD_HOVER};
}}
#dub_center_split::handle:hover {{
    background: {COLOR_PRIMARY};
}}

/* ─── Dub timeline ───────────────────────────────────────────────── */
#timeline_panel {{
    background-color: {COLOR_BG_CARD};
    border: none;
}}
#timeline_tools {{
    background-color: {COLOR_BG_SIDEBAR};
    border-bottom: 1px solid {COLOR_BORDER}44;
    min-height: 32px;
    max-height: 36px;
}}
#sequence_bar {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
}}
#sequence_bar[flow="row"] {{
    border-bottom: 1px solid {COLOR_BORDER};
}}
#sequence_scroll, #sequence_host {{
    background: transparent;
    border: none;
}}
#sequence_bar[flow="column"] #sequence_scroll {{
    background-color: {COLOR_BG_SIDEBAR};
}}
QPushButton#sequence_chip {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_SUB};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 2px 12px;
    font-size: 11px;
    font-weight: 500;
    min-height: 22px;
    max-height: 26px;
    text-align: left;
}}
QPushButton#sequence_chip:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
}}
QPushButton#sequence_chip:checked {{
    background-color: {wash};
    border-color: {accent};
    color: {COLOR_TEXT_MAIN};
}}
QPushButton#sequence_chip[drop="true"] {{
    border-style: dashed;
    border-color: {accent};
}}
#sequence_bar[flow="row"] QPushButton#sequence_chip {{
    min-height: 26px;
    max-height: 26px;
    padding: 0 12px;
    margin: 0;
    outline: none;
}}
#sequence_bar[flow="column"] QPushButton#sequence_chip {{
    min-height: 32px;
    max-height: 32px;
    padding: 0 12px;
    margin: 0;
    outline: none;
}}
#timeline_meta {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 400;
}}
#timeline_timecode_badge, #media_time_badge {{
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
    opacity: 0.4;
}}
#media_ctrl_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
}}
#media_ctrl_btn:hover {{
    background: {COLOR_BG_CARD_HOVER};
    border-color: {COLOR_BORDER};
}}
#media_ctrl_btn:disabled {{
    background: transparent;
    opacity: 0.35;
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
    border-color: {COLOR_BORDER};
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
#media_zoom_lbl {{
    color: {COLOR_TEXT_SUB};
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    background: transparent;
}}
#media_zoom_lbl[zoomed="true"] {{
    color: {accent};
    background: {COLOR_BG_CARD_HOVER};
    border: 1px solid {COLOR_BORDER};
}}
#media_zoom_lbl:hover {{
    color: {COLOR_TEXT_MAIN};
    background: {COLOR_BG_CARD_HOVER};
}}
#timeline_tool_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: {COLOR_TEXT_SUB};
    font-size: 10px;
    font-weight: 400;
    padding: 0;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
}}
#timeline_tool_btn:hover {{
    background: {COLOR_BG_CARD_HOVER};
    border-color: {COLOR_BORDER};
}}
#timeline_tool_btn:disabled {{
    opacity: 0.35;
}}
#timeline_tool_btn::menu-indicator {{
    image: none;
    width: 0;
}}
#timeline_tool_btn:checked {{
    background: rgba(99, 102, 241, 0.28);
    border-color: #6366f1;
    color: {COLOR_TEXT_MAIN};
}}
#timeline_tool_sep {{
    background: {COLOR_BORDER};
    margin: 0 4px;
}}
#timeline_rec_btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: {COLOR_TEXT_SUB};
    font-size: 10px;
    font-weight: 400;
    padding: 0 16px 0 5px;
    min-height: 24px;
    max-height: 24px;
}}
#timeline_rec_btn:hover {{
    background: {COLOR_BG_CARD_HOVER};
    border-color: {COLOR_BORDER};
}}
#timeline_rec_btn::menu-button {{
    border: none;
    border-left: 1px solid {COLOR_BORDER};
    width: 12px;
}}
#timeline_rec_btn[recording="true"] {{
    background: rgba(244, 63, 94, 0.22);
    border-color: {COLOR_ACCENT_ROSE};
    color: {COLOR_TEXT_MAIN};
}}
#timeline_split::handle {{
    width: 1px;
    background: {COLOR_BORDER};
}}
#timeline_split::handle:hover {{
    background: {COLOR_PRIMARY};
}}
#timeline_lane_rail {{
    background-color: {COLOR_BG_CARD};
    border-right: 1px solid {COLOR_BORDER}66;
}}
#timeline_lane_title {{
    background: {COLOR_BG_SIDEBAR};
    border-bottom: 1px solid {COLOR_BORDER}55;
}}
#timeline_lane_title_text {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
/* CapCut-style scrub / context tip */
QFrame#timeline_scrub_tip {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QLabel#timeline_scrub_tip_thumb {{
    background: #1a222e;
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
}}
QLabel#timeline_scrub_tip_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
    font-weight: 650;
    background: transparent;
}}
QLabel#timeline_scrub_tip_time {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    font-family: "Cascadia Mono", "Consolas", monospace;
    background: transparent;
}}
#timeline_track_header {{
    background: {COLOR_BG_CARD};
    border-bottom: 1px solid {COLOR_BORDER}55;
}}
#timeline_track_header:hover {{
    background: {COLOR_BG_CARD_HOVER}44;
}}
#timeline_track_header[picked="true"] {{
    background-color: {wash};
}}
#timeline_track_grip {{
    color: {COLOR_TEXT_MUTED};
    opacity: 0.55;
}}
#timeline_track_header:hover #timeline_track_grip {{
    opacity: 1;
}}
#timeline_track_name {{
    color: {COLOR_TEXT_MAIN};
    font-size: 11px;
    font-weight: 600;
}}
#timeline_track_name_edit {{
    background: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {accent};
    border-radius: 3px;
    padding: 0 4px;
    font-size: 11px;
    font-weight: 400;
}}
#timeline_badge_kind {{
    font-size: 8px;
    font-weight: 700;
    color: {COLOR_TEXT_MUTED};
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 3px;
    padding: 0 4px;
}}
#timeline_track_controls {{
    background: transparent;
}}
#timeline_lane_btn, #timeline_btn_lock, #timeline_btn_mute, #timeline_btn_eye, #timeline_btn_del {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 0;
}}
#timeline_lane_btn:hover, #timeline_btn_lock:hover, #timeline_btn_mute:hover, #timeline_btn_eye:hover {{
    background: {COLOR_BG_CARD_HOVER};
}}
#timeline_btn_del:hover {{
    background: rgba(248, 113, 113, 0.22);
}}
#timeline_btn_lock:checked {{
    background: rgba(245, 158, 11, 0.22);
}}
#timeline_btn_mute:checked {{
    background: rgba(239, 68, 68, 0.24);
}}
#timeline_btn_eye:checked {{
    background: rgba(100, 116, 139, 0.22);
}}
#timeline_btn_solo {{
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    color: {COLOR_TEXT_MUTED};
    font-size: 9px;
    font-weight: 800;
    padding: 0;
}}
#timeline_btn_solo:hover {{
    background: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
    border-color: rgba(255, 255, 255, 0.18);
}}
#timeline_btn_solo:checked {{
    background: rgba(245, 158, 11, 0.28);
    border: 1px solid rgba(245, 158, 11, 0.6);
    color: #fbbf24;
}}
#timeline_plus_btn {{
    background-color: {COLOR_PRIMARY};
    border: none;
    border-radius: 4px;
    min-width: 22px;
    max-width: 22px;
    min-height: 20px;
    max-height: 20px;
    padding: 1px;
}}
#timeline_plus_btn:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
}}
#timeline_plus_btn::menu-indicator {{
    image: none;
    width: 0;
}}
QCheckBox#timeline_dub_focus {{
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: 600;
    spacing: 4px;
    padding: 0;
}}
QCheckBox#timeline_dub_focus::indicator {{
    width: 14px;
    height: 14px;
    background-color: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
}}
QCheckBox#timeline_dub_focus::indicator:hover {{
    border-color: {COLOR_PRIMARY};
    background-color: {COLOR_BG_CARD_HOVER};
}}
QCheckBox#timeline_dub_focus::indicator:checked {{
    background-color: {COLOR_PRIMARY};
    border-color: {COLOR_PRIMARY};
    image: url({_CHECK_ICON});
}}
QToolButton#timeline_add_track_card {{
    background-color: rgba(18, 26, 38, 0.45);
    border: 1px dashed #334155;
    border-radius: 6px;
    color: #94a3b8;
    font-size: 11px;
    font-weight: 500;
    padding: 4px 10px;
    margin: 6px 8px 4px 8px;
    min-height: 22px;
}}
QToolButton#timeline_add_track_card:hover {{
    background-color: rgba(99, 102, 241, 0.12);
    border: 1px dashed {COLOR_PRIMARY};
    color: #ffffff;
}}
QToolButton#timeline_add_track_card::menu-indicator {{
    image: none;
    width: 0;
}}
#timeline_track_slider {{
    max-height: 14px;
}}
#timeline_track_slider::groove:horizontal {{
    height: 3px;
    background: #1e293b;
    border-radius: 2px;
}}
#timeline_track_slider::sub-page:horizontal {{
    background: {COLOR_PRIMARY};
    border-radius: 2px;
}}
#timeline_track_slider::handle:horizontal {{
    width: 9px;
    height: 9px;
    margin: -3px 0;
    border-radius: 4px;
    background: #e2e8f0;
}}
#timeline_track_slider::handle:horizontal:hover {{
    background: #ffffff;
}}
#timeline_track_level_lbl {{
    color: {COLOR_TEXT_MUTED};
    font-size: 9px;
    font-family: monospace;
}}
#timeline_scroll, #timeline_lane_scroll, #timeline_sequence {{
    background-color: {COLOR_BG_DARK};
    border: none;
}}
#timeline_canvas, #timeline_ruler {{
    background-color: {COLOR_BG_DARK};
}}
QSlider#timeline_zoom::groove:horizontal, QSlider#timeline_opacity::groove:horizontal {{
    height: 3px;
    background: {COLOR_BORDER};
    border-radius: 2px;
}}
QSlider#timeline_zoom::handle:horizontal, QSlider#timeline_opacity::handle:horizontal {{
    width: 9px;
    height: 9px;
    margin: -3px 0;
    background: {COLOR_PRIMARY};
    border-radius: 5px;
}}

#dub_option_bar {{
    background-color: {COLOR_BG_SIDEBAR};
    border-bottom: 1px solid {COLOR_BORDER}44;
}}
QPushButton#dub_option_btn {{
    background-color: transparent;
    color: {COLOR_TEXT_SUB};
    font-size: 11px;
    font-weight: 700;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 8px;
}}
QPushButton#dub_option_btn:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: #ffffff;
}}
QPushButton#dub_option_btn:checked {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_ACCENT_PURPLE};
    border: 1px solid {COLOR_BORDER};
}}
QPushButton#dub_option_btn:disabled {{
    color: {COLOR_TEXT_MUTED};
}}
QToolButton#dub_canvas_swatch {{
    background-color: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_SUB};
    font-size: 14px;
    font-weight: 700;
    border: 2px solid transparent;
    border-radius: 6px;
    padding: 0;
}}
QToolButton#dub_canvas_swatch:hover {{
    border: 2px solid {COLOR_BORDER};
}}
QToolButton#dub_canvas_swatch:checked {{
    border: 2px solid {COLOR_ACCENT_PURPLE};
}}
QToolButton#dub_style_swatch {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0;
}}
QToolButton#dub_style_swatch:hover {{
    background: transparent;
}}
#dub_text_edit {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 4px 6px;
    font-size: 13px;
}}
#dub_text_edit:focus {{
    border-color: {accent};
}}
QToolButton#dub_text_toggle {{
    background-color: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_SUB};
    font-size: 12px;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 0;
}}
QToolButton#dub_text_toggle:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
}}
QToolButton#dub_text_toggle:checked {{
    background-color: rgba(139, 92, 246, 0.22);
    border-color: {COLOR_ACCENT_PURPLE};
    color: {COLOR_TEXT_MAIN};
}}
QToolButton#dub_text_tile {{
    background: transparent;
    color: {COLOR_TEXT_SUB};
    font-size: 10px;
    font-weight: 600;
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 2px;
}}
QToolButton#dub_text_tile:hover {{
    border-color: {COLOR_BORDER};
    color: {COLOR_TEXT_MAIN};
}}
QToolButton#dub_text_tile:checked {{
    border-color: {COLOR_ACCENT_PURPLE};
    color: {COLOR_TEXT_MAIN};
}}
#caption_look_grid, #start_localize_look_grid {{
    background: transparent;
}}
#dub_caption_page {{
    background-color: {COLOR_BG_CARD};
}}
QToolButton#caption_look_tile {{
    background-color: #0b111a;
    color: #94a3b8;
    font-size: 10px;
    font-weight: 600;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 3px 2px 2px 2px;
    min-height: 56px;
    max-height: 56px;
}}
QToolButton#caption_look_tile:hover {{
    border-color: #475569;
    color: #f1f5f9;
    background-color: #131c2a;
}}
QToolButton#caption_look_tile:checked {{
    border: 1.5px solid {COLOR_ACCENT_PURPLE};
    color: #ffffff;
    background-color: rgba(168, 85, 247, 0.14);
}}
#caption_motion_grid, #start_localize_motion_grid {{
    background: transparent;
}}
QToolButton#caption_motion_tile {{
    background-color: #0b111a;
    color: #94a3b8;
    font-size: 9.5px;
    font-weight: 600;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 3px 2px 2px 2px;
    min-height: 50px;
    max-height: 50px;
}}
QToolButton#caption_motion_tile:hover {{
    border-color: #475569;
    color: #f1f5f9;
    background-color: #131c2a;
}}
QToolButton#caption_motion_tile:checked {{
    border: 1.5px solid {COLOR_ACCENT_PURPLE};
    color: #ffffff;
    background-color: rgba(168, 85, 247, 0.14);
}}
#caption_color_pick {{
    background: transparent;
    padding-top: 2px;
}}
QToolButton#caption_color_swatch {{
    background-color: transparent;
    border: 2px solid transparent;
    border-radius: 13px;
    padding: 1px;
}}
QToolButton#caption_color_swatch:hover {{
    border-color: #475569;
}}
QToolButton#caption_color_swatch:checked {{
    border-color: {COLOR_ACCENT_PURPLE};
    background-color: rgba(168, 85, 247, 0.22);
}}
QToolButton#caption_color_custom {{
    background-color: #0c121d;
    border: 1px dashed #334155;
    border-radius: 13px;
}}
QToolButton#caption_color_custom:hover {{
    border-color: {COLOR_ACCENT_PURPLE};
    background-color: #151e2e;
}}
QPushButton#caption_color_hex {{
    background-color: #090e17;
    color: #38bdf8;
    font-family: monospace;
    font-size: 10px;
    font-weight: 700;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 2px 8px;
}}
QPushButton#caption_color_hex:hover {{
    border-color: {COLOR_ACCENT_PURPLE};
    color: #ffffff;
}}
#caption_color_pick:disabled {{
    opacity: 0.45;
}}
#caption_color_pick:disabled QToolButton#caption_color_swatch,
#caption_color_pick:disabled QToolButton#caption_color_custom,
#caption_color_pick:disabled QPushButton#caption_color_hex {{
    opacity: 0.45;
}}
QToolButton#caption_pos_preset {{
    background-color: #0b111a;
    color: #94a3b8;
    font-size: 11px;
    font-weight: 500;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 5px 8px;
}}
QToolButton#caption_pos_preset:hover {{
    background-color: #131c2a;
    border-color: #334155;
    color: #f1f5f9;
}}
QToolButton#caption_pos_preset:checked {{
    background-color: rgba(168, 85, 247, 0.14);
    border: 1.5px solid {COLOR_ACCENT_PURPLE};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#caption_apply_btn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #6366f1);
    color: #ffffff;
    font-size: 11px;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    padding: 7px 12px;
    min-height: 18px;
}}
QPushButton#caption_apply_btn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9333ea, stop:1 #4f46e5);
}}
QPushButton#caption_sync_btn {{
    background-color: #0b111a;
    color: #cbd5e1;
    font-size: 11px;
    font-weight: 500;
    border: 1px solid #233348;
    border-radius: 6px;
    padding: 7px 12px;
    min-height: 18px;
}}
QPushButton#caption_sync_btn:hover {{
    background-color: #131d2b;
    border-color: #38bdf8;
    color: #ffffff;
}}
#caption_sec_divider {{
    background-color: #1e293b66;
    max-height: 1px;
    border: none;
    margin: 4px 0px 2px 0px;
}}
/* ─── AI Movie Dubbing Specialized UI System ─────────────────────── */
/* Shelf / panel headers match the sidebar rail */
#dub_panel_header {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}44;
    min-height: 48px;
    max-height: 48px;
}}
#properties_panel #dub_panel_header {{
    background-color: {COLOR_BG_SIDEBAR};
    border-bottom: none;
}}
/* Shelf header actions — 24px pills with elevated Cyber Dark gradient surfaces */
QToolButton#shelf_header_btn,
QPushButton#shelf_header_btn {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a2536, stop:1 #111a26);
    color: #cbd5e1;
    border: 1px solid #26384f;
    border-radius: 6px;
    padding: 0 10px;
    font-size: 11px;
    font-weight: 600;
    min-height: 24px;
    max-height: 24px;
    margin: 0;
}}
QToolButton#shelf_header_btn {{
    padding: 0 9px 0 7px;
}}
QToolButton#shelf_header_btn[icon_only="true"],
QPushButton#shelf_header_btn[icon_only="true"] {{
    padding: 0;
}}

QToolButton#shelf_header_btn:hover,
QPushButton#shelf_header_btn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #24344a, stop:1 #172436);
    color: #ffffff;
    border-color: #3f587a;
}}
QToolButton#shelf_header_btn:pressed,
QPushButton#shelf_header_btn:pressed {{
    background: #0f1621;
    border-color: #223246;
}}
QPushButton#shelf_header_btn:disabled,
QToolButton#shelf_header_btn:disabled {{
    color: #4b5a6c;
    background: rgba(14, 20, 29, 0.6);
    border-color: #1a2533;
}}
QToolButton#shelf_header_btn::menu-indicator {{
    image: none;
    width: 0;
    height: 0;
}}

/* Primary action — Export CTA */
QToolButton#shelf_header_btn[role="primary"],
QPushButton#shelf_header_btn[role="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6366f1, stop:1 #4f46e5);
    color: #ffffff;
    border: 1px solid #7c7ff6;
    font-weight: 700;
}}
QToolButton#shelf_header_btn[role="primary"]:hover,
QPushButton#shelf_header_btn[role="primary"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7579f8, stop:1 #5a52ec);
    border-color: #9aa0ff;
    color: #ffffff;
}}
QToolButton#shelf_header_btn[role="primary"]:pressed,
QPushButton#shelf_header_btn[role="primary"]:pressed {{
    background: #4338ca;
    border-color: #6366f1;
}}
QToolButton#shelf_header_btn[role="primary"]:disabled,
QPushButton#shelf_header_btn[role="primary"]:disabled {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a2536, stop:1 #111a26);
    border-color: #223246;
    color: #4b5a6c;
}}

/* Danger action — Delete checked tasks */
QPushButton#shelf_header_btn[role="danger"],
QToolButton#shelf_header_btn[role="danger"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2d1822, stop:1 #1c1017);
    color: #fca5a5;
    border: 1px solid #572230;
}}
QPushButton#shelf_header_btn[role="danger"]:hover,
QToolButton#shelf_header_btn[role="danger"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #421c2c, stop:1 #281420);
    border-color: #e11d48;
    color: #ffffff;
}}
QPushButton#shelf_header_btn[role="danger"]:pressed,
QToolButton#shelf_header_btn[role="danger"]:pressed {{
    background: #190c12;
    border-color: #be123c;
}}

/* Add action — Quick add (+) button hover accent */
QPushButton#shelf_header_btn[role="add"]:hover,
QToolButton#shelf_header_btn[role="add"]:hover {{
    border-color: #6366f1;
    color: #ffffff;
}}

/* Shared segmented tabs (Properties / Dub / Text / Preview) */
#claynext_seg_chrome, #dub_props_tabs {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}44;
}}
#dub_props_tabs_host {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}44;
}}
#claynext_seg_host, #claynext_seg_sm {{
    background: transparent;
    border: none;
}}
#chrome_tabs_host, #chrome_tabs_row {{
    background: transparent;
    border: none;
}}
#dub_player_modes {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
}}
#preview_load_overlay {{
    background: rgba(8, 12, 18, 0.72);
    border: none;
}}
#preview_load_label {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    border: none;
}}
/* Fill / shape painted by ChromeTabButton — keep QSS transparent. */
QPushButton#chrome_tab_btn {{
    background-color: transparent;
    border: none;
    padding: 0 12px;
    min-height: 26px;
    max-height: 28px;
    min-width: 88px;
}}
QPushButton#chrome_tab_btn:hover,
QPushButton#chrome_tab_btn:checked {{
    background-color: transparent;
    border: none;
}}
/* Track fill/border painted by SegmentTrack (full capsule). */
#claynext_seg, #dub_props_seg {{
    background: transparent;
    border: none;
    border-radius: 999px;
}}
#claynext_seg_sm #claynext_seg {{
    border-radius: 999px;
    min-height: 24px;
    max-height: 24px;
}}
QPushButton#claynext_seg_btn, QPushButton#dub_props_tab {{
    background-color: transparent;
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 400;
    border: 1px solid transparent;
    border-radius: 999px;
    padding: 4px 10px;
    min-height: 24px;
    max-height: 26px;
}}
#claynext_seg_sm QPushButton#claynext_seg_btn {{
    font-size: 10px;
    padding: 0 12px;
    min-height: 18px;
    max-height: 20px;
    border-radius: 999px;
}}
QPushButton#claynext_seg_btn:hover, QPushButton#dub_props_tab:hover {{
    background-color: transparent;
    color: {COLOR_TEXT_MAIN};
}}
QPushButton#claynext_seg_btn:checked, QPushButton#dub_props_tab:checked {{
    /* Sliding pill is painted by SegmentTrack — keep label normal weight. */
    background-color: transparent;
    color: {COLOR_TEXT_MAIN};
    border: 1px solid transparent;
    font-weight: 400;
}}
QPushButton#dub_props_chip {{
    background-color: transparent;
    color: {COLOR_TEXT_SUB};
    font-size: 10px;
    font-weight: 600;
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 3px 4px;
    min-height: 22px;
}}
QPushButton#dub_props_chip:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
}}
QPushButton#dub_props_chip:checked {{
    background-color: rgba(139, 92, 246, 0.14);
    color: {COLOR_ACCENT_PURPLE};
    border: 1px solid {COLOR_ACCENT_PURPLE};
    font-weight: 700;
}}
QToolButton#dub_props_ratio {{
    background-color: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_SUB};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 2px;
    min-width: 32px;
    max-width: 32px;
    min-height: 26px;
    max-height: 26px;
}}
QToolButton#dub_props_ratio:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    border-color: {COLOR_BORDER_FOCUS};
}}
QToolButton#dub_props_ratio:checked {{
    background-color: rgba(139, 92, 246, 0.18);
    border: 1px solid {COLOR_ACCENT_PURPLE};
}}
#dub_props_tabs_host #claynext_seg_sm {{
    min-width: 0;
}}
#dub_props_tabs_host #claynext_seg_sm #claynext_seg {{
    min-width: 0;
    min-height: 24px;
    max-height: 24px;
    border-radius: 999px;
}}
#dub_props_tabs_host QPushButton#claynext_seg_btn {{
    min-width: 0;
    padding: 0 8px;
    border-radius: 999px;
}}
QToolButton#dub_props_filter {{
    background-color: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_SUB};
    font-size: 9px;
    font-weight: 500;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 3px 2px 2px 2px;
    min-height: 56px;
}}
QToolButton#dub_props_filter:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
    border-color: {COLOR_BORDER_FOCUS};
}}
QToolButton#dub_props_filter:checked {{
    background-color: rgba(139, 92, 246, 0.16);
    color: {COLOR_ACCENT_PURPLE};
    border: 1px solid {COLOR_ACCENT_PURPLE};
    font-weight: 700;
}}
#dub_props_divider, #dub_config_divider {{
    background: transparent;
    border: none;
    margin: 0;
    min-height: 0;
    max-height: 0;
}}
QPushButton#dub_props_ghost_btn {{
    background-color: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_SUB};
    font-size: 10px;
    font-weight: 600;
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 2px 8px 2px 6px;
    min-height: 20px;
    max-height: 22px;
}}
QPushButton#dub_props_ghost_btn:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
    border-color: {COLOR_BORDER_FOCUS};
}}
QPushButton#dub_props_ghost_btn:pressed {{
    background-color: rgba(139, 92, 246, 0.2);
}}
#dub_props_scroll QSlider::groove:horizontal, #track_props_page QSlider::groove:horizontal, #overlay_inspector QSlider::groove:horizontal {{
    height: 4px;
    background: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 2px;
}}
#dub_props_scroll QSlider::sub-page:horizontal, #track_props_page QSlider::sub-page:horizontal, #overlay_inspector QSlider::sub-page:horizontal {{
    background: {COLOR_ACCENT_PURPLE};
    border-radius: 2px;
}}
#dub_props_scroll QSlider::handle:horizontal, #track_props_page QSlider::handle:horizontal, #overlay_inspector QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -4px 0;
    background: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_ACCENT_PURPLE};
    border-radius: 6px;
}}
#dub_props_scroll QSlider::handle:horizontal:hover, #track_props_page QSlider::handle:horizontal:hover {{
    background: #ffffff;
    border-color: #ffffff;
}}
#dub_panel_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 15px;
    font-weight: 400;
    letter-spacing: 0;
    text-transform: none;
    padding: 0;
    margin: 0;
    background: transparent;
    border: none;
}}
#dub_panel_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 400;
    line-height: 1.35;
    padding: 4px 12px 8px 12px;
    background: transparent;
    border: none;
}}
#dub_tasks_panel #transcript_table {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 6px;
    outline: none;
}}
#dub_tasks_panel #transcript_table::item {{
    padding: 0;
    border: none;
    outline: none;
}}
#dub_tasks_panel #transcript_table::item:focus {{
    outline: none;
    border: none;
}}
#dub_tasks_panel #transcript_table QHeaderView::section {{
    background-color: {COLOR_BG_SIDEBAR};
    padding: 5px 1px;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: {COLOR_TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER};
}}
#dub_tasks_panel #transcript_table QHeaderView::section:first,
#dub_tasks_panel #transcript_table QHeaderView::section:horizontal:first {{
    padding: 0;
    max-width: 26px;
}}

#dub_tasks_panel #task_check_cell {{
    background: transparent;
    border: none;
}}
#dub_tasks_panel QCheckBox#task_row_check {{
    background: transparent;
    border: none;
    margin: 0;
    padding: 0;
    spacing: 0;
    max-width: 16px;
    max-height: 16px;
}}
#dub_tasks_panel QCheckBox#task_row_check::indicator {{
    width: 14px;
    height: 14px;
    background-color: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
}}
#dub_tasks_panel QCheckBox#task_row_check::indicator:hover {{
    border-color: {COLOR_BORDER_FOCUS};
    background-color: {COLOR_BG_CARD_HOVER};
}}
#dub_tasks_panel QCheckBox#task_row_check::indicator:checked {{
    background-color: {COLOR_PRIMARY};
    border-color: {COLOR_PRIMARY};
    image: url({_CHECK_ICON});
}}
#dub_tasks_panel QCheckBox#task_row_check::indicator:indeterminate {{
    background-color: {COLOR_PRIMARY};
    border-color: {COLOR_PRIMARY};
    image: url({_DASH_ICON});
}}
/* Voices panel filter (search row) — keep existing look. */
#voice_filter_btn {{
    background-color: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 0 10px;
    font-size: 11px;
    font-weight: 650;
    min-height: 26px;
    max-height: 26px;
}}
#voice_filter_btn:hover {{
    border-color: {accent};
}}
#voice_filter_btn::menu-indicator {{
    image: none;
    width: 0;
    height: 0;
}}

#voice_browser {{
    background: transparent;
}}
#voice_row {{
    background-color: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
#voice_name {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}}
#voice_meta {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    background: transparent;
}}
#voice_star {{
    color: #f5c451;
    background: transparent;
    border: none;
    font-size: 14px;
    font-weight: 700;
}}

#dub_config_section {{
    background: transparent;
    border: none;
    min-width: 0;
}}
#dub_config_head {{
    background: transparent;
    border: none;
    border-radius: 4px;
}}
#dub_config_head:hover {{
    background: rgba(99, 102, 241, 0.08);
}}
#dub_config_chevron_btn {{
    background: transparent;
    border: none;
    padding: 0;
    margin: 0;
}}
#dub_config_chevron_btn:hover {{
    background: transparent;
}}
#dub_config_body {{
    background: transparent;
    border: none;
    margin: 0 2px;
    padding-bottom: 4px;
}}
#dub_config_header {{
    color: {COLOR_ACCENT_PURPLE};
    font-size: 10px;
    font-weight: 400;
    letter-spacing: 0.8px;
    padding: 2px 0;
    background: transparent;
}}
#dub_switch {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 400;
    spacing: 8px;
    padding: 0 2px;
    background: transparent;
}}
#dub_switch::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    background: {COLOR_BG_INPUT};
}}
#dub_switch::indicator:hover {{
    border-color: {COLOR_ACCENT_PURPLE};
}}
#dub_switch::indicator:checked {{
    background: {COLOR_ACCENT_PURPLE};
    border-color: {COLOR_ACCENT_PURPLE};
    image: url({_CHECK_ICON});
}}
#dub_switch_hint {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 400;
    padding-left: 22px;
    background: transparent;
}}
#startLocalizeDialog {{
    background-color: {COLOR_BG_CARD};
}}
#start_dub_chrome {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}44;
}}
#start_dub_chrome #claynext_seg_sm {{
    background: transparent;
    min-width: 0;
}}
#start_dub_chrome #claynext_seg_sm #claynext_seg {{
    min-width: 0;
    min-height: 24px;
    max-height: 24px;
    border-radius: 999px;
}}
#start_dub_chrome QPushButton#claynext_seg_btn {{
    min-width: 0;
    padding: 0 10px;
    border-radius: 999px;
}}
#start_dub_body {{
    background-color: {COLOR_BG_CARD};
}}
#startLocalizeDialog QScrollArea#start_dub_captions,
#startLocalizeDialog QScrollArea#start_dub_captions > QWidget {{
    background: transparent;
    border: none;
}}
/* Match Settings field size (28px) */
#startLocalizeDialog QComboBox#start_localize_combo {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 0 8px;
    min-height: 28px;
    max-height: 28px;
    font-size: 11px;
}}
#startLocalizeDialog QComboBox#start_localize_combo:hover {{
    border-color: {accent};
}}
#startLocalizeDialog QComboBox#start_localize_combo:focus {{
    border-color: {accent};
}}
#startLocalizeDialog QComboBox#start_localize_combo::drop-down {{
    border: none;
    width: 18px;
}}
#startLocalizeDialog QLineEdit#start_localize_field {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 0 8px;
    min-height: 28px;
    max-height: 28px;
    font-size: 11px;
}}
#startLocalizeDialog QLineEdit#start_localize_field:focus {{
    border-color: {accent};
}}
#startLocalizeDialog QLineEdit#start_localize_field:disabled {{
    color: {COLOR_TEXT_MUTED};
}}
#startLocalizeDialog #scrub_spin {{
    min-height: 28px;
    max-height: 28px;
}}
#startLocalizeDialog #start_localize_divider {{
    background: transparent;
    border: none;
}}
#startLocalizeDialog #start_localize_divider_label {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.6px;
    background: transparent;
    border: none;
    padding: 0;
}}
#startLocalizeDialog #start_localize_divider_rule {{
    background-color: {COLOR_BORDER}66;
    border: none;
    max-height: 1px;
}}
#startLocalizeDialog #dub_switch {{
    spacing: 8px;
    padding: 1px 0;
    font-size: 11px;
}}
#startLocalizeDialog #dub_switch_hint {{
    padding-left: 22px;
    padding-bottom: 0;
}}
#startLocalizeDialog QPushButton#start_localize_btn {{
    background-color: transparent;
    color: {COLOR_TEXT_SUB};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 0 14px;
    font-size: 11.5px;
    font-weight: 600;
    min-height: 28px;
    max-height: 28px;
}}
#startLocalizeDialog QPushButton#start_localize_btn:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
    border-color: {COLOR_BORDER_FOCUS};
}}
#startLocalizeDialog QPushButton#start_localize_btn:pressed {{
    background-color: {COLOR_BG_INPUT};
}}
#startLocalizeDialog QPushButton#start_localize_btn_primary {{
    background-color: {COLOR_PRIMARY};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 0 14px;
    font-size: 11.5px;
    font-weight: 600;
    min-height: 28px;
    max-height: 28px;
}}
#startLocalizeDialog QPushButton#start_localize_btn_primary:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
}}
#startLocalizeDialog QPushButton#start_localize_btn_primary:pressed {{
    background-color: {COLOR_ACCENT_PURPLE};
}}
#startLocalizeDialog QPushButton#start_localize_btn_primary:disabled {{
    background-color: {COLOR_BG_INPUT};
    color: {COLOR_TEXT_MUTED};
    border: 1px solid {COLOR_BORDER}66;
}}
#start_dub_batch {{
    background-color: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER}66;
    border-radius: 10px;
}}
#start_dub_batch #start_dub_sources_head {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.3px;
    background: transparent;
}}
#start_dub_batch #dub_switch_hint {{
    padding-left: 0;
}}
#dub_setting_field {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 4px 8px;
    min-height: 26px;
}}
#dub_setting_field:focus {{
    border-color: {accent};
}}
#dub_setting_field:disabled {{
    color: {COLOR_TEXT_MUTED};
}}
#font_field {{
    background-color: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
#font_field:hover,
#font_field[open="true"] {{
    border-color: {accent};
}}
#font_field_name {{
    background: transparent;
    border: none;
    color: {COLOR_TEXT_MAIN};
    padding: 0 6px;
    font-size: 12px;
}}
#font_field_rail {{
    background: transparent;
    border: none;
    border-left: 1px solid {COLOR_BORDER}88;
}}
#font_field_chevron {{
    background: transparent;
    border: none;
    padding: 0;
    margin: 0;
}}
#font_menu {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
#font_menu_list {{
    background: transparent;
    border: none;
    outline: none;
    color: {COLOR_TEXT_MAIN};
    padding: 2px;
}}
#font_menu_list::item {{
    border-radius: 4px;
    padding: 4px 8px;
    color: {COLOR_TEXT_MAIN};
}}
#font_menu_list::item:hover {{
    background: {COLOR_BG_CARD_HOVER};
}}
#font_menu_list::item:selected {{
    background: {wash};
    color: {COLOR_TEXT_MAIN};
}}
#scrub_spin {{
    background-color: {COLOR_BG_DARK};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
#scrub_spin:hover {{
    border-color: {COLOR_BORDER};
}}
#scrub_spin[focused="true"] {{
    border-color: {accent};
}}
#scrub_spin_edit {{
    background: transparent;
    border: none;
    color: {COLOR_TEXT_MAIN};
    padding: 4px 6px;
    font-size: 12px;
    font-weight: 400;
    selection-background-color: rgba(99, 102, 241, 0.35);
}}
#scrub_spin_steps {{
    background: transparent;
    border-left: 1px solid {COLOR_BORDER}88;
}}
#scrub_spin_step {{
    background: transparent;
    border: none;
    border-radius: 3px;
    padding: 0;
    margin: 0;
}}
#scrub_spin_step:hover {{
    background: {COLOR_BG_CARD_HOVER};
}}
#scrub_spin_step:pressed {{
    background: rgba(99, 102, 241, 0.25);
}}
QSlider#dub_setting_slider::groove:horizontal {{
    height: 3px;
    background: {COLOR_BORDER};
    border-radius: 2px;
}}
QSlider#dub_setting_slider::sub-page:horizontal {{
    background: {COLOR_ACCENT_PURPLE};
    border-radius: 2px;
}}
QSlider#dub_setting_slider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -5px 0;
    background: {COLOR_TEXT_MAIN};
    border-radius: 6px;
}}
#script_reverse_btn, #script_accept_btn {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 700;
    min-height: 26px;
}}
#script_reverse_btn {{
    color: {COLOR_TEXT_SUB};
}}
#script_reverse_btn:hover {{
    color: {COLOR_TEXT_MAIN};
    border-color: {COLOR_TEXT_SUB};
}}
#script_accept_btn {{
    color: #e9d5ff;
    border-color: rgba(168, 85, 247, 0.55);
    background: rgba(168, 85, 247, 0.16);
}}
#script_accept_btn:hover {{
    background: rgba(168, 85, 247, 0.28);
}}
#script_reverse_btn:disabled, #script_accept_btn:disabled {{
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER};
    background: transparent;
}}
"""

