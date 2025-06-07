# table_manager.py

import pandas as pd
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt5.QtCore import Qt

from logger import logger

class TokenTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # MainWindow
        self.df = pd.DataFrame()
        self.history = []
        self.redo_stack = []
        self.locked_cells = set()  # (row, col)
        self.active_filter = None
        self.filtered_index = []

        self.setup_table()

    # ========== SETUP ========== #
    def setup_table(self):
        self.setColumnCount(0)
        self.setRowCount(0)
        self.setSortingEnabled(True)

    # ========== DATA MANAGEMENT ========== #
    def load_data(self):
        """
        Chargement automatique depuis un fichier CSV ou Excel.
        """
        try:
            self.df = pd.read_excel("data.xlsx")  # ou CSV si tu préfères
            self.update_table_from_df()
            logger.info("✅ Données chargées depuis le fichier.")
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement des données : {e}")

    def save_data(self):
        """
        Sauvegarde manuelle dans Excel.
        """
        try:
            self.update_df_from_table()
            self.df.to_excel("data.xlsx", index=False)
            logger.info("💾 Données sauvegardées.")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la sauvegarde : {e}")

    def export_selected(self):
        """
        Exporte uniquement les lignes cochées dans un nouveau fichier Excel.
        """
        try:
            selected_rows = self.get_checked_rows()
            export_df = self.df.iloc[selected_rows]
            export_df.to_excel("export.xlsx", index=False)
            logger.info(f"📤 {len(export_df)} lignes exportées.")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'export : {e}")

    # ========== UNDO / REDO ========== #
    def undo(self):
        if self.history:
            self.redo_stack.append(self.df.copy())
            self.df = self.history.pop()
            self.update_table_from_df()
            logger.info("↩️ Undo effectué.")
        else:
            logger.warning("⚠️ Aucun historique pour undo.")

    def redo(self):
        if self.redo_stack:
            self.history.append(self.df.copy())
            self.df = self.redo_stack.pop()
            self.update_table_from_df()
            logger.info("↪️ Redo effectué.")
        else:
            logger.warning("⚠️ Aucun historique pour redo.")

    def backup(self):
        """
        Sauvegarde l’état courant du DataFrame.
        """
        self.history.append(self.df.copy())
        self.redo_stack.clear()

    # ========== TABLE <-> DF SYNCHRONISATION ========== #
    def update_table_from_df(self):
        """
        Affiche le DataFrame dans la table, selon le filtre actif.
        """
        self.setRowCount(0)
        self.setColumnCount(0)

        df = self.apply_active_filter(self.df)

        self.setColumnCount(len(df.columns))
        self.setHorizontalHeaderLabels(df.columns)

        self.setRowCount(len(df))
        for row in range(len(df)):
            for col, value in enumerate(df.iloc[row]):
                item = QTableWidgetItem(str(value) if pd.notna(value) else "")
                if (row, col) in self.locked_cells:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row, col, item)

        self.filtered_index = df.index.tolist()

    def update_df_from_table(self):
        """
        Met à jour le DataFrame à partir de la table (hors cases verrouillées).
        """
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                if (row, col) in self.locked_cells:
                    continue
                item = self.item(row, col)
                value = item.text() if item else ""
                self.df.iat[row, col] = value if value != "" else None

    # ========== VERROUILLAGE ========== #
    def lock_cell(self, row, col):
        self.locked_cells.add((row, col))
        item = self.item(row, col)
        if item:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def unlock_cell(self, row, col):
        self.locked_cells.discard((row, col))
        item = self.item(row, col)
        if item:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

    # ========== FILTRAGE ========== #
    def apply_active_filter(self, df):
        """
        Applique le filtre libre courant. Retourne un DataFrame filtré.
        """
        if not self.active_filter:
            return df
        try:
            filtered_df = df.query(self.active_filter)
            logger.info(f"🔍 Filtre appliqué : {self.active_filter} ({len(filtered_df)} lignes)")
            return filtered_df
        except Exception as e:
            logger.warning(f"❌ Erreur dans le filtre : {e}")
            return df

    def set_filter(self, query_str):
        self.active_filter = query_str
        self.update_table_from_df()

    # ========== UTILITAIRES ========== #
    def get_checked_rows(self):
        """
        Renvoie les index des lignes cochées (si colonne dédiée aux cases cochées ajoutée).
        """
        if '✔️' not in self.df.columns:
            return []
        return self.df.index[self.df['✔️'] == True].tolist()
    
    # ========== AJOUT / SUPPRESSION DE LIGNES & COLONNES ========== #
    def add_row(self):
        self.backup()
        empty_row = pd.Series([None] * len(self.df.columns), index=self.df.columns)
        self.df = pd.concat([self.df, empty_row.to_frame().T], ignore_index=True)
        logger.info("➕ Ligne ajoutée.")
        self.update_table_from_df()

    def delete_row(self, row_idx):
        if 0 <= row_idx < len(self.df):
            self.backup()
            self.df.drop(index=self.filtered_index[row_idx], inplace=True)
            self.df.reset_index(drop=True, inplace=True)
            logger.info(f"🗑️ Ligne {row_idx} supprimée.")
            self.update_table_from_df()

    def add_column(self, column_name, default_value=None):
        if column_name not in self.df.columns:
            self.backup()
            self.df[column_name] = default_value
            logger.info(f"➕ Colonne '{column_name}' ajoutée avec valeur : {default_value}")
            self.update_table_from_df()

    def delete_column(self, column_name):
        if column_name in self.df.columns:
            self.backup()
            self.df.drop(columns=[column_name], inplace=True)
            logger.info(f"🗑️ Colonne '{column_name}' supprimée.")
            self.update_table_from_df()

    def rename_column(self, old_name, new_name):
        if old_name in self.df.columns:
            self.backup()
            self.df.rename(columns={old_name: new_name}, inplace=True)
            logger.info(f"🔤 Colonne renommée : {old_name} → {new_name}")
            self.update_table_from_df()

    def hide_column(self, column_name):
        col_index = self.df.columns.get_loc(column_name)
        self.setColumnHidden(col_index, True)
        logger.info(f"🙈 Colonne masquée : {column_name}")

    def show_column(self, column_name):
        col_index = self.df.columns.get_loc(column_name)
        self.setColumnHidden(col_index, False)
        logger.info(f"👀 Colonne affichée : {column_name}")

    # ========== TRI & DEPLACEMENT DE COLONNES ========== #
    def move_column(self, from_index, to_index):
        cols = list(self.df.columns)
        if 0 <= from_index < len(cols) and 0 <= to_index < len(cols):
            self.backup()
            col = cols.pop(from_index)
            cols.insert(to_index, col)
            self.df = self.df[cols]
            logger.info(f"↔️ Colonne déplacée : {col} de {from_index} à {to_index}")
            self.update_table_from_df()

    def sort_by_column(self, column_name, ascending=True):
        if column_name in self.df.columns:
            self.backup()
            self.df.sort_values(by=column_name, ascending=ascending, inplace=True)
            logger.info(f"🔢 Trié par '{column_name}' (asc={ascending})")
            self.update_table_from_df()

    # ========== APPLICATION DE VALEUR COMMUNE ========== #
    def apply_value_to_selection(self, column_name, value):
        """
        Applique une valeur à toutes les lignes cochées dans une colonne donnée.
        """
        if column_name not in self.df.columns:
            logger.warning(f"⚠️ Colonne inconnue : {column_name}")
            return
        self.backup()
        selected_rows = self.get_checked_rows()
        for row in selected_rows:
            if (row, self.df.columns.get_loc(column_name)) not in self.locked_cells:
                self.df.at[row, column_name] = value
        logger.info(f"🖊️ Valeur '{value}' appliquée à {len(selected_rows)} lignes dans '{column_name}'")
        self.update_table_from_df()

    def apply_value_and_create_column(self, column_name, value):
        """
        Crée une colonne avec la valeur donnée pour les lignes cochées.
        """
        self.backup()
        if column_name not in self.df.columns:
            self.df[column_name] = None
        selected_rows = self.get_checked_rows()
        for row in selected_rows:
            if (row, self.df.columns.get_loc(column_name)) not in self.locked_cells:
                self.df.at[row, column_name] = value
        logger.info(f"🆕 Colonne '{column_name}' créée / modifiée avec '{value}' pour {len(selected_rows)} lignes")
        self.update_table_from_df()

    # ========== SÉLECTION RAPIDE ========== #
    def select_all_visible(self):
        """
        Coche toutes les lignes actuellement visibles (en fonction du filtre).
        """
        if '✔️' not in self.df.columns:
            self.df['✔️'] = False
        for i in self.filtered_index:
            self.df.at[i, '✔️'] = True
        logger.info(f"☑️ {len(self.filtered_index)} lignes cochées.")
        self.update_table_from_df()