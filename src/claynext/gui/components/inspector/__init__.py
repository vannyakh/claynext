"""Inspector widgets: text, effects, styles, and track properties."""
from claynext.gui.components.inspector.fx import FxInspector
from claynext.gui.components.inspector.properties import TrackPropsPage
from claynext.gui.components.inspector.shelf import FxShelfPanel
from claynext.gui.components.inspector.styles import TextStylesPanel
from claynext.gui.components.inspector.text import TextInspector

__all__ = [
    "FxInspector",
    "FxShelfPanel",
    "TextInspector",
    "TextStylesPanel",
    "TrackPropsPage",
]
