"""Window chrome: title bar, docks, shelves, and the startup loader."""
from claynext.gui.components.shell.dock import DockWorkspace
from claynext.gui.components.shell.icon_tabs import IconTabShelf
from claynext.gui.components.shell.loader import ToolLoaderScreen
from claynext.gui.components.shell.log import LogPanel
from claynext.gui.components.shell.status_bar import CustomStatusBar
from claynext.gui.components.shell.title_bar import CustomTitleBar

__all__ = [
    "CustomStatusBar",
    "CustomTitleBar",
    "DockWorkspace",
    "IconTabShelf",
    "LogPanel",
    "ToolLoaderScreen",
]
