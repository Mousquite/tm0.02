import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QHBoxLayout,
    QFileDialog, QLineEdit, QLabel, QComboBox
)
from table_manager import TokenTableWidget
import config
from logger import logger

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Token Manager")
        self.resize(1200, 800)
        self.table = TokenTableWidget()

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        btn_layout = QHBoxLayout()

        # Boutons principaux
        load_btn = QPushButton("📂 Charger")
        save_btn = QPushButton("💾 Sauvegarder")
        undo_btn = QPushButton("↩️ Undo")
        redo_btn = QPushButton("↪️ Redo")
        select_all_btn = QPushButton("☑️ Tout cocher")

        # Champs recherche et filtre
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filtre ex: chain = base + owned > 0")

        self.selection_combo = QComboBox()
        self.selection_combo.addItem("Selection actuelle")  # Placeholder, ajouter favoris plus tard

        apply_filter_btn = QPushButton("🔍 Appliquer filtre")
        save_selection_btn = QPushButton("💾 Sauver sélection")
        load_selection_btn = QPushButton("📂 Charger sélection")

        # Connecter les boutons
        load_btn.clicked.connect(self.load_file)
        save_btn.clicked.connect(self.save_file)
        undo_btn.clicked.connect(self.table.undo)
        redo_btn.clicked.connect(self.table.redo)
        select_all_btn.clicked.connect(self.table.select_all_visible)
        apply_filter_btn.clicked.connect(self.apply_filter)

        # Ajouter au layout
        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(undo_btn)
        btn_layout.addWidget(redo_btn)
        btn_layout.addWidget(select_all_btn)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("🔎 Filtre:"))
        filter_layout.addWidget(self.filter_input)
        filter_layout.addWidget(apply_filter_btn)
        filter_layout.addWidget(self.selection_combo)
        filter_layout.addWidget(save_selection_btn)
        filter_layout.addWidget(load_selection_btn)

        layout.addLayout(btn_layout)
        layout.addLayout(filter_layout)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_file(self):
        self.table.load_data()

    def save_file(self):
        self.table.save_data()
            

    def apply_filter(self):
        filter_text = self.filter_input.text()
        self.table.apply_filter(filter_text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
