from PyQt5.QtWidgets import QMenu, QInputDialog, QMessageBox, QTableWidgetItem, QTableWidget, QApplication
from PyQt5.QtCore import Qt, QPoint
import pandas as pd

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
        """Annulation avec préservation du filtre actif"""
        if self.history:
            self.redo_stack.append(self.df.copy())
            self.df = self.history.pop()
            
            # Conserver le filtre actif
            active_filter = self.active_filter
            self.update_table_from_df()
            self.active_filter = active_filter
            
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
                self.df.iat[self.filtered_index[row], col] = value if value != "" else None

    # ========== VERROUILLAGE ========== #
    def lock_cell(self, row, col):
        """Verrouille une cellule en utilisant l'index original du DataFrame"""
        original_index = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        self.locked_cells.add((original_index, col))
        
        item = self.item(row, col)
        if item:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            font = item.font()
            font.setBold(True)
            item.setFont(font)

    def unlock_cell(self, row, col):
        """Déverrouille une cellule en utilisant l'index original du DataFrame"""
        original_index = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        self.locked_cells.discard((original_index, col))
        
        item = self.item(row, col)
        if item:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            font = item.font()
            font.setBold(False)
            item.setFont(font)

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
    def add_row(self, index=None):
        """Ajoute une ligne au DataFrame avec gestion de l'index"""
        self.backup()
        empty_row = pd.Series([None] * len(self.df.columns), index=self.df.columns)
        
        if index is None or index >= len(self.df):
            self.df = pd.concat([self.df, empty_row.to_frame().T], ignore_index=True)
        else:
            top = self.df.iloc[:index]
            bottom = self.df.iloc[index:]
            self.df = pd.concat([top, empty_row.to_frame().T, bottom], ignore_index=True)
        
        logger.info(f"➕ Ligne ajoutée à l'index {index if index is not None else len(self.df)-1}")
        self.update_table_from_df()

    def delete_row(self, row_idx):
        """Supprime une ligne du DataFrame"""
        if 0 <= row_idx < len(self.df):
            self.backup()
            self.df.drop(index=self.filtered_index[row_idx], inplace=True)
            self.df.reset_index(drop=True, inplace=True)
            logger.info(f"🗑️ Ligne {row_idx} supprimée.")
            self.update_table_from_df()

    def add_column(self, column_name, default_value=None):
        """Ajoute une colonne au DataFrame"""
        if column_name not in self.df.columns:
            self.backup()
            self.df[column_name] = default_value
            logger.info(f"➕ Colonne '{column_name}' ajoutée avec valeur : {default_value}")
            self.update_table_from_df()

    def delete_column(self, column_name):
        """Supprime une colonne du DataFrame"""
        if column_name in self.df.columns:
            self.backup()
            self.df.drop(columns=[column_name], inplace=True)
            logger.info(f"🗑️ Colonne '{column_name}' supprimée.")
            self.update_table_from_df()

    def rename_column(self, col):
        old_name = self.horizontalHeaderItem(col).text()
        new_name, ok = QInputDialog.getText(self, "Renommer la colonne", f"Nom actuel : {old_name}\nNouveau nom :")
        if ok and new_name and new_name != old_name:
            self.backup()
            self.df.rename(columns={old_name: new_name}, inplace=True)
            logger.info(f"✏️ Colonne renommée de '{old_name}' à '{new_name}'")
            self.update_table_from_df()

    def hide_column(self, col):
        self.setColumnHidden(col, True)
        logger.info(f"Colonne {col} masquée")

    def show_column(self, col):
        self.setColumnHidden(col, False)
        logger.info(f"Colonne {col} affichée")

    def show_hidden_columns_menu(self):
        hidden_columns = [
            (i, self.horizontalHeaderItem(i).text())
            for i in range(self.columnCount())
            if self.isColumnHidden(i)
        ]
        if not hidden_columns:
            QMessageBox.information(self, "Colonnes masquées", "Aucune colonne masquée.")
            return

        items = [f"{name} (col {i})" for i, name in hidden_columns]
        selected, ok = QInputDialog.getItem(
            self, "Afficher une colonne masquée", "Colonnes disponibles :", items, editable=False
        )
        if ok and selected:
            col_num = int(selected.split("col")[-1].strip(")"))
            self.show_column(col_num)


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

    def duplicate_row(self, index):
        """Duplique une ligne dans le DataFrame"""
        if index < 0 or index >= len(self.df):
            logger.warning("Index de ligne invalide pour duplication.")
            return

        self.backup()
        row_data = self.df.iloc[index].copy()
        self.df = pd.concat([
            self.df.iloc[:index+1], 
            pd.DataFrame([row_data]), 
            self.df.iloc[index+1:]
        ], ignore_index=True)
        
        logger.info(f"📄 Ligne {index} dupliquée à l'index {index+1}")
        self.update_table_from_df()

    def delete_selected_rows(self):
        """Supprime les lignes sélectionnées en synchronisant avec le DataFrame"""
        selected_indexes = self.selectedIndexes()
        if not selected_indexes:
            return
        
        # Obtenir les indices originaux du DataFrame
        selected_rows = sorted(set(
            self.filtered_index[index.row()] 
            if hasattr(self, 'filtered_index') and index.row() < len(self.filtered_index)
            else index.row()
            for index in selected_indexes
        ), reverse=True)
        
        self.backup()
        self.df.drop(index=selected_rows, inplace=True)
        self.df.reset_index(drop=True, inplace=True)
        
        logger.info(f"🗑️ {len(selected_rows)} lignes sélectionnées supprimées")
        self.update_table_from_df()

    def delete_column(self, index):
        """
        Supprime la colonne spécifiée.
        """
        if index < 0 or index >= self.columnCount():
            logger.warning("Index de colonne invalide pour suppression.")
            return

        header = self.horizontalHeaderItem(index).text() if self.horizontalHeaderItem(index) else f"Colonne {index}"
        self.removeColumn(index)

        logger.info(f"Colonne supprimée : {header} (index {index})")

    def check_rows_from_selected_cells(self):
        """
        Coche les lignes associées aux cellules sélectionnées.
        """
        if self.checkbox_column is None:
            logger.warning("Colonne de coche non définie.")
            return

        rows = set(index.row() for index in self.selectedIndexes())
        for row in rows:
            item = self.item(row, self.checkbox_column)
            if item:
                item.setText("✔️")
            else:
                self.setItem(row, self.checkbox_column, QTableWidgetItem("✔️"))

        logger.info(f"{len(rows)} ligne(s) cochée(s)")

    def copy_selected_cells(self):
        """
        Copie les cellules sélectionnées dans le presse-papier (compatible Excel).
        """
        selection = self.selectedRanges()
        if not selection:
            return

        copied_text = ""
        for range_ in selection:
            for row in range(range_.topRow(), range_.bottomRow() + 1):
                row_data = []
                for col in range(range_.leftColumn(), range_.rightColumn() + 1):
                    item = self.item(row, col)
                    row_data.append(item.text() if item else "")
                copied_text += "\t".join(row_data) + "\n"

        clipboard = QApplication.clipboard()
        clipboard.setText(copied_text.strip())

        logger.info("Cellules copiées dans le presse-papier")

    def clear_selected_cells(self):
        """
        Efface le contenu des cellules sélectionnées, sauf si elles sont verrouillées.
        """
        for index in self.selectedIndexes():
            item = self.item(index.row(), index.column())
            if item and (item.flags() & Qt.ItemIsEditable):
                item.setText("")
            else:
                logger.debug(f"Cellule {index.row()}, {index.column()} non effacée (verrouillée ou vide)")

        logger.info("Cellules sélectionnées effacées (si non verrouillées)")

    def contextMenuEvent(self, event):
        pos = event.pos()
        index = self.indexAt(pos)

        if not index.isValid():
            return

        menu = QMenu(self)

        # Gestion des lignes
        menu.addAction("➕ Ajouter une ligne vide", lambda: self.add_row(index.row()))
        menu.addAction("📄 Dupliquer la ligne", lambda: self.duplicate_row(index.row()))
        menu.addAction("🗑️ Supprimer les lignes sélectionnées", self.delete_selected_rows)

        # Colonnes
        menu.addSeparator()
        menu.addAction("➕ Ajouter une colonne", self.prompt_add_column)
        menu.addAction("🗑️ Supprimer la colonne sélectionnée", lambda: self.delete_column(index.column()))

        # Cellules
        menu.addSeparator()
        menu.addAction("🔒 Verrouiller les cellules sélectionnées", self.lock_selected_cells)
        menu.addAction("🔓 Déverrouiller les cellules sélectionnées", self.unlock_selected_cells)

        # Lignes cochées
        menu.addSeparator()
        menu.addAction("✅ Cocher les lignes sélectionnées", self.check_rows_from_selected_cells)

        # Presse-papier
        menu.addSeparator()
        menu.addAction("📋 Copier", self.copy_selected_cells)
        menu.addAction("🧹 Effacer (protégé si verrouillé)", self.clear_selected_cells)

        menu.exec_(self.viewport().mapToGlobal(pos))

    def clone_item(self, item):
        new_item = QTableWidgetItem(item.text())
        new_item.setFlags(item.flags())
        new_item.setFont(item.font())
        new_item.setBackground(item.background())
        return new_item

    def lock_cell(self, row, column):
        item = self.item(row, column)
        if not item:
            item = QTableWidgetItem()
            self.setItem(row, column, item)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    
    def unlock_cell(self, row, column):
        item = self.item(row, column)
        if item:
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            font = item.font()
            font.setBold(False)
            item.setFont(font)

    def lock_selected_cells(self):
        for index in self.selectedIndexes():
            self.lock_cell(index.row(), index.column())
        logger.info("Cellules sélectionnées verrouillées")

    def unlock_selected_cells(self):
        for index in self.selectedIndexes():
            self.unlock_cell(index.row(), index.column())
        logger.info("Cellules sélectionnées déverrouillées")

    def is_cell_locked(self, row, column):
        item = self.item(row, column)
        return item and not (item.flags() & Qt.ItemIsEditable)

    def check_row(self, row):
        check_item = self.item(row, 0)
        if not check_item:
            check_item = QTableWidgetItem()
            self.setItem(row, 0, check_item)
        check_item.setCheckState(Qt.Checked)

    def prompt_add_column(self):
        """Ajout de colonne avec synchronisation DataFrame"""
        name, ok = QInputDialog.getText(self, "Ajouter une colonne", "Nom de la nouvelle colonne :")
        if ok and name:
            self.add_column(name)  # Utilise la méthode synchronisée
