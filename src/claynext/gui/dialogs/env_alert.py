"""Alert when optional packages or model weights are missing before a job runs."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from claynext.models.env_preflight import (
    format_gaps_message,
    has_blocking_gaps,
    primary_install_command,
)


def alert_missing_environment(
    parent,
    gaps: list[dict[str, Any]],
    *,
    title: str = "Environment required",
) -> bool:
    """
    Show a download / install alert for missing environment pieces.

    Returns True if the caller may proceed (no gaps, or only soft gaps and user continues).
    Returns False when the user cancels or a blocking package is missing.
    """
    if not gaps:
        return True

    blocking = has_blocking_gaps(gaps)
    body = format_gaps_message(gaps)
    cmd = primary_install_command(gaps)
    model_repos = [
        str(g.get("repo") or "")
        for g in gaps
        if g.get("kind") == "model" and g.get("repo")
    ]

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setMinimumWidth(440)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 16, 16, 14)
    lay.setSpacing(12)

    head = QLabel("Download or install missing pieces before this job can run.")
    head.setObjectName("env_alert_title")
    head.setWordWrap(True)
    if blocking:
        head.setText("Required environment is not ready. Install the missing package, then retry.")
    lay.addWidget(head)

    detail = QLabel(body)
    detail.setObjectName("env_alert_body")
    detail.setWordWrap(True)
    detail.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    lay.addWidget(detail)

    row = QHBoxLayout()
    row.setSpacing(8)
    if cmd:
        btn_copy = QPushButton("Copy install command")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(lambda: _copy_cmd(cmd, btn_copy))
        row.addWidget(btn_copy)
    if model_repos:
        btn_dl = QPushButton("Download model…")
        btn_dl.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dl.clicked.connect(lambda: _open_models(parent, dlg))
        row.addWidget(btn_dl)
    btn_settings = QPushButton("Open Features")
    btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_settings.clicked.connect(lambda: _open_features(parent, dlg))
    row.addWidget(btn_settings)
    row.addStretch(1)
    lay.addLayout(row)

    buttons = QDialogButtonBox()
    if blocking:
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
    else:
        cont = buttons.addButton("Continue anyway", QDialogButtonBox.ButtonRole.AcceptRole)
        cont.setDefault(True)
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)

    result = dlg.exec()
    if blocking:
        return False
    return result == QDialog.DialogCode.Accepted


def ensure_job_environment(
    parent,
    *,
    voice_id: str | None = None,
    secondary_voice_id: str | None = None,
    asr_model: str | None = None,
    check_stems: bool = True,
    title: str = "Environment required",
) -> bool:
    """Collect gaps for this job and alert when anything is missing."""
    from claynext.models.env_preflight import collect_job_gaps

    gaps = collect_job_gaps(
        voice_id=voice_id,
        secondary_voice_id=secondary_voice_id,
        asr_model=asr_model,
        check_stems=check_stems,
    )
    return alert_missing_environment(parent, gaps, title=title)


def _copy_cmd(cmd: str, btn: QPushButton | None = None):
    QApplication.clipboard().setText(cmd)
    if btn is not None:
        btn.setText("Copied")


def _settings_host(parent):
    win = parent.window() if parent is not None else None
    if win is not None and hasattr(win, "open_settings_dialog"):
        return win
    return parent


def _open_features(parent, dlg: QDialog):
    dlg.reject()
    host = _settings_host(parent)
    if host is not None and hasattr(host, "open_settings_dialog"):
        host.open_settings_dialog("Features")
        return
    try:
        from claynext.gui.dialogs.settings_dialog import SettingsDialog

        SettingsDialog(parent).exec()
    except Exception:
        QMessageBox.information(
            parent,
            "Features",
            "Open Settings → Features to install optional packages.",
        )


def _open_models(parent, dlg: QDialog):
    dlg.reject()
    host = _settings_host(parent)
    if host is not None and hasattr(host, "open_settings_dialog"):
        host.open_settings_dialog("Models")
        return
    try:
        from claynext.gui.dialogs.settings_dialog import SettingsDialog

        SettingsDialog(parent).exec()
    except Exception:
        QMessageBox.information(
            parent,
            "Models",
            "Open Settings → Models to download missing weights.",
        )
