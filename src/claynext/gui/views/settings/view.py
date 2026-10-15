from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QFrame, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt
from claynext.utils.config import DEFAULT_CONFIG, DATA_DIR, MODELS_DIR, OUTPUTS_DIR


class SettingsView(QWidget):
    """
    Settings & Model Directory Manager View.
    """
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Header Title Card
        header_card = QFrame()
        header_card.setProperty("class", "card")
        h_layout = QHBoxLayout(header_card)

        t_box = QVBoxLayout()
        lbl_title = QLabel("Settings & Neural Model Manager")
        lbl_title.setProperty("class", "section_title")
        lbl_desc = QLabel("Configure hardware acceleration device, local model directories, and export paths.")
        lbl_desc.setProperty("class", "label_muted")
        t_box.addWidget(lbl_title)
        t_box.addWidget(lbl_desc)

        h_layout.addLayout(t_box)
        layout.addWidget(header_card)

        # Settings Form Card
        settings_card = QFrame()
        settings_card.setProperty("class", "card")
        s_layout = QVBoxLayout(settings_card)
        s_layout.setSpacing(16)

        lbl_device = QLabel("Hardware Execution Device:")
        lbl_device.setStyleSheet("color: #f1f5f9; font-weight: 700;")
        self.combo_device = QComboBox()
        self.combo_device.addItems(["CUDA (NVIDIA GPU)", "DirectML (AMD / Intel GPU)", "CPU Threadpool (Fallback)"])
        self.combo_device.setCurrentText("CUDA (NVIDIA GPU)")

        s_layout.addWidget(lbl_device)
        s_layout.addWidget(self.combo_device)

        lbl_models_path = QLabel("Local AI Models Cache Directory:")
        lbl_models_path.setStyleSheet("color: #f1f5f9; font-weight: 700;")
        
        models_box = QHBoxLayout()
        self.txt_models_dir = QLineEdit(str(MODELS_DIR))
        btn_browse_models = QPushButton("Browse")
        btn_browse_models.setObjectName("btn_secondary")
        btn_browse_models.clicked.connect(lambda: self.browse_folder(self.txt_models_dir))

        models_box.addWidget(self.txt_models_dir)
        models_box.addWidget(btn_browse_models)

        s_layout.addWidget(lbl_models_path)
        s_layout.addLayout(models_box)

        lbl_outputs_path = QLabel("Default Export Output Directory:")
        lbl_outputs_path.setStyleSheet("color: #f1f5f9; font-weight: 700;")
        
        outputs_box = QHBoxLayout()
        self.txt_outputs_dir = QLineEdit(str(OUTPUTS_DIR))
        btn_browse_outputs = QPushButton("Browse")
        btn_browse_outputs.setObjectName("btn_secondary")
        btn_browse_outputs.clicked.connect(lambda: self.browse_folder(self.txt_outputs_dir))

        outputs_box.addWidget(self.txt_outputs_dir)
        outputs_box.addWidget(btn_browse_outputs)

        s_layout.addWidget(lbl_outputs_path)
        s_layout.addLayout(outputs_box)

        btn_save = QPushButton("Save & Apply Configuration")
        btn_save.setObjectName("btn_primary")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.save_config)

        s_layout.addStretch()
        s_layout.addWidget(btn_save, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(settings_card)

    def browse_folder(self, target_line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", target_line_edit.text())
        if folder:
            target_line_edit.setText(folder)

    def save_config(self):
        QMessageBox.information(self, "Settings Saved", "Configuration updated successfully!")
