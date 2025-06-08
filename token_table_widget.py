from PyQt5.QtWidgets import QMenu, QInputDialog, QMessageBox, QTableWidgetItem, QTableWidget, QApplication
from PyQt5.QtCore import Qt, QPoint
import pandas as pd
import ast 

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
        self.hidden_columns = set()  # Stockage persistant des colonnes masquées

        self.setup_table()


    # ========== SETUP ========== #
    def setup_table(self):
        self.setColumnCount(0)
        self.setRowCount(0)
        self.setSortingEnabled(True)
        
    # ========== DATA MANAGEMENT ========== #
    def load_data(self):
        try:
            with pd.ExcelFile("data.xlsx", engine='openpyxl') as xls:
                self.df = pd.read_excel(xls, sheet_name='Data')
                
                if 'Metadata' in xls.sheet_names:
                    metadata_df = pd.read_excel(xls, sheet_name='Metadata')
                    metadata = {}  # Initialisation ici
                    
                    if not metadata_df.empty:
                        metadata = metadata_df.iloc[0].to_dict()
                    
                    # ✅ Conversion des chaînes en listes Python
                    hidden_cols = metadata.get('hidden_columns', '[]')
                    locked_cells = metadata.get('locked_cells', '[]')
                    column_dtypes = metadata.get('column_dtypes', '{}')
                    
                    try:
                        hidden_cols = ast.literal_eval(hidden_cols)
                    except:
                        hidden_cols = []
                    
                    try:
                        locked_cells = ast.literal_eval(locked_cells)
                    except:
                        locked_cells = []
                    
                    try:
                        column_dtypes = ast.literal_eval(column_dtypes)
                    except:
                        column_dtypes = {}# ✅ Appliquer les types de colonnes
                    for col, dtype in column_dtypes.items():
                        if col in self.df.columns:
                            try:
                                if dtype == 'object':
                                    # Force le type object pour accepter les types mixtes
                                    self.df[col] = self.df[col].astype('object')
                                else:
                                    self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
                            except:
                                pass  # En cas d'erreur, garde le type actuel
                    
                    self.hidden_columns = set(hidden_cols) if isinstance(hidden_cols, list) else set()
                    self.locked_cells = set(tuple(cell) for cell in locked_cells) if isinstance(locked_cells, list) else set()
                else:
                    self.hidden_columns = set()
                    self.locked_cells = set()
            
            self.update_table_from_df()
            for col in self.hidden_columns:
                if col < self.columnCount():
                    self.setColumnHidden(col, True)
                
                    
            logger.info("✅ Données chargées avec métadonnées")
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement : {e}")

    def save_data(self):
        try:
            self.update_df_from_table()
            
            if self.df.empty:
                raise ValueError("Le DataFrame est vide. Impossible de sauvegarder.")
            
            # Préparer les métadonnées
            metadata = {
                'column_dtypes': {col: str(dtype) for col, dtype in self.df.dtypes.items()},
                'hidden_columns': list(self.hidden_columns),
                'locked_cells': [list(cell) for cell in self.locked_cells]
            }
            metadata_df = pd.DataFrame([metadata])
            
            # ✅ Vérification que les données sont valides
            if metadata_df.empty:
                raise ValueError("Les métadonnées sont vides. Impossible de sauvegarder.")
            
            # ✅ Écrire dans un seul fichier avec deux feuilles
            with pd.ExcelWriter("data.xlsx", engine='openpyxl') as writer:
                self.df.to_excel(writer, sheet_name='Data', index=False)
                metadata_df.to_excel(writer, sheet_name='Metadata', index=False)
            
            logger.info("💾 Données sauvegardées avec métadonnées")
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
        Affiche le DataFrame dans la table, selon le filtre actif,
        en préservant les états (verrouillage, visibilité)
        """
        # Sauvegarder l'état actuel
        prev_filter = self.active_filter
        prev_hidden = self.hidden_columns.copy()
        prev_locked = self.locked_cells.copy()
        
        # Réinitialiser la table
        self.setRowCount(0)
        self.setColumnCount(0)
        
        # Appliquer le filtre
        df = self.apply_active_filter(self.df)
        
        # Configurer la table
        self.setColumnCount(len(df.columns))
        self.setHorizontalHeaderLabels(df.columns)
        self.setRowCount(len(df))
        
        # Remplir les cellules
        for row in range(len(df)):
            for col, value in enumerate(df.iloc[row]):
                item = QTableWidgetItem(str(value) if pd.notna(value) else "")
                
                # Appliquer le verrouillage
                df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
                if (df_row, col) in self.locked_cells:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    
                self.setItem(row, col, item)
        
        # Restaurer la visibilité des colonnes
        for col in range(len(df.columns)):
            self.setColumnHidden(col, col in self.hidden_columns)
        
        self.filtered_index = df.index.tolist()

            
            

    def update_df_from_table(self):
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
                
                item = self.item(row, col)
                value = item.text() if item else ""
                
                if value == "":
                    self.df.iat[df_row, col] = None
                else:
                    col_name = self.df.columns[col]
                    current_dtype = str(self.df[col_name].dtype)
                    
                    if current_dtype == 'object':
                        # ✅ Garde la valeur telle quelle pour les colonnes mixtes
                        self.df.iat[df_row, col] = value
                    else:
                        # ✅ Conversion selon le type attendu
                        try:
                            if current_dtype == 'int64':
                                self.df.iat[df_row, col] = int(value)
                            elif current_dtype == 'float64':
                                self.df.iat[df_row, col] = float(value)
                            elif current_dtype == 'bool':
                                self.df.iat[df_row, col] = value.lower() in ('true', '1', 'yes')
                            else:
                                self.df.iat[df_row, col] = value
                        except ValueError:
                            # ✅ Conversion impossible : force le type object
                            self.df[col_name] = self.df[col_name].astype('object')
                            self.df.iat[df_row, col] = value
                        
    # ========== VERROUILLAGE ========== #
    def lock_cell(self, row, col):
        """Verrouille une cellule en utilisant l'index original du DataFrame"""
        # Conversion correcte de l'indice de la table vers le DataFrame
        df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        df_col = col  # Les colonnes sont stockées en index relatif
        
        # Stockage dans self.locked_cells avec les indices du DataFrame
        self.locked_cells.add((df_row, df_col))
        
        # Mise à jour visuelle
        item = self.item(row, col)
        if item:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            font = item.font()
            font.setBold(True)
            item.setFont(font)

    def unlock_cell(self, row, col):
        """Déverrouille une cellule en utilisant l'index original du DataFrame"""
        df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        df_col = col
        
        self.locked_cells.discard((df_row, df_col))
        
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
        """Supprime une colonne du DataFrame ET de l'affichage"""
        if column_name in self.df.columns:
            col_idx = self.df.columns.get_loc(column_name)
            
            # Sauvegarder l'état
            self.backup()
            
            # Supprimer du DataFrame
            self.df.drop(columns=[column_name], inplace=True)
            
            # Mettre à jour les positions des cellules verrouillées
            col_pos = self.df.columns.tolist().index(column_name)
            new_locked = set()
            for row, col in self.locked_cells:
                if col < col_pos:
                    new_locked.add((row, col))
                elif col > col_pos:
                    new_locked.add((row, col-1))
            self.locked_cells = new_locked
            
            # Mettre à jour les colonnes masquées
            new_hidden = set()
            for col in self.hidden_columns:
                if col < col_pos:
                    new_hidden.add(col)
                elif col > col_pos:
                    new_hidden.add(col-1)
            self.hidden_columns = new_hidden
            
            logger.info(f"🗑️ Colonne '{column_name}' supprimée")
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
        """Masque une colonne avec gestion persistante"""
        self.setColumnHidden(col, True)
        self.hidden_columns.add(col)
        logger.info(f"👁️ Colonne {col} masquée")

    def show_column(self, col):
        """Affiche une colonne avec gestion persistante"""
        self.setColumnHidden(col, False)
        self.hidden_columns.discard(col)
        logger.info(f"👁️ Colonne {col} affichée")

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

    def toggle_column_visibility(self, col):
        """Bascule l'état de visibilité d'une colonne"""
        self.setColumnHidden(col, not self.isColumnHidden(col))
        if self.isColumnHidden(col):
            self.hidden_columns.add(col)
        else:
            self.hidden_columns.discard(col)
            
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

    # ========== GESTION DES CELLULES VERROUILLÉES ========== #
    def lock_cell(self, row, col):
        """Verrouille une cellule et met à jour l'état de verrouillage"""
        df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        
        # Mise à jour de l'état interne
        self.locked_cells.add((df_row, col))
        
        # Création de l'item si nécessaire
        if not self.item(row, col):
            self.setItem(row, col, QTableWidgetItem(""))
            
        item = self.item(row, col)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        font = item.font()
        font.setBold(True)
        item.setFont(font)

    def unlock_cell(self, row, col):
        """Déverrouille une cellule et met à jour l'état de verrouillage"""
        df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        
        # Mise à jour de l'état interne
        self.locked_cells.discard((df_row, col))
        
        item = self.item(row, col)
        if item:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            font = item.font()
            font.setBold(False)
            item.setFont(font)

    def lock_selected_cells(self):
        """Verrouille toutes les cellules sélectionnées"""
        for index in self.selectedIndexes():
            self.lock_cell(index.row(), index.column())
        logger.info(f"🔒 {len(self.selectedIndexes())} cellules verrouillées")

    def unlock_selected_cells(self):
        """Déverrouille toutes les cellules sélectionnées"""
        for index in self.selectedIndexes():
            self.unlock_cell(index.row(), index.column())
        logger.info(f"🔓 {len(self.selectedIndexes())} cellules déverrouillées")

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

    def cellChanged(self, row, col):
        col_name = self.df.columns[col]
        current_dtype = str(self.df[col_name].dtype)
        
        if current_dtype != 'object':
            item = self.item(row, col)
            value = item.text() if item else ""
            
            try:
                if current_dtype == 'int64':
                    int(value)
                elif current_dtype == 'float64':
                    float(value)
            except ValueError:
                logger.warning(f"⚠️ La colonne '{col_name}' sera convertie en type 'object' pour accepter les valeurs mixtes.")
