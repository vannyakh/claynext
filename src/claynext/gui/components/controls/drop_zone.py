from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog, QPushButton
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from claynext.gui.icons import icon


class DropZoneWidget(QWidget):
    """
    Drag-and-drop file upload area with a clear empty → loaded state.
    Emits file_dropped(str_path) when the user drops or browses a file.
    """
    file_dropped = Signal(str)

    def __init__(
        self,
        title: str = "Drag & Drop Media File Here",
        subtitle: str = "Supports MP4, MKV, AVI, MOV, MP3, WAV, FLAC",
        accepted_extensions=None,
    ):
        super().__init__()
        self.accepted_extensions = accepted_extensions or [
            ".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav",
            ".flac", ".png", ".jpg", ".jpeg", ".srt", ".vtt",
        ]
        self.setAcceptDrops(True)
        self.setObjectName("drop_zone")
        self.setProperty("loaded", False)
        self.init_ui(title, subtitle)

    def init_ui(self, title: str, subtitle: str):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 28, 20, 28)
        layout.setSpacing(8)

        self.icon_lbl = QLabel()
        self.icon_lbl.setObjectName("drop_zone_icon")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setPixmap(icon("folder", color="#64748b", size=28).pixmap(28, 28))
        layout.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("drop_zone_title")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setWordWrap(True)

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("drop_zone_sub")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setWordWrap(True)

        self.file_lbl = QLabel("")
        self.file_lbl.setObjectName("drop_zone_file")
        self.file_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_lbl.hide()

        self.btn_browse = QPushButton("Browse Files")
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.setObjectName("btn_secondary")
        self.btn_browse.setMinimumWidth(128)
        self.btn_browse.clicked.connect(self.browse_files)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.sub_lbl)
        layout.addWidget(self.file_lbl)
        layout.addSpacing(4)
        layout.addWidget(self.btn_browse, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_loaded(self, file_path: str):
        """Mark the drop zone as having a selected file."""
        name = file_path.split("/")[-1].split("\\")[-1]
        self.file_lbl.setText(name)
        self.file_lbl.show()
        self.title_lbl.setText("File ready")
        self.sub_lbl.setText("Drop another file to replace, or browse again")
        self.icon_lbl.setPixmap(icon("folder", color="#34d399", size=28).pixmap(28, 28))
        self.setProperty("loaded", True)
        self.style().unpolish(self)
        self.style().polish(self)

    def clear(self):
        self.file_lbl.hide()
        self.file_lbl.setText("")
        self.setProperty("loaded", False)
        self.icon_lbl.setPixmap(icon("folder", color="#64748b", size=28).pixmap(28, 28))
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            self.set_loaded(file_path)
            self.file_dropped.emit(file_path)

    def browse_files(self):
        ext_filter = (
            "All Supported Files (*.mp4 *.mkv *.avi *.mov *.mp3 *.wav *.flac *.png *.jpg *.jpeg *.srt *.vtt);;"
            "Video Files (*.mp4 *.mkv *.avi *.mov);;"
            "Audio Files (*.mp3 *.wav *.flac);;"
            "All Files (*.*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Media File", "", ext_filter)
        if file_path:
            self.set_loaded(file_path)
            self.file_dropped.emit(file_path)

