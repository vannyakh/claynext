"""Alert when optional packages or model weights are missing before a job runs."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QThreadPool
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

from claynext.gui.worker import Worker
from claynext.models.env_preflight import (
    format_gaps_message,
    has_blocking_gaps,
    primary_install_command,
)


class _EnvironmentDialog(QDialog):
    """Modal environment alert. Close and Escape wait while an install is running."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._installing = False
        self._installed_ok = False

    def reject(self) -> None:  # type: ignore[override]
        if self._installing:
            return
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._installing:
            event.ignore()
            return
        super().closeEvent(event)


def alert_missing_environment(
    parent,
    gaps: list[dict[str, Any]],
    *,
    title: str = "Environment required",
    recheck: Callable[[], list[dict[str, Any]]] | None = None,
) -> bool:
    """
    Show a download / install alert for missing environment pieces.

    Returns True if the caller may proceed (no gaps, install succeeded, or only
    soft gaps and the user continues).
    Returns False when the user cancels or a blocking package is still missing.
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

    dlg = _EnvironmentDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setMinimumWidth(560)
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
    action_buttons: list[QPushButton] = []
    btn_install: QPushButton | None = None
    if cmd:
        btn_install = QPushButton("Install all")
        btn_install.setObjectName("btn_primary")
        btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_install.setToolTip("Installs every optional extra and keeps them installed together.")
        row.addWidget(btn_install)
        action_buttons.append(btn_install)
        btn_copy = QPushButton("Copy install command")
        btn_copy.setObjectName("btn_secondary")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(lambda: _copy_cmd(cmd, btn_copy))
        row.addWidget(btn_copy)
        action_buttons.append(btn_copy)
    if model_repos:
        btn_dl = QPushButton("Download model…")
        btn_dl.setObjectName("btn_secondary")
        btn_dl.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dl.clicked.connect(lambda: _open_models(parent, dlg))
        row.addWidget(btn_dl)
        action_buttons.append(btn_dl)
    btn_settings = QPushButton("Open Features")
    btn_settings.setObjectName("btn_secondary")
    btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_settings.clicked.connect(lambda: _open_features(parent, dlg))
    row.addWidget(btn_settings)
    action_buttons.append(btn_settings)
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
    if btn_install is not None:
        btn_install.clicked.connect(
            lambda: _start_install_all(
                dlg,
                btn_install,
                buttons,
                action_buttons,
                detail,
                head,
                recheck,
            )
        )

    result = dlg.exec()
    if getattr(dlg, "_installed_ok", False):
        return True
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

    def _recheck() -> list[dict[str, Any]]:
        return collect_job_gaps(
            voice_id=voice_id,
            secondary_voice_id=secondary_voice_id,
            asr_model=asr_model,
            check_stems=check_stems,
        )

    return alert_missing_environment(parent, _recheck(), title=title, recheck=_recheck)


def _start_install_all(
    dlg: QDialog,
    btn_install: QPushButton,
    buttons: QDialogButtonBox,
    action_buttons: list[QPushButton],
    detail: QLabel,
    head: QLabel,
    recheck: Callable[[], list[dict[str, Any]]] | None,
) -> None:
    if getattr(dlg, "_installing", False):
        return
    dlg._installing = True
    buttons.setEnabled(False)
    for btn in action_buttons:
        btn.setEnabled(False)
    btn_install.setText("Installing…")

    def _task(progress_callback=None):
        from claynext.models.features import install_dev_environment

        return install_dev_environment(progress_callback=progress_callback, apply_preferences=True)

    worker = Worker(_task)
    dlg._install_worker = worker

    def _progress(pct: int, _msg: str) -> None:
        if not getattr(dlg, "_installing", False):
            return
        btn_install.setText(f"Installing {max(0, min(100, int(pct)))}%")

    def _restore_actions() -> None:
        dlg._installing = False
        buttons.setEnabled(True)
        for btn in action_buttons:
            btn.setEnabled(True)
        btn_install.setText("Install all")

    def _done(result: object) -> None:
        payload = result if isinstance(result, dict) else {}
        failed = list(payload.get("failed") or [])
        still = list(payload.get("still_missing") or [])
        if failed or still:
            _restore_actions()
            lines = ["Some pieces could not be installed:"]
            seen: set[str] = set()
            for item in failed:
                name = str(item.get("extra") or "extra")
                if name in seen:
                    continue
                seen.add(name)
                err = str(item.get("error") or "install failed")
                lines.append(f"• {name}: {err}")
            for name in still:
                if name in seen:
                    continue
                lines.append(f"• {name}: still not importable")
            if "whisperx" in seen or "whisperx" in {str(name) for name in still}:
                lines.append("Dub can continue with Faster-Whisper if WhisperX is the piece that failed.")
            detail.setText(detail.text() + "\n\n" + "\n".join(lines))
            return
        if recheck is not None:
            try:
                fresh = recheck()
            except Exception:
                fresh = []
            if has_blocking_gaps(fresh):
                _restore_actions()
                detail.setText(format_gaps_message(fresh))
                head.setText("Required environment is not ready. Install the missing package, then retry.")
                return
        dlg._installing = False
        dlg._installed_ok = True
        dlg.accept()

    def _error(err: str, _tb: str) -> None:
        _restore_actions()
        detail.setText(detail.text() + f"\n\nInstall failed:\n{err}")

    worker.signals.progress.connect(_progress)
    worker.signals.result.connect(_done)
    worker.signals.error.connect(_error)
    QThreadPool.globalInstance().start(worker)


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
    if getattr(dlg, "_installing", False):
        return
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
    if getattr(dlg, "_installing", False):
        return
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
