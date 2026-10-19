"""Right-dock properties."""
from claynext.gui.components.inspector.properties.const import (
    AUDIO_KINDS,
    VIDEO_TABS,
    db10_to_pct,
    db_text,
    pct_to_db10,
)
from claynext.gui.components.inspector.properties.page import TrackPropsPage
from claynext.gui.dialogs.project_settings_dialog import ProjectInfoPage

__all__ = [
    "AUDIO_KINDS",
    "VIDEO_TABS",
    "ProjectInfoPage",
    "TrackPropsPage",
    "db10_to_pct",
    "db_text",
    "pct_to_db10",
]
