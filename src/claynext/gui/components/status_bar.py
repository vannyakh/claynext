import os
import threading
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, Signal

from claynext.constants import STATUSBAR_HEIGHT
from claynext.constants.theme_constants import COLOR_TEXT_SUB, COLOR_TEXT_MUTED, COLOR_PRIMARY, COLOR_BORDER
from claynext.adapters import sysinfo_adapter as sysinfo
from claynext.gui.icons import get_icon


class CustomStatusBar(QWidget):
    """
    CamDot-inspired System Monitor Status Bar.
    Real-time displays for GPU, CPU load, RAM usage, Disk space, Process memory, and active tool.
    """
    gpu_detected_signal = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("custom_status_bar")
        self.setFixedHeight(STATUSBAR_HEIGHT)
        
        self.stats = {}
        self._stat_cells = {}
        self._cpu_meter = sysinfo.CpuMeter()
        
        self.init_ui()
        self.gpu_detected_signal.connect(self._on_gpu_detected)
        
        # Initial GPU detection in background thread
        threading.Thread(target=self._detect_gpu, daemon=True).start()

        # Timer for polling system metrics (1.5s interval)
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(1500)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start()

        # First refresh
        self._refresh_stats()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        # Left Items: System hardware meters (GPU, CPU, RAM, Disk)
        for key, icon_name, tooltip, sample in (
            ("gpu", "gpu", "Looking for graphics adapter...", "NVIDIA GeForce RTX 3080"),
            ("cpu", "cpu", sysinfo.cpu_label(), "100%"),
            ("ram", "activity", "Memory in use on this machine", "16.0 GB / 32.0 GB"),
            ("disk", "folder", "Free space on workspace drive", "100.0 GB free on C:"),
        ):
            layout.addWidget(self._create_stat_cell(key, icon_name, tooltip, sample))

        # Status Message
        self.lbl_msg = QLabel("Ready")
        self.lbl_msg.setStyleSheet(f"color: {COLOR_TEXT_SUB}; font-size: 11px; padding-left: 6px;")
        layout.addWidget(self.lbl_msg)

        layout.addStretch()

        # Right Items: Active tool, Process memory/threads, version info
        self.lbl_active_tool = QLabel("AI Transcript")
        self.lbl_active_tool.setStyleSheet(
            f"color: {COLOR_PRIMARY}; font-weight: 700; font-size: 11px; margin-right: 6px;"
        )
        layout.addWidget(self.lbl_active_tool)

        # Process stat
        layout.addWidget(self._create_stat_cell("process", "log", "Memory & threads used by Claynext Studio", "128 MB · 12 thread(s)"))

        # Version tag
        self.lbl_ver = QLabel("v1.0.0")
        self.lbl_ver.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 3px; background: rgba(255,255,255,0.04);"
        )
        layout.addWidget(self.lbl_ver)

    def _create_stat_cell(self, key: str, icon_name: str, tooltip: str, sample: str = "") -> QWidget:
        cell = QWidget()
        row = QHBoxLayout(cell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        icon_lbl = QLabel()
        pixmap = get_icon(icon_name, color=COLOR_TEXT_SUB, size=14).pixmap(14, 14)
        icon_lbl.setPixmap(pixmap)

        value_lbl = QLabel("—")
        value_lbl.setStyleSheet(f"color: {COLOR_TEXT_SUB}; font-size: 11px; font-weight: 500;")
        
        if sample:
            min_w = value_lbl.fontMetrics().horizontalAdvance(sample)
            value_lbl.setMinimumWidth(min_w)

        row.addWidget(icon_lbl)
        row.addWidget(value_lbl)

        self.stats[key] = value_lbl
        self._stat_cells[key] = cell
        self._set_stat(key, "—", tooltip)
        return cell

    def _set_stat(self, key: str, text: str, tooltip: str = ""):
        if key in self.stats:
            self.stats[key].setText(text)
        if tooltip and key in self._stat_cells:
            cell = self._stat_cells[key]
            cell.setToolTip(tooltip)
            for child in cell.findChildren(QLabel):
                child.setToolTip(tooltip)

    def _detect_gpu(self):
        label, tooltip = sysinfo.gpu_summary()
        self.gpu_detected_signal.emit(label, tooltip)

    def _on_gpu_detected(self, label: str, tooltip: str):
        self._set_stat("gpu", label, tooltip)

    def _refresh_stats(self):
        # CPU
        percent = self._cpu_meter.percent()
        cores = os.cpu_count() or 0
        self._set_stat(
            "cpu",
            "—" if percent is None else f"{percent:.0f}%",
            f"CPU load across {cores} logical core(s)" if cores else "CPU load",
        )

        # RAM
        ram = sysinfo.memory()
        if ram and ram[1]:
            used, total = ram
            self._set_stat(
                "ram",
                f"{sysinfo.human_bytes(used)} / {sysinfo.human_bytes(total)}" if used else sysinfo.human_bytes(total),
                f"{sysinfo.human_bytes(used)} of {sysinfo.human_bytes(total)} RAM in use ({used / total:.0%})"
                if used else f"{sysinfo.human_bytes(total)} of RAM installed",
            )

        # Disk
        space = sysinfo.disk()
        if space:
            free, total = space
            root = sysinfo.volume_name()
            self._set_stat(
                "disk",
                f"{sysinfo.human_bytes(free)} free on {root}",
                f"{sysinfo.human_bytes(free)} free of {sysinfo.human_bytes(total)} total on {root}",
            )

        # App Process Memory
        label, tooltip = sysinfo.process_summary()
        self._set_stat("process", label, tooltip)

    def set_status_message(self, msg: str):
        self.lbl_msg.setText(msg)

    def set_active_tool_name(self, name: str):
        self.lbl_active_tool.setText(name)

