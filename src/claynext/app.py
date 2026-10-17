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


def _open_home():
    from claynext.gui.project_home_window import ProjectHomeWindow

    home = ProjectHomeWindow()
    home.show()
    home.raise_()
    home.activateWindow()
    return home


def _open_studio(tool_index: int = 0, project_path: str | None = None, home_window=None):
    from claynext.gui.main_window import ToolWindow

    win = ToolWindow(
        tool_index=tool_index,
        home_window=home_window,
        project_path=project_path,
    )
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def main(argv: list[str] | None = None):
    """
    Application entrypoint.
    Flow: loader splash → Project Home → Studio.
    Dev: uv run main.py
         uv run main.py --studio
         uv run main.py --project path.claynext.json
    """
    parser = argparse.ArgumentParser(description="Claynext Studio")
    parser.add_argument(
        "--tool",
        metavar="NAME",
        help="Tool id (studio, or 0). Defaults to studio.",
    )
    parser.add_argument(
        "--studio",
        action="store_true",
        help="Skip project home and open the studio editor directly",
    )
    parser.add_argument(
        "--project",
        metavar="PATH",
        help="Open this .claynext.json project in the studio (implies --studio)",
    )
    args, qt_args = parser.parse_known_args(argv)

    # Qt Multimedia probes h264_mf / hevc_mf on startup; many PCs lack HEVC MF.
    install_ffmpeg_mf_stderr_filter()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Claynext Studio")
    app.setOrganizationName("Claynext")

    tool_index = _resolve_tool_index(args.tool)
    open_studio = bool(args.studio or args.project)

    # Keep strong refs so windows are not GC'd.
    state: dict = {"home": None, "win": None, "loader": None}

    def _after_loader():
        if open_studio:
            state["win"] = _open_studio(tool_index, project_path=args.project)
        else:
            state["home"] = _open_home()

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
