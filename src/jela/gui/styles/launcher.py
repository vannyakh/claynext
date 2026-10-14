"""QSS section: Launcher, tool tabs, and API keys."""
from __future__ import annotations

from jela.constants.theme_constants import (
    COLOR_BG_DARK, COLOR_BG_SIDEBAR, COLOR_BG_HEADER, COLOR_BG_TITLEBAR,
    COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_INPUT, COLOR_BG_STATUSBAR,
    COLOR_BORDER, COLOR_PRIMARY, COLOR_PRIMARY_HOVER,
    COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
    COLOR_ACCENT_EMERALD, COLOR_ACCENT_PURPLE,
)


def launcher_qss(accent: str, wash: str) -> str:
    return f"""
/* ─── Launcher Window Styles ─────────────────────────────────────── */
#launcher_root {{
    background-color: {COLOR_BG_DARK};
}}

#launcher_left_panel {{
    background-color: {COLOR_BG_SIDEBAR};
    border: none;
}}
#launcher_brand {{
    background-color: {COLOR_BG_DARK};
    border-bottom: 1px solid {COLOR_BORDER};
}}
#launcher_brand_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -0.3px;
    background: transparent;
}}
#launcher_section {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.2px;
    background: transparent;
}}
#launcher_divider {{
    background: {COLOR_BORDER};
    border: none;
    max-width: 1px;
}}
#tool_content_panel, #content_inner {{
    background: transparent;
}}
#tool_hero_title {{
    color: {COLOR_TEXT_MAIN};
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.4px;
    background: transparent;
}}
#tool_hero_desc {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}}
#launcher_kicker {{
    color: {COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.1px;
    background: transparent;
}}
#launcher_body {{
    color: {COLOR_TEXT_SUB};
    font-size: 13px;
    background: transparent;
}}
#launcher_rule {{
    background: {COLOR_BORDER};
    border: none;
    max-height: 1px;
}}
#tool_row_name {{
    color: {COLOR_TEXT_MAIN};
    font-size: 13px;
    font-weight: 650;
    background: transparent;
    border: none;
}}
#tool_row_desc {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    background: transparent;
    border: none;
}}
#tool_row_key {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 700;
    background: transparent;
    border: none;
}}
#launch_bar {{
    background: {COLOR_BG_SIDEBAR};
    border-top: 1px solid {COLOR_BORDER};
}}

#launcher_header {{
    background-color: transparent;
    border-bottom: 1px solid #1e293b;
}}

#launcher_header_title {{
    color: #ffffff;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -0.4px;
}}

#launcher_header_subtitle {{
    color: #64748b;
    font-size: 12px;
    font-weight: 500;
}}

.tool_tile {{
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid transparent;
    border-radius: 18px;
    padding: 12px 10px;
}}

.tool_tile:hover {{
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.06);
}}

.tool_tile:focus {{
    background-color: rgba(255, 255, 255, 0.07);
    border: 1px solid {accent}66;
}}

#tool_tile_title {{
    color: #f8fafc;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -0.2px;
}}

#launcher_footer {{
    background-color: {COLOR_BG_DARK};
    border-top: 1px solid {COLOR_BORDER};
}}

#launcher_footer_tip {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 500;
    background: transparent;
}}

#launcher_footer_version {{
    color: {COLOR_TEXT_SUB};
    font-size: 11px;
    font-weight: 600;
    background: transparent;
}}

/* ─── Tool Tabs Strip ────────────────────────────────────────────── */
#tool_tab_btn {{
    background-color: transparent;
    color: #8fa1b4;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    border-radius: 4px 4px 0 0;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 600;
}}
#tool_tab_btn:hover {{
    background-color: #151d28;
    color: #ffffff;
}}
#tool_tab_btn:checked {{
    background-color: #1a2434;
    color: #ffffff;
    border-bottom: 2px solid {accent};
}}

/* ─── API keys dialog ────────────────────────────────────────────── */
#apiKeysDialog QLineEdit, #apiKeysDialog QComboBox {{
    min-height: 24px;
    padding: 3px 8px;
    font-size: 11px;
}}
#api_keys_btn, #api_keys_btn_primary {{
    min-height: 24px;
    max-height: 26px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
    border-radius: 6px;
}}
#api_keys_btn {{
    background-color: #1a2230;
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
}}
#api_keys_btn:hover {{
    background-color: #243044;
    border-color: #3d4f66;
}}
#api_keys_btn_primary {{
    background-color: {COLOR_PRIMARY};
    color: #ffffff;
    border: none;
}}
#api_keys_btn_primary:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
}}

"""
