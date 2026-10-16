"""QSS section: Sidebar, header, and dock workspace."""
from __future__ import annotations

from claynext.constants.theme_constants import (
    COLOR_BG_DARK, COLOR_BG_SIDEBAR, COLOR_BG_HEADER, COLOR_BG_TITLEBAR,
    COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_INPUT, COLOR_BG_STATUSBAR,
    COLOR_BORDER, COLOR_PRIMARY, COLOR_PRIMARY_HOVER,
    COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
    COLOR_ACCENT_EMERALD, COLOR_ACCENT_PURPLE,
)


def shell_qss(accent: str, wash: str) -> str:
    return f"""
/* ─── Sidebar ────────────────────────────────────────────────────── */
#sidebar {{
    background-color: {COLOR_BG_SIDEBAR};
    border-right: 1px solid {COLOR_BORDER}66;
    min-width: 220px;
    max-width: 220px;
}}

#sidebar QPushButton {{
    background-color: transparent;
    color: {COLOR_TEXT_SUB};
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    padding: 9px 14px;
    text-align: left;
    font-size: 12px;
    font-weight: 600;
    margin: 0px;
}}
#sidebar QPushButton:hover {{
    background-color: {COLOR_BG_CARD_HOVER};
    color: {COLOR_TEXT_MAIN};
    border-left: 3px solid {COLOR_BORDER};
}}
#sidebar QPushButton:checked, #sidebar QPushButton:pressed {{
    background-color: {wash};
    color: {accent};
    font-weight: 700;
    border-left: 3px solid {accent};
}}

/* ─── Content Header Bar ─────────────────────────────────────────── */
#header_bar {{
    background-color: {COLOR_BG_SIDEBAR};
    border-bottom: 1px solid {COLOR_BORDER}44;
}}
#page_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
}}
#page_desc {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
}}
#header_divider {{
    background-color: {COLOR_BORDER}66;
}}
#header_settings_btn {{
    background: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
#header_settings_btn:hover {{
    background: {COLOR_BG_CARD_HOVER};
    border-color: {accent};
}}
#header_settings_btn:focus {{
    border-color: {accent};
}}

/* ─── Tool Workspace ─────────────────────────────────────────────── */
#tool_workspace {{
    background-color: {COLOR_BG_DARK};
}}

/* ─── Dock Workspace (ASR & tool panels) ─────────────────────────── */
/* ─── Dock Workspace (ASR & tool panels) ─────────────────────────── */
#dock_workspace, #dock_host, #dock_central_placeholder {{
    background-color: {COLOR_BG_DARK};
    border: none;
}}
QDockWidget {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 400;
    border: none;
    background-color: {COLOR_BG_CARD};
}}
/* Dock titles — 32px chrome (shorter than shelf panel headers at 40px) */
QDockWidget::title {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-bottom: none;
    padding: 6px 10px;
    text-align: left;
    min-height: 20px;
    max-height: 20px;
}}
#dock_header {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER}44;
    border-radius: 0;
    min-height: 36px;
    max-height: 36px;
}}
#dock_header #claynext_seg, #dock_header #dub_props_seg {{
    border-radius: 6px;
}}
#dock_header QPushButton#claynext_seg_btn, #dock_header QPushButton#dub_props_tab {{
    min-height: 18px;
    max-height: 20px;
    padding: 1px 10px;
    font-size: 10px;
}}
/* Preview Source / Timeline — compact segmented pill */
#dock_header #dub_player_modes {{
    background-color: transparent;
    border: none;
    max-height: 24px;
}}
#dock_header #dub_player_modes #claynext_seg_sm,
#dock_header #dub_player_modes #claynext_seg_host {{
    background: transparent;
}}
#dock_header #dub_player_modes #claynext_seg {{
    min-width: 148px;
    max-height: 22px;
    border-radius: 11px;
}}
#dock_header #dub_player_modes QPushButton#claynext_seg_btn {{
    min-width: 64px;
    max-width: 88px;
    min-height: 18px;
    max-height: 20px;
    padding: 0 10px;
    font-size: 10px;
}}
QToolButton#dock_header_btn {{
    background-color: transparent;
    border: none;
    border-radius: 9px;
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
}}
QToolButton#dock_header_btn:hover {{
    background-color: rgba(255, 255, 255, 0.06);
}}
#dock_title_label {{
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.2px;
    background: transparent;
    border: none;
    padding: 0;
    margin: 0;
}}
QDockWidget[chrome="docked"],
QDockWidget[chrome="float"] {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER}66;
    border-radius: 0;
}}
QDockWidget[chrome="docked"] > QWidget,
QDockWidget[chrome="float"] > QWidget {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
}}
QMainWindow::separator {{
    background: {COLOR_BG_DARK};
    width: 6px;
    height: 6px;
}}
QMainWindow::separator:hover {{
    background: {COLOR_BORDER};
}}
QSplitter::handle {{
    background: {COLOR_BORDER};
}}
QSplitter::handle:hover {{
    background: {accent};
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 2px;
}}
#media_group_split::handle {{
    background: {COLOR_BORDER};
    margin: 0 10px;
}}
#media_group_split::handle:hover {{
    background: {accent};
}}

#asr_toolbar {{
    border-radius: 0;
}}
#media_panel, #playback_panel, #controls_panel, #properties_panel, #transcript_panel, #timeline_panel, #preview_editor, #dub_shelf, #dub_shelf_stack, #dub_config_panel {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
}}
#panel_section_label {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: 400;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    padding: 2px 2px 4px 2px;
    background: transparent;
    border: none;
}}
#media_lib_group, #media_player_group {{
    background: transparent;
    border: none;
}}
#media_player_body {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
}}
#transcript_panel {{
    background-color: {COLOR_BG_CARD};
    border: none;
    border-radius: 0;
}}

"""

