from PyQt5.QtWidgets import QMenu, QInputDialog, QMessageBox, QTableWidgetItem, QTableWidget, QApplication
from PyQt5.QtCore import Qt
import pandas as pd
import ast 

from logger import logger



class TokenTableWidget(QTableWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.df = pd.DataFrame()
        self.history = []
        self.redo_stack = []
        self.locked_cells = set()  # (row, col)
        self.active_filter = None
        self.filtered_index = []
        self.hidden_columns = set()  # Stockage persistant des colonnes masquées
        self.quick_search_term = ""
        self.clipboard = QApplication.clipboard()
        self.active_advanced_filter = None  # État du filtre1
        self.active_filters = []  # Liste pour stocker les filtres actifs
        self.active_advanced_filter = None
        self.column_order = []
        self.updating = False 

        self.setup_table()
        self.setSortingEnabled(True)

        # Raccourcis clavier
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        self.setShortcutEnabled(True)

        self.itemChanged.connect(self.on_item_changed)

    def on_item_changed(self, item):
        row = item.row()
        col = item.column()
        df_row = self.filtered_index[row] if row < len(self.filtered_index) else row

        # Si la cellule est verrouillée → on rétablit l’ancienne valeur
        if (df_row, col) in self.locked_cells:
            self.blockSignals(True)
            old_value = str(self.df.iat[df_row, col]) if pd.notna(self.df.iat[df_row, col]) else ""
            item.setText(old_value)
            self.blockSignals(False)
            #logger.warning(f"✋ Modification bloquée : cellule verrouillée ({row}, {col})")
            return

        # Appliquer la modif dans le DataFrame
        new_value = item.text()
        self.df.iat[df_row, col] = new_value if new_value != "" else None

        self.update_table_and_filters()

    # ========== RIGHT CLICK MENU ========== OK
    def contextMenuEvent(self, event):
        try: # Obtenir la position de la souris lors du clic droit
            pos = event.pos()
        except AttributeError as e:
            logger.error(f"Erreur lors de l'obtention de la position de la souris : {e}")
            return
        index = self.indexAt(pos)
        if not index.isValid():
            return

        menu = QMenu(self)

        # Gestion des lignes
        menu.addAction("➕ Ajouter une ligne vide", lambda: self.add_row())
        menu.addAction("📄 Dupliquer les lignes sélectionnées", lambda: self.duplicate_selected_rows(self.selectedIndexes()))
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
        #menu.addAction("✅ Cocher les lignes sélectionnées", self.check_rows_from_selected_cells)
        # menu.addAction("X Décocher les lignes sélectionnées", self.check_rows_from_selected_cells) # a implementer

        # Presse-papier
        menu.addSeparator()
        menu.addAction("📋 Copier", self.copy_selected_cells)
        menu.addAction("📋 Couper", self.cut_selected_cells) # a implementer
        menu.addAction("📋 Coller", self.paste_selected_cells) # a implementer
        menu.addAction("🧹 Effacer (protégé si verrouillé)", self.clear_selected_cells)

        menu.exec_(self.viewport().mapToGlobal(pos))

    # ========== SETUP ========== OK
    def setup_table(self):
        self.setColumnCount(0)
        self.setRowCount(0)

    def update_table_and_filters(self):
        self.backup()
        self.update_table_from_df()
        self.reapply_filters()
        if hasattr(self.parent(), "update_filter_autocompletion"):
            self.parent().update_filter_autocompletion()
    
    def update_df_and_filters(self):
        self.backup()
        self.update_df_from_table()
        self.reapply_filters()
        if hasattr(self.parent(), "update_filter_autocompletion"):
            self.parent().update_filter_autocompletion()

    # ========== DATA MANAGEMENT ========== OK
    def load_data(self):
        try:
            with pd.ExcelFile("data.xlsx", engine='openpyxl') as xls:
                self.df = pd.read_excel(xls, sheet_name='Data')

                if 'Metadata' in xls.sheet_names:
                    metadata_df = pd.read_excel(xls, sheet_name='Metadata')
                    metadata = metadata_df.iloc[0].to_dict() if not metadata_df.empty else {}

                    # Conversion des chaînes en listes Python
                    hidden_cols = ast.literal_eval(metadata.get('hidden_columns', '[]'))
                    locked_cells = ast.literal_eval(metadata.get('locked_cells', '[]'))
                    column_dtypes = ast.literal_eval(metadata.get('column_dtypes', '{}'))
                    self.active_filter = str(metadata.get('active_filter', ''))
                    self.quick_search_term = str(metadata.get('quick_search_term', ''))

                    # Appliquer les types de colonnes
                    for col, dtype in column_dtypes.items():
                        if col in self.df.columns:
                            try:
                                if dtype == 'object':
                                    self.df[col] = self.df[col].astype('object')
                                else:
                                    self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
                            except Exception as e:
                                logger.warning(f"Erreur lors de la conversion du type de la colonne '{col}' : {e}")

                    self.hidden_columns = set(hidden_cols) if isinstance(hidden_cols, list) else set()
                    self.locked_cells = set(tuple(cell) for cell in locked_cells) if isinstance(locked_cells, list) else set()
                else:
                    self.hidden_columns = set()
                    self.locked_cells = set()
           
            for col in self.hidden_columns:
                if col < self.columnCount():
                    self.setColumnHidden(col, True)
            
            self.update_table_from_df()
            if hasattr(self.parent(), "update_filter_autocompletion"):
                self.parent().update_filter_autocompletion()

        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement : {e}")

    def save_data(self):
        try:
            if self.df.empty:
                raise ValueError("Le DataFrame est vide. Impossible de sauvegarder.")

            # Préparer les métadonnées
            metadata = {
                'column_dtypes': {col: str(dtype) for col, dtype in self.df.dtypes.items()},
                'hidden_columns': list(self.hidden_columns),
                'locked_cells': [list(cell) for cell in self.locked_cells],
                'active_filter': str(self.active_filter),
                'quick_search_term': str(self.quick_search_term)
            }
            metadata_df = pd.DataFrame([metadata])

            # Écrire dans un seul fichier avec deux feuilles. A terme peut-être passer sur un json
            with pd.ExcelWriter("data.xlsx", engine='openpyxl') as writer:
                self.df.to_excel(writer, sheet_name='Data', index=False)
                metadata_df.to_excel(writer, sheet_name='Metadata', index=False)

        except Exception as e:
            logger.error(f"❌ Erreur lors de la sauvegarde : {e}")
    # ========== UNDO / REDO ========== # a clean et implementer y compris logique
    def undo(self):
        """Annulation avec préservation du filtre actif et des métadonnées"""
        if self.history:
            # Restaurer l'état précédent
            state = self.history.pop()
            self.df = state['df']
            self.hidden_columns = state['hidden_columns']
            self.locked_cells = state['locked_cells']
            self.active_filter = state['active_filter']
            self.filtered_index = state['filtered_index']

            self.update_table_from_df()

            logger.info("↩️ Undo effectué.")
        else:
            logger.warning("⚠️ Aucun historique pour undo.")

    def redo(self):
        """Rétablissement avec préservation du filtre actif et des métadonnées"""
        if self.redo_stack:
            # Restaurer l'état suivant
            state = self.redo_stack.pop()
            self.df = state['df']
            self.hidden_columns = state['hidden_columns']
            self.locked_cells = state['locked_cells']
            self.active_filter = state['active_filter']
            self.filtered_index = state['filtered_index']

            self.update_table_from_df()

            logger.info("↪️ Redo effectué.")
        else:
            logger.warning("⚠️ Aucun historique pour redo.")

    def backup(self):
        self.history.append({
            'df': self.df.copy(),
            'hidden_columns': self.hidden_columns.copy(),
            'locked_cells': self.locked_cells.copy(),
            'active_filter': self.active_filter,
            'filtered_index': self.filtered_index.copy() if hasattr(self, 'filtered_index') else []
        })
        self.redo_stack.clear()
    
    # ========== TABLE <-> DF SYNCHRONISATION ========== # OK
    def update_df_from_table(self):
        self.filtered_index = list(self.df.index)

        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
                item = self.item(row, col)
                value = item.text() if item else ""

                if (df_row, col) in self.locked_cells:
                    if item:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    else:
                        logger.warning(f"Cellule verrouillée mais item est None à la position ({row}, {col})")

                self.df.iat[df_row, col] = value if value != "" else None

    def update_table_from_df(self):
        self.blockSignals(True)
        if self.updating:
            return
        self.updating = True

        header = self.horizontalHeader()
        # Stocker les largeurs et l'ordre des colonnes avant de réinitialiser la table
        column_widths = [self.columnWidth(i) for i in range(self.columnCount())]
        column_order = [header.visualIndex(i) for i in range(self.columnCount())]
        
        # Réinitialiser la table
        self.setup_table()

        df = self.df

        # Configurer la table
        self.setColumnCount(len(df.columns))
        self.setHorizontalHeaderLabels(df.columns)
        self.setRowCount(len(df))

        # Pré-créer les items en dehors de la boucle principale
        items = []
        for row in range(len(df)):
            row_items = []
            for col, value in enumerate(df.iloc[row]):
                item = QTableWidgetItem(str(value) if pd.notna(value) else "")
                row_items.append(item)
            items.append(row_items)
            
        # Placer les items dans la table
        for row in range(len(items)):
            for col in range(len(items[row])):
                item = items[row][col]
                df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
                if (df_row, col) in self.locked_cells:
                    self.update_item_flags(item, True)
                self.setItem(row, col, item)
     
        # Restaurer la visibilité des colonnes
        for col in range(len(df.columns)):
            self.setColumnHidden(col, col in self.hidden_columns)

        # Mise à jour des indices filtrés
        self.filtered_index = df.index.tolist()
     
        # Restaurer les largeurs et l'ordre des colonnes
        for i, width in enumerate(column_widths):
            self.setColumnWidth(i, width)
 
        for logical in range(self.columnCount()):
            try:
                to_visual = column_order[logical]
            except IndexError:
                to_visual = logical
            current_visual = header.visualIndex(logical)
            if current_visual != to_visual:
                header.moveSection(current_visual, to_visual)

        self.blockSignals(False)   
        self.updating = False
    
    # ========== SAUVEGARDE DES CELLULES ========== selfback up en pause
    def setItem(self, row, col, item):
        self.blockSignals(True)
        super().setItem(row, col, item)
        self.blockSignals(False)

    # ========== AJOUT / SUPPRESSION DE LIGNES & COLONNES ========== 
    def add_row(self, row_data=None):        
        if row_data is None:
            row_data = [None] * self.columnCount()

        # Ajouter la nouvelle ligne au DataFrame
        new_row_index = len(self.df)
        self.df.loc[new_row_index] = row_data

        # 🔓 S'assurer qu'aucune cellule de la nouvelle ligne n'est verrouillée
        for col in range(self.columnCount()):
            self.unlock_cell(new_row_index, col)
        
        self.update_table_and_filters()

    def delete_selected_rows(self):
        selected_indexes = self.selectedIndexes()
        if not selected_indexes:
            return
        
        # Obtenir les indices originaux du DataFrame
        selected_rows = sorted(set(
            index.row()
            for index in selected_indexes
        ), reverse=True)

        if hasattr(self, 'filtered_index'):
            selected_rows = [self.filtered_index[row] for row in selected_rows]
        
        # Déverrouiller les cellules de la ligne avant suppression
        for row_index in selected_rows:
            for col in range(self.columnCount()):
                self.unlock_cell(row_index, col)
       
        for row_index in selected_rows:
            self.df.drop(index=row_index, inplace=True)
        self.df.reset_index(drop=True, inplace=True)
       
        # Mettre à jour les indices des cellules verrouillées
        new_locked_cells = set()
        for (r, c) in self.locked_cells:
            if r in selected_rows:
                continue
            elif r > selected_rows[-1]:  # Si la ligne verrouillée est après les lignes supprimées
                new_locked_cells.add((r - len(selected_rows), c))
            else:
                new_locked_cells.add((r, c))
    
        self.locked_cells = new_locked_cells
        self.update_table_and_filters()

    def duplicate_selected_rows(self, indexes):

        row_indices = sorted([index.row() for index in indexes], reverse=True)

        for row_index in row_indices:

            # Obtenir la ligne d'origine
            original_row = self.df.loc[row_index].copy()

            # Insérer la nouvelle ligne juste après la ligne d'origine
            self.df = pd.concat([self.df.iloc[:row_index+1], pd.DataFrame([original_row]), self.df.iloc[row_index+1:]]).reset_index(drop=True)

            # Cloner les éléments de la ligne dupliquée
            for col in range(self.columnCount()):
                original_item = self.item(row_index, col)
                if original_item:
                    cloned_item = self.clone_item(original_item)
                    self.insertRow(row_index + 1)
                    self.setItem(row_index + 1, col, cloned_item)

            # Mettre à jour les indices des cellules verrouillées
            new_locked_cells = set()
            for (r, c) in self.locked_cells:
                if r > row_index:
                    new_locked_cells.add((r + 1, c))
                else:
                    new_locked_cells.add((r, c))

            # Ajouter les nouvelles cellules verrouillées pour la ligne dupliquée
            for col in range(self.columnCount()):
                if (row_index, col) in self.locked_cells:
                    new_locked_cells.add((row_index + 1, col))

            self.locked_cells = new_locked_cells

        self.update_table_and_filters()

    def add_column(self, column_name, default_value=None):
        if column_name not in self.df.columns:
            self.backup()
            self.df[column_name] = default_value
            self.update_table_and_filters()
        else:
            logger.warning(f"La colonne '{column_name}' existe déjà.")
        
    def prompt_add_column(self):
        name, ok = QInputDialog.getText(self, "Ajouter une colonne", "Nom de la nouvelle colonne :")
        if ok and name:
            self.add_column(name)  # Utilise la méthode synchronisée
        
    def delete_column(self, column_name_or_index):
        
        if isinstance(column_name_or_index, int):
            # Suppression par index
            index = column_name_or_index
            if index < 0 or index >= self.columnCount():
                logger.warning("Index de colonne invalide pour suppression.")
                return

            column_name = self.horizontalHeaderItem(index).text() if self.horizontalHeaderItem(index) else f"Colonne {index}"
            if column_name not in self.df.columns:
                logger.error(f"Nom de colonne introuvable dans le DataFrame : {column_name}")
                return
            
            # Supprimer du DataFrame
            self.df.drop(columns=[column_name], inplace=True)

            # Mettre à jour les positions des cellules verrouillées
            new_locked = set()
            for row, col in self.locked_cells:
                if col < index:
                    new_locked.add((row, col))
                elif col > index:
                    new_locked.add((row, col - 1))
            self.locked_cells = new_locked

            # Mettre à jour les colonnes masquées
            new_hidden = set()
            for col in self.hidden_columns:
                if col < index:
                    new_hidden.add(col)
                elif col > index:
                    new_hidden.add(col - 1)
            self.hidden_columns = new_hidden

        else:
            # Suppression par nom de colonne
            column_name = column_name_or_index
            if column_name in self.df.columns:
                col_idx = self.df.columns.get_loc(column_name)

                # Sauvegarder l'état
                self.backup()

                # Supprimer du DataFrame
                self.df.drop(columns=[column_name], inplace=True)

                # Mettre à jour les positions des cellules verrouillées
                new_locked = set()
                for row, col in self.locked_cells:
                    if col < col_idx:
                        new_locked.add((row, col))
                    elif col > col_idx:
                        new_locked.add((row, col - 1))
                self.locked_cells = new_locked

                # Mettre à jour les colonnes masquées
                new_hidden = set()
                for col in self.hidden_columns:
                    if col < col_idx:
                        new_hidden.add(col)
                    elif col > col_idx:
                        new_hidden.add(col - 1)
                self.hidden_columns = new_hidden
                logger.info(f"🗑️ Colonne '{column_name}' supprimée")

        self.update_table_and_filters()
        
    def rename_column(self, col):

        old_name = self.horizontalHeaderItem(col).text()
        new_name, ok = QInputDialog.getText(self, "Renommer la colonne", f"Nom actuel : {old_name}\nNouveau nom :")
        if ok and new_name and new_name != old_name:
            self.backup()
            self.df.rename(columns={old_name: new_name}, inplace=True)
            self.update_table_and_filters()

    # ========== VISIBILITE DES COLONNES ========== ajouter self.update_and_reapply() ? a tester data
    def hide_column(self, col):
        header = self.horizontalHeader()
        prev = header.blockSignals(True)
        try:
            header.hideSection(col)
            self.hidden_columns.add(col)
        finally:
            header.blockSignals(prev)

    def show_column(self, col):
        header = self.horizontalHeader()
        prev = header.blockSignals(True)
        try:
            header.showSection(col)
            self.hidden_columns.discard(col)
        finally:
            header.blockSignals(prev)

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
            self.update_table_and_filters()

    def on_section_moved(self, logicalIndex, oldVisualIndex, newVisualIndex):
        if self.updating: return
        self.updating = True
        self.update_table_and_filters()
        self.updating = False

    def on_section_resized(self, logical_index, old_size, new_size):
        if self.updating:
            return
        self.updating = True
        self.horizontalHeader().blockSignals(True)
        self.update_table_and_filters()
        self.horizontalHeader().blockSignals(False)
        self.updating = False
        print(f"Colonne redimensionnée de {old_size} à {new_size}")

    # ========== TRI & DEPLACEMENT DE COLONNES ==========
    def move_column(self, from_index, to_index):
        
        cols = list(self.df.columns)
        if 0 <= from_index < len(cols) and 0 <= to_index < len(cols):
            self.backup()
            col = cols.pop(from_index)
            cols.insert(to_index, col)
            self.df = self.df[cols]
            self.update_table_and_filters()
        

    def sort_by_column(self, column_name, ascending=True):
        
        if column_name in self.df.columns:
            self.backup()
            self.df[column_name] = self.df[column_name].astype(str)
            self.df.sort_values(by=column_name, ascending=ascending, inplace=True)
            self.update_table_and_filters()
        

   # ========== FILTRAGE & QUICK SEARCH ========== 
    def apply_filter(self, filter_text):
        normalized_filter = filter_text.strip()  # ne pas le lower()

        if not normalized_filter:
            QMessageBox.warning(self, "Filtre vide", "Le champ de filtre est vide.")
            return

        try:
            self.active_advanced_filter = normalized_filter  # 🔹 Enregistrer le filtre

            # Appliquer le filtre à TOUTES les lignes (pas seulement les visibles)
            filtered_df = self.df.query(normalized_filter)
            matching_indices = filtered_df.index.tolist()

            for row in range(self.rowCount()):
                df_index = self.df.index[row]
                self.setRowHidden(row, df_index not in matching_indices)

            print(f"Filtre appliqué : {normalized_filter}")

            # Réappliquer recherche rapide s’il y en a une
            main_window = self.parent()
            if main_window:
                current_search = main_window.quick_search_input.text()
                self.filter_table(current_search)

            self.update_visible_counter()

        except Exception as e:
            columns_info = "\n".join(
                f"- {col} ({self.df[col].dtype})" for col in self.df.columns
            )
            QMessageBox.critical(
                self,
                "Filtre invalide",
                f"{str(e)}\n\nColonnes disponibles :\n{columns_info}",
            )

    def filter_table(self, quick_search_text):
        text = self.normalize_text(quick_search_text)

        # 🔹 D’abord, appliquer le filtre avancé s’il existe
        base_visible_rows = []
        if self.active_advanced_filter:
            try:
                filtered_df = self.df.query(self.active_advanced_filter)
                base_visible_rows = filtered_df.index.tolist()
            except Exception as e:
                print(f"[filter_table] Erreur filtre avancé : {e}")
                base_visible_rows = self.df.index.tolist()  # fallback : tout visible
        else:
            base_visible_rows = self.df.index.tolist()

        for row in range(self.rowCount()):
            df_index = self.df.index[row]

            if df_index not in base_visible_rows:
                self.setRowHidden(row, True)
                continue

            if text:
                match = False
                for column in range(self.columnCount()):
                    if self.isColumnHidden(column):
                        continue
                    item = self.item(row, column)
                    if item and text in item.text().lower():
                        match = True
                        break
                self.setRowHidden(row, not match)
            else:
                self.setRowHidden(row, False)

        self.update_visible_counter()
    
    def normalize_text(self, text):
        return text.strip().lower()

    def reset_filters(self):
        for row in range(self.rowCount()):
            self.setRowHidden(row, False)
        self.update_visible_counter()
        self.active_advanced_filter = None

    def update_visible_counter(self):
        if hasattr(self.parent(), "result_counter"):
            visible = sum(not self.isRowHidden(row) for row in range(self.rowCount()))
            total = self.rowCount()
            self.parent().result_counter.setText(f"{visible} lignes visibles sur {total}")
            
    def reapply_filters(self):
        if self.active_advanced_filter:
            self.apply_filter(self.active_advanced_filter)
        main_window = self.parent()
        if main_window:
            current_search = main_window.quick_search_input.text()
            self.filter_table(current_search)
    
    # ========== CUT COPY PASTE ERASE ========== rajouter self.update_and_reapply() ? a test data dans cut
    def copy_selected_cells(self):
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

    def cut_selected_cells(self):
        selection = self.selectedRanges()
        if not selection:
            return

        clipboard = QApplication.clipboard()
        copied_text = ""
        for range_ in selection:
            for row in range(range_.topRow(), range_.bottomRow() + 1):
                row_data = []
                for col in range(range_.leftColumn(), range_.rightColumn() + 1):
                    item = self.item(row, col)
                    text = item.text() if item else ""
                    row_data.append(text)
                copied_text += "\t".join(row_data) + "\n"

        clipboard.setText(copied_text.strip())

        # Maintenant on efface seulement les cellules non verrouillées
        for range_ in selection:
            for row in range(range_.topRow(), range_.bottomRow() + 1):
                for col in range(range_.leftColumn(), range_.rightColumn() + 1):
                    df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') else row
                    if (df_row, col) not in self.locked_cells:
                        item = self.item(row, col)
                        if item:
                            item.setText("")
        
    def paste_selected_cells(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text:
            return

        rows = text.splitlines()
        sel = self.selectedRanges()
        if sel:
            start_row = sel[0].topRow()
            start_col = sel[0].leftColumn()
        else:
            start_row = 0
            start_col = 0

        for i, row_text in enumerate(rows):
            values = row_text.split("\t")
            target_row = start_row + i

            # ➕ Ajouter des lignes si nécessaire
            while target_row >= self.rowCount():
                self.add_row()

            for j, val in enumerate(values):
                target_col = start_col + j

                # ➕ Ajouter des colonnes si nécessaire
                while target_col >= self.columnCount():
                    col_name = f"Col_{self.columnCount()}"
                    self.add_column(col_name)

                df_row = self.filtered_index[target_row] if hasattr(self, 'filtered_index') else target_row

                # ➖ Respect verrouillage
                if (df_row, target_col) in self.locked_cells:
                    continue

                item = self.item(target_row, target_col)
                if not item:
                    item = QTableWidgetItem()
                    self.setItem(target_row, target_col, item)
                item.setText(val)
        self.update_table_and_filters()

    def clear_selected_cells(self):
        
        for index in self.selectedIndexes():
            item = self.item(index.row(), index.column())
            if item and (item.flags() & Qt.ItemIsEditable):
                item.setText("")
            else:
                logger.debug(f"Cellule {index.row()}, {index.column()} non effacée (verrouillée ou vide)")
        self.update_table_and_filters()

    def clone_item(self, item):
        new_item = QTableWidgetItem(item.text())
        new_item.setFlags(item.flags())
        new_item.setFont(item.font())
        new_item.setBackground(item.background())
        if not item.flags() & Qt.ItemIsEditable:
            new_item.setFlags(new_item.flags() & ~Qt.ItemIsEditable)
        return new_item
  
    # ========== GESTION DES CELLULES VERROUILLÉES ========== 
    def lock_cell(self, row, col):
        df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        df_col = col  # Les colonnes sont stockées en index relatif

        try:
            value = self.df.iloc[df_row, df_col]
        except IndexError:
            logger.warning("❌ Impossible de verrouiller une cellule hors des limites.")
            return

        if pd.isna(value) or (isinstance(value, str) and value.strip() == ""):
            logger.warning("❌ Impossible de verrouiller une cellule vide.")
            return

        self.locked_cells.add((df_row, df_col))

        item = self.item(row, col)
        if item:
            self.update_item_flags(item, True)
        
    def unlock_cell(self, row, col):
        
        df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        df_col = col  # Les colonnes sont stockées en index relatif

        self.locked_cells.discard((df_row, df_col))

        item = self.item(row, col)
        if item:
            self.update_item_flags(item, False)
        else:
            logger.warning(f"Item non trouvé à la position ({row}, {col}) lors du déverrouillage de la cellule.")
    
    def lock_selected_cells(self):
        for index in self.selectedIndexes():
            self.lock_cell(index.row(), index.column())
        self.update_table_and_filters()
        
    def unlock_selected_cells(self):
        for index in self.selectedIndexes():
            self.unlock_cell(index.row(), index.column())
        self.update_table_and_filters()

    def update_item_flags(self, item, is_locked):
        self.blockSignals(True)
        if is_locked:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        else:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
        self.blockSignals(False)

