import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QHBoxLayout,
    QLineEdit, QLabel, QComboBox, QMenu, QCompleter, QAbstractItemView
)
from PyQt5.QtCore import Qt
from table_manager import TokenTableWidget
import config
from logger import logger
import json

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Token Manager")
        self.resize(1200, 800)
        self.table = TokenTableWidget(self)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.show_header_menu)

        # Rendre les en-têtes de colonnes déplaçables
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.setDragDropMode(QAbstractItemView.InternalMove)
        # connection des signaux 
        header.sectionMoved.connect(self.table.on_section_moved)
        header.sectionResized.connect(self.table.on_section_resized)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        btn_layout = QHBoxLayout()

        # Boutons principaux
        load_btn = QPushButton("📂 Charger")
        save_btn = QPushButton("💾 Sauvegarder")
        undo_btn = QPushButton("↩ Undo")
        redo_btn = QPushButton("↪ Redo")
        select_all_btn = QPushButton("v Tout cocher")

        # Champ de recherche rapide
        self.quick_search_input = QLineEdit()
        self.quick_search_input.setPlaceholderText("🔎 Recherche rapide (insensible à la casse)")
        self.quick_search_input.textChanged.connect(self.table.filter_table)

        # Champs recherche et filtre
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Ex: col1 > 10 and col2 == 'test'")

        self.selection_combo = QComboBox()
        self.selection_combo.addItem("Selection actuelle")  # Placeholder, ajouter favoris plus tard

        # Bouton appliquer filtre
        apply_filter_btn = QPushButton("🔍 Appliquer filtre")
        apply_filter_btn.clicked.connect(lambda: self.table.apply_filter(self.filter_input.text()))
        self.result_counter = QLabel("0 lignes visibles")
         # Autocomplétion des noms de colonnes dans le filtre
        completer = QCompleter(self.table.df.columns.tolist())
        completer.setCaseSensitivity(False)
        self.filter_input.setCompleter(completer)

        # Bouton réinitialiser les filtres
        reset_filters_btn = QPushButton("🧹 Réinitialiser filtres")
        reset_filters_btn.clicked.connect(self.reset_filters)

        # Boutons sauvegarder/charger sélection (optionnel)
        save_selection_btn = QPushButton("💾 Sauver sélection")
        load_selection_btn = QPushButton("📂 Charger sélection")

        # Connecter les boutons
        load_btn.clicked.connect(self.load_file)
        save_btn.clicked.connect(self.save_file)
        undo_btn.clicked.connect(self.table.undo)
        redo_btn.clicked.connect(self.table.redo)
        #select_all_btn.clicked.connect(self.table.select_all_visible)

        # Ajouter au layout
        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(undo_btn)
        btn_layout.addWidget(redo_btn)
        btn_layout.addWidget(select_all_btn)

        quick_search_layout = QHBoxLayout()
        quick_search_layout.addWidget(QLabel("🔎 Recherche:"))
        quick_search_layout.addWidget(self.quick_search_input)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("🔎 Filtre:"))
        filter_layout.addWidget(self.filter_input)
        filter_layout.addWidget(apply_filter_btn)
        filter_layout.addWidget(reset_filters_btn)
        filter_layout.addWidget(self.result_counter)
        filter_layout.addWidget(self.selection_combo)
        filter_layout.addWidget(save_selection_btn)
        filter_layout.addWidget(load_selection_btn)

        layout.addLayout(btn_layout)
        layout.addLayout(filter_layout)
        layout.addLayout(quick_search_layout)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_file(self):
        self.table.load_data()                       # charge df depuis fichier
        self.table.update_visible_counter()
        
        self.table.update_table_from_df()            # remplit la QTableWidget
        self.load_table_settings()                   # applique les réglages d'affichage
        self.table.update_df_from_table()

    def save_file(self):
        self.table.save_data()
        self.save_table_settings()
            
    def reset_filters(self):
        self.quick_search_input.clear()
        self.filter_input.clear()
        self.table.reset_filters()
        
    def update_filter_autocompletion(self):
        column_names_with_types = []
        for col in self.table.df.columns:
            # Appliquer la fonction type à chaque élément de la colonne
            types = self.table.df[col].apply(type)

            # Compter la fréquence de chaque type de données
            type_counts = types.value_counts()

            if not type_counts.empty:
                # Trouver le type de données le plus fréquent
                most_common_type = type_counts.idxmax()
                col_type = most_common_type.__name__
            else:
                # Si la colonne est vide, définir le type comme 'unknown'
                col_type = 'unknown'

            column_names_with_types.append(f"{col} ({col_type})")

        completer = QCompleter(column_names_with_types)
        completer.setCaseSensitivity(False)
        self.filter_input.setCompleter(completer)
        
    def show_header_menu(self, position):
        header = self.table.horizontalHeader()
        col = header.logicalIndexAt(position)
        if col < 0:
            return

        menu = QMenu()
        rename_action = menu.addAction("✏️ Renommer la colonne")
        hide_action = menu.addAction("🙈 Masquer la colonne")
        show_hidden_action = menu.addAction("👁️ Afficher les colonnes masquées...")

        action = menu.exec_(header.mapToGlobal(position))

        if action == rename_action:
            self.table.rename_column(col)
        elif action == hide_action:
            self.table.hide_column(col)
        elif action == show_hidden_action:
            self.table.show_hidden_columns_menu()

    def load_table_settings(self, path="table_settings.json"):
        try:
            with open(path, "r") as f:
                settings = json.load(f)

            header = self.table.horizontalHeader()

            # Ordre des colonnes (mapping logique → visuelle)
            if "column_order" in settings:
                for logical, visual in enumerate(settings["column_order"]):
                    if 0 <= logical < header.count() and 0 <= visual < header.count():
                        header.moveSection(header.visualIndex(logical), visual)

            # Colonnes masquées
            if "hidden_columns" in settings:
                self.table.hidden_columns = set(settings["hidden_columns"])
                for i in range(self.table.columnCount()):
                    self.table.setColumnHidden(i, i in self.table.hidden_columns)

            # Largeurs de colonnes
            if "column_widths" in settings:
                for i_str, width in settings["column_widths"].items():
                    i = int(i_str)
                    if 0 <= i < self.table.columnCount():
                        self.table.setColumnWidth(i, width)

        except Exception as e:
            print(f"Erreur lors du chargement des préférences d'affichage : {e}")

    def save_table_settings(self, path="table_settings.json"):
        header = self.table.horizontalHeader()
        settings = {
            "column_order": [header.visualIndex(i) for i in range(header.count())],
            "hidden_columns": [i for i in range(self.table.columnCount()) if self.table.isColumnHidden(i)],
            "column_widths": {str(i): self.table.columnWidth(i) for i in range(self.table.columnCount())}
        }
        with open(path, "w") as f:
            json.dump(settings, f)    


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
