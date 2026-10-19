"""Video stage with the overlay canvas stacked on the preview."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QWidget

from claynext.gui.components.overlay.canvas import OverlayCanvas

class PreviewStageHost(QWidget):
    """Video stage with a transparent overlay canvas on top."""

    def __init__(self, preview: QWidget, overlay: OverlayCanvas, parent=None):
        super().__init__(parent)
        self.setObjectName("preview_stage_wrap")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.preview = preview
        self.overlay = overlay
        preview.setParent(self)
        overlay.setParent(self)
        overlay.raise_()
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if hasattr(overlay, "bind_preview"):
            overlay.bind_preview(preview)
        if hasattr(preview, "aspect_changed"):
            preview.aspect_changed.connect(self.sync_overlay)
        if hasattr(preview, "setFocusPolicy"):
            preview.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def sync_overlay(self, _key=None):
        """Keep overlay full-wrapper; map items to the visible (possibly zoomed) frame."""
        box = self.rect()
        self.overlay.setGeometry(box)
        if hasattr(self.preview, "stage_geometry"):
            # stage_geometry follows view zoom/pan; item x/y stay normalized 0–1.
            self.overlay.set_content_rect(self.preview.stage_geometry())
        else:
            self.overlay.set_content_rect(box)
        self.overlay.raise_()

    # Back-compat for signal connections / callers.
    _sync_overlay_geom = sync_overlay

    def resizeEvent(self, event):
        super().resizeEvent(event)
        box = self.rect()
        self.preview.setGeometry(box)
        self.sync_overlay()
        self.overlay.raise_()
        loader = getattr(self, "_load_overlay", None)
        if loader is not None and loader.isVisible():
            loader.setGeometry(box)
            loader.raise_()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_V:
            if hasattr(self.overlay, "set_view_tool"):
                self.overlay.set_view_tool("move")
            elif hasattr(self.preview, "set_view_tool"):
                self.preview.set_view_tool("move")
            event.accept()
            return
        if key == Qt.Key.Key_H:
            if hasattr(self.overlay, "set_view_tool"):
                self.overlay.set_view_tool("hand")
            elif hasattr(self.preview, "set_view_tool"):
                self.preview.set_view_tool("hand")
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        # Letterbox areas around the frame still zoom the preview.
        delta = event.angleDelta().y()
        if delta != 0 and hasattr(self.preview, "apply_wheel_zoom"):
            self.preview.apply_wheel_zoom(event.globalPosition().toPoint(), delta)
            event.accept()
            return
        super().wheelEvent(event)
