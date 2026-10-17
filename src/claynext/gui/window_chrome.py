"""Windows DWM / task-switcher helpers for frameless Claynext windows.

The floating \"Clay…\" list is Windows truncating \"Claynext Studio — …\" when
more than one top-level HWND is registered (Home + Studio, or a nested
QMainWindow that was created without a parent).

Important: do **not** toggle Qt.WindowType.Tool via setWindowFlags while
parking — that recreates the native HWND and can trigger Snap Assist.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolTip, QWidget


def park_window_away_from_task_switcher(widget: QWidget) -> None:
    """Hide *widget* and drop it from Alt+Tab / Snap Assist (no HWND recreate)."""
    if widget is None:
        return
    widget.hide()
    # Blank caption while parked — Windows truncates \"Claynext…\" to \"Clay…\".
    if widget.property("_parked_title") is None:
        widget.setProperty("_parked_title", widget.windowTitle())
    widget.setWindowTitle("")
    _set_tool_exstyle(widget, tool=True)


def restore_parked_window(widget: QWidget, *, custom_chrome: bool = True) -> None:
    """Restore a parked home window's caption / taskbar presence (no flag churn)."""
    del custom_chrome  # kept for call-site compatibility
    if widget is None:
        return
    _set_tool_exstyle(widget, tool=False)
    parked = widget.property("_parked_title")
    if parked:
        widget.setWindowTitle(str(parked))
        widget.setProperty("_parked_title", None)


def force_embedded_main_window(host: QWidget) -> None:
    """Ensure a nested QMainWindow never registers as its own top-level HWND."""
    host.setWindowFlags(Qt.WindowType.Widget)
    host.setWindowTitle("")


def dismiss_stray_overlays(*, keep: set[QWidget] | None = None) -> None:
    """Close leftover loader/tip windows and orphan dock hosts."""
    QToolTip.hideText()
    app = QApplication.instance()
    if app is None:
        return
    keep = keep or set()
    for w in list(app.topLevelWidgets()):
        if w in keep:
            continue
        name = w.objectName() or ""
        if name in {"toolLoaderScreen", "timeline_scrub_tip"}:
            w.hide()
            w.close()
            continue
        if name == "dock_host":
            w.hide()
            force_embedded_main_window(w)


def _set_tool_exstyle(widget: QWidget, *, tool: bool) -> None:
    """Toggle WS_EX_TOOLWINDOW / WS_EX_APPWINDOW without recreating the HWND."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        if not hwnd:
            return
        gwl_exstyle = -20
        ws_ex_appwindow = 0x00040000
        ws_ex_toolwindow = 0x00000080
        user32 = ctypes.windll.user32
        style = int(user32.GetWindowLongW(hwnd, gwl_exstyle))
        if tool:
            style = (style & ~ws_ex_appwindow) | ws_ex_toolwindow
        else:
            style = (style & ~ws_ex_toolwindow) | ws_ex_appwindow
        user32.SetWindowLongW(hwnd, gwl_exstyle, style)
        # Ask DWM to refresh the task-switcher list without Qt flag recreation.
        swp_nosize = 0x0001
        swp_nomove = 0x0002
        swp_nozorder = 0x0004
        swp_framechanged = 0x0020
        swp_hidewindow = 0x0080
        flags = swp_nosize | swp_nomove | swp_nozorder | swp_framechanged
        if tool:
            flags |= swp_hidewindow
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
    except Exception:
        pass
