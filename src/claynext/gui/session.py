"""Single active top-level window for Claynext GUI.

Keeps strong refs and ensures Home and Studio never both own an HWND at once —
that dual-window state is what Windows paints as the floating \"Clay…\" list.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication

_state: dict[str, Any] = {"home": None, "studio": None}


def active_home():
    return _state["home"]


def active_studio():
    return _state["studio"]


def set_home(home) -> None:
    _state["home"] = home


def set_studio(studio) -> None:
    _state["studio"] = studio


def destroy_home() -> None:
    """Close and delete the Home window so its HWND leaves Alt+Tab / Snap Assist."""
    home = _state["home"]
    _state["home"] = None
    if home is None:
        return
    try:
        home.hide()
    except Exception:
        pass
    try:
        home.close()
    except Exception:
        pass
    try:
        home.deleteLater()
    except Exception:
        pass


def destroy_studio() -> None:
    studio = _state["studio"]
    _state["studio"] = None
    if studio is None:
        return
    try:
        studio._returning_home = True  # noqa: SLF001
    except Exception:
        pass
    try:
        studio.hide()
    except Exception:
        pass
    try:
        studio.close()
    except Exception:
        pass
    try:
        studio.deleteLater()
    except Exception:
        pass


def open_studio(project_path: str | None = None, tool_index: int = 0):
    """Open Studio, then destroy Home so only one top-level HWND remains."""
    from claynext.gui.main_window import ToolWindow
    from claynext.gui.window_chrome import dismiss_stray_overlays

    app = QApplication.instance()
    prev_quit = True
    if app is not None:
        prev_quit = app.quitOnLastWindowClosed()
        # Prevent quit while we swap Home → Studio.
        app.setQuitOnLastWindowClosed(False)

    try:
        win = ToolWindow(
            tool_index=tool_index,
            home_window=None,
            on_return_home=return_to_home,
            project_path=project_path,
        )
        _state["studio"] = win
        win.show()
        win.raise_()
        win.activateWindow()
        # Destroy Home only after Studio is mapped — one HWND, no Clay… pair.
        destroy_home()
        dismiss_stray_overlays(keep={win})
        return win
    finally:
        if app is not None:
            app.setQuitOnLastWindowClosed(prev_quit)


def return_to_home():
    """Close Studio and recreate a fresh Home window."""
    from claynext.gui.project_home_window import ProjectHomeWindow

    app = QApplication.instance()
    prev_quit = True
    if app is not None:
        prev_quit = app.quitOnLastWindowClosed()
        app.setQuitOnLastWindowClosed(False)

    try:
        destroy_studio()
        home = ProjectHomeWindow()
        _state["home"] = home
        home.show()
        home.raise_()
        home.activateWindow()
        return home
    finally:
        if app is not None:
            app.setQuitOnLastWindowClosed(prev_quit)
