import argparse
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from claynext.constants import NAV_ITEMS
from claynext.utils.stderr_filter import install_ffmpeg_mf_stderr_filter


def _resolve_tool_index(value: str | None) -> int:
    """Resolve --tool value to a NAV_ITEMS index. Defaults to studio (0)."""
    if value is None:
        return 0
    text = value.strip().lower()
    if text.isdigit():
        idx = int(text)
        if 0 <= idx < len(NAV_ITEMS):
            return idx
        return 0
    if text in ("dubbing", "dub"):
        text = "studio"
    for item in NAV_ITEMS:
        if text in (item["id"], item.get("short_label", "").lower(), item["label"].lower()):
            return item["index"]
    return 0


def _open_studio(tool_index: int = 0, project_path: str | None = None):
    from claynext.gui.main_window import ToolWindow

    win = ToolWindow(
        tool_index=tool_index,
        project_path=project_path,
    )
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def main():
    """
    Application entrypoint.
    Flow: loader splash → Studio editor.
    Dev: uv run main.py --no-splash
         uv run main.py --project path.claynext.json --no-splash
    """
    parser = argparse.ArgumentParser(description="Claynext Studio")
    parser.add_argument(
        "--tool",
        metavar="NAME",
        help="Tool id (studio, or 0). Defaults to studio.",
    )
    parser.add_argument(
        "--no-splash",
        action="store_true",
        help="Skip the loader splash (useful during development)",
    )
    parser.add_argument(
        "--studio",
        action="store_true",
        help="Deprecated: Studio opens by default (kept for compatibility)",
    )
    parser.add_argument(
        "--project",
        metavar="PATH",
        help="Open this .claynext.json project in the studio",
    )
    args, qt_args = parser.parse_known_args()

    # Qt Multimedia probes h264_mf / hevc_mf on startup; many PCs lack HEVC MF.
    install_ffmpeg_mf_stderr_filter()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Claynext Studio")
    app.setOrganizationName("Claynext")

    tool_index = _resolve_tool_index(args.tool)

    # Keep strong refs so windows are not GC'd.
    state: dict = {"win": None, "loader": None}

    def _after_loader():
        state["win"] = _open_studio(tool_index, project_path=args.project)

    if args.no_splash:
        _after_loader()
    else:
        from claynext.gui.components.tool_loader import ToolLoaderScreen

        tool_data = NAV_ITEMS[tool_index] if 0 <= tool_index < len(NAV_ITEMS) else NAV_ITEMS[0]
        loader = ToolLoaderScreen(tool_data=tool_data, parent=None, on_complete=_after_loader)
        state["loader"] = loader
        loader.show()
        loader.raise_()
        loader.activateWindow()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
