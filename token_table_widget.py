from PyQt5.QtWidgets import QMenu, QInputDialog, QMessageBox, QTableWidgetItem, QTableWidget, QApplication
from PyQt5.QtCore import Qt
import pandas as pd
import ast 
import re

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
        self.quick_search_term = ""
        self.clipboard = QApplication.clipboard()

        self.setup_table()

        # Raccourcis clavier
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        self.setShortcutEnabled(True)

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
        #menu.addAction("📋 Couper", self.copy_selected_cells) # a implementer
        #menu.addAction("📋 Coller", self.copy_selected_cells) # a implementer
        menu.addAction("🧹 Effacer (protégé si verrouillé)", self.clear_selected_cells)

        menu.exec_(self.viewport().mapToGlobal(pos))

    # ========== SETUP ========== OK
    def setup_table(self):
        self.setColumnCount(0)
        self.setRowCount(0)
        self.setSortingEnabled(True)
        
    # ========== DATA MANAGEMENT ========== 
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
            
            self.clean_locked_empty_cells()
            self.update_table_from_df()
            for col in self.hidden_columns:
                if col < self.columnCount():
                    self.setColumnHidden(col, True)

            #logger.info("✅ Données chargées avec métadonnées")
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement : {e}")

    def save_data(self):
        try:
            self.update_df_from_table()
            self.clean_locked_empty_cells()

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

            # Écrire dans un seul fichier avec deux feuilles
            with pd.ExcelWriter("data.xlsx", engine='openpyxl') as writer:
                self.df.to_excel(writer, sheet_name='Data', index=False)
                metadata_df.to_excel(writer, sheet_name='Metadata', index=False)

            #logger.info("💾 Données sauvegardées avec métadonnées")
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
        """
        Sauvegarde l’état courant du DataFrame et des métadonnées.
        """
        #logger.info("Sauvegarde de l'état actuel")
        #logger.info(f"État du DataFrame à sauvegarder :\n{self.df}")

        self.history.append({
            'df': self.df.copy(),
            'hidden_columns': self.hidden_columns.copy(),
            'locked_cells': self.locked_cells.copy(),
            'active_filter': self.active_filter,
            'filtered_index': self.filtered_index.copy() if hasattr(self, 'filtered_index') else []
        })
        self.redo_stack.clear()
        #logger.info("État sauvegardé pour undo/redo.")
    
    # ========== TABLE <-> DF SYNCHRONISATION ========== # OK
    def update_df_from_table(self):
        """
        Met à jour le DataFrame à partir de la table, y compris les cellules verrouillées.
        """
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
                item = self.item(row, col)
                value = item.text() if item else ""

                if (df_row, col) in self.locked_cells:
                    print(f"Locking cell ({df_row}, {col})")
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                self.df.iat[df_row, col] = value if value != "" else None

    def update_table_from_df(self):
        """
        Affiche le DataFrame dans la table, selon le filtre actif,
        en préservant les états (verrouillage, visibilité)
        """
        logger.info("Début de la mise à jour de la table à partir du DataFrame")
        logger.info(f"État initial du DataFrame :\n{self.df}")

        # Réinitialiser la table
        self.setRowCount(0)
        self.setColumnCount(0)
        logger.info("Table réinitialisée")

        # Appliquer le filtre
        df = self.apply_active_filter(self.df)
        logger.info(f"Filtre appliqué, nombre de lignes filtrées : {len(df)}")

        # Configurer la table
        self.setColumnCount(len(df.columns))
        self.setHorizontalHeaderLabels(df.columns)
        logger.info(f"En-têtes de la table mis à jour : {df.columns.tolist()}")
        self.setRowCount(len(df))
        logger.info(f"Table configurée avec les nouvelles colonnes et lignes = {len(df)}")

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
                #logger.debug(f"Item placé dans la cellule ({row}, {col}) avec la valeur : {item.text()}")

        # Restaurer la visibilité des colonnes
        for col in range(len(df.columns)):
            self.setColumnHidden(col, col in self.hidden_columns)

        # Mise à jour des indices filtrés
        self.filtered_index = df.index.tolist()
        """ logger.info("Indices filtrés mis à jour")
        logger.info("Mise à jour de la table à partir du DataFrame terminée")
        logger.info(f"État final du DataFrame après mise à jour de la table :\n{self.df}")"""
    
    # ========== SAUVEGARDE DES CELLULES ========== # à implementer proprement
    def setItem(self, row, col, item):
        super().setItem(row, col, item)
        #logger.debug(f"Item placé dans la cellule ({row}, {col}) avec la valeur : {item.text()}")

        self.backup()

    def cellChanged(self, row, col):
        col_name = self.df.columns[col]
        current_dtype = str(self.df[col_name].dtype)
        
        self.backup()

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

        self.update_df_from_table()

    # ========== AJOUT / SUPPRESSION DE LIGNES & COLONNES ========== # duplicate a fix
    def add_row(self, row_data=None):
        """Ajoute une ligne au DataFrame et met à jour la table"""
        self.backup()
        
        if row_data is None:
            row_data = [None] * self.columnCount()

        # Ajouter la nouvelle ligne au DataFrame
        new_row_index = len(self.df)
        self.df.loc[new_row_index] = row_data

        # 🔓 S'assurer qu'aucune cellule de la nouvelle ligne n'est verrouillée
        for col in range(self.columnCount()):
            self.unlock_cell(new_row_index, col)
        
        self.update_table_from_df()

   # faire + de test sur les locks
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

        logger.info(f"Cellules verrouillées avant modif :\n{self.locked_cells}")
        logger.info(f"Lignes à supprimer :\n{selected_rows}")

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
            new_locked_cells.add((r - len(selected_rows), c))

        self.locked_cells = new_locked_cells

        logger.info(f"Cellules verrouillées après modif :\n{self.locked_cells}")
        self.update_table_from_df()  # Mettre à jour la table après suppression
        
  # gere mal les locks, fais des dupplication en masse
    def duplicate_selected_rows(self, indexes):
        row_indices = sorted([index.row() for index in indexes], reverse=True)

        for row_index in row_indices:
            logger.info(f"Duplication de la ligne d'origine à l'index {row_index}.")

            # Obtenir la ligne d'origine
            original_row = self.df.loc[row_index].copy()
            logger.info(f"Ligne d'origine : {original_row.to_dict()}")

            # Insérer la nouvelle ligne juste après la ligne d'origine
            self.df = pd.concat([self.df.iloc[:row_index+1], pd.DataFrame([original_row]), self.df.iloc[row_index+1:]]).reset_index(drop=True)
            logger.info(f"DataFrame après insertion de la nouvelle ligne :\n{self.df}")

            # Cloner les éléments de la ligne dupliquée
            for col in range(self.columnCount()):
                original_item = self.item(row_index, col)
                if original_item:
                    cloned_item = self.clone_item(original_item)
                    self.insertRow(row_index + 1)
                    self.setItem(row_index + 1, col, cloned_item)
                    logger.info(f"Élément cloné et inséré à la position ({row_index + 1}, {col}) : {cloned_item.text()}")

            # Mettre à jour les indices des cellules verrouillées
            new_locked_cells = set()
            for (r, c) in self.locked_cells:
                if r > row_index:
                    new_locked_cells.add((r + 1, c))
                else:
                    new_locked_cells.add((r, c))
            self.locked_cells = new_locked_cells
            logger.info(f"Nouvel ensemble de cellules verrouillées : {self.locked_cells}")

        self.update_table_from_df()  # Mettre à jour la table après duplication
        logger.info("Fin de la duplication des lignes sélectionnées.")
        logger.info(f"État final du DataFrame après duplication :\n{self.df}")
        logger.info(f"État final des cellules verrouillées : {self.locked_cells}")

    def add_column(self, column_name, default_value=None):
        """Ajoute une colonne au DataFrame et met à jour la table"""
        self.update_df_from_table()
        if column_name not in self.df.columns:
            self.backup()
            self.df[column_name] = default_value
            logger.info(f"➕ Colonne '{column_name}' ajoutée avec valeur : {default_value}")
            self.update_table_from_df()
        else:
            logger.warning(f"La colonne '{column_name}' existe déjà.")
        self.update_table_from_df()

    def prompt_add_column(self):
        """Ajout de colonne avec synchronisation DataFrame"""
        name, ok = QInputDialog.getText(self, "Ajouter une colonne", "Nom de la nouvelle colonne :")
        if ok and name:
            self.add_column(name)  # Utilise la méthode synchronisée

    def delete_column(self, column_name_or_index):
        """
        Supprime une colonne du DataFrame et de l'affichage par nom ou par index.
        """
        self.update_df_from_table()
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
            

            # Sauvegarder l'état
            self.backup()

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
            #logger.info(f"Cellules verrouillées mises à jour : {self.locked_cells}")

            # Mettre à jour les colonnes masquées
            new_hidden = set()
            for col in self.hidden_columns:
                if col < index:
                    new_hidden.add(col)
                elif col > index:
                    new_hidden.add(col - 1)
            self.hidden_columns = new_hidden
            #logger.info(f"Colonnes masquées mises à jour : {self.hidden_columns}")

            #logger.info(f"🗑️ Colonne '{column_name}' (index {index}) supprimée")
            self.update_table_from_df()

        else:
            # Suppression par nom de colonne
            column_name = column_name_or_index
            if column_name in self.df.columns:
                col_idx = self.df.columns.get_loc(column_name)
                #logger.info(f"Suppression de la colonne '{column_name}' à l'index {col_idx}")

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
                logger.info(f"Cellules verrouillées mises à jour : {self.locked_cells}")

                # Mettre à jour les colonnes masquées
                new_hidden = set()
                for col in self.hidden_columns:
                    if col < col_idx:
                        new_hidden.add(col)
                    elif col > col_idx:
                        new_hidden.add(col - 1)
                self.hidden_columns = new_hidden
                #logger.info(f"Colonnes masquées mises à jour : {self.hidden_columns}")
                logger.info(f"🗑️ Colonne '{column_name}' supprimée")

        self.update_table_from_df()

    def rename_column(self, col):
        old_name = self.horizontalHeaderItem(col).text()
        new_name, ok = QInputDialog.getText(self, "Renommer la colonne", f"Nom actuel : {old_name}\nNouveau nom :")
        if ok and new_name and new_name != old_name:
            self.update_df_from_table()
            self.backup()
            self.df.rename(columns={old_name: new_name}, inplace=True)
            logger.info(f"✏️ Colonne renommée de '{old_name}' à '{new_name}'")
            self.update_table_from_df()

    # ========== VISIBILITE DES COLONNES ========== #
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

    # ========== TRI & DEPLACEMENT DE COLONNES ========== # a clean et implementer
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

   # ========== FILTRAGE & QUICK SEARCH ========== # " Erreur dans le filtre : name 'nan' is not defined "
    def apply_active_filter(self, df):
        """
        Applique le filtre principal et la recherche rapide.
        Gère les valeurs NaN et les caractères spéciaux.
        """
        base_query = self.normalize_query(self.active_filter)
        quick_search_query = self.build_quick_search_filter(self.quick_search_term)

        # Vérifier si les filtres sont vides
        if not base_query and not quick_search_query:
            self.filtered_index = df.index.tolist()
            return df

        # Combinaison des filtres : (filtre_principal) & (recherche_rapide)
        combined_query = ''
        if base_query and quick_search_query:
            combined_query = f'({base_query}) & ({quick_search_query})'
        elif base_query:
            combined_query = base_query
        elif quick_search_query:
            combined_query = quick_search_query

        try:
            filtered_df = df.query(combined_query)
            self.filtered_index = filtered_df.index.tolist()
            return filtered_df
        except Exception as e:
            logger.warning(f"❌ Erreur dans le filtre : {e}")
            self.filtered_index = df.index.tolist()
            return df

    def normalize_query(self, query_str):
        """
        Convertit les comparaisons de chaînes pour qu'elles soient insensibles à la casse.
        Gère les valeurs NaN et les caractères spéciaux.
        """
        if not query_str:
            return ""

        # Pattern pour détecter les comparaisons de chaînes (ex: col == "value")
        pattern = r'(\w+)\s*([=!><]+)\s*("([^"]*)"|\'([^\']*)\')'

        def replace_match(match):
            col = match.group(1)
            op = match.group(2)
            value = match.group(4) or match.group(5)  # Valeur entre guillemets ou apostrophes

            # Sécurise la valeur contre les caractères spéciaux
            safe_value = re.escape(value)

            # Si l'opérateur est `==` ou `!=`, appliquer `.str.lower()` pour ignorer la casse
            if op in ['==', '!=']:
                return f"{col}.fillna('').str.lower() {op} '{safe_value.lower()}'"
            # Si l'opérateur est `str.contains()` (ex: `col.str.contains("abc")`)
            elif 'str.contains' in match.group(0):
                return re.sub(
                    r'str.contains\(([^)]+)\)',
                    lambda m: f"str.contains('{safe_value}', case=False, na=False)",
                    match.group(0)
                )
            else:
                return match.group(0)  # Laisser les autres opérations inchangées

        # Appliquer la transformation
        normalized_query = re.sub(pattern, replace_match, query_str)
        return normalized_query

    def build_quick_search_filter(self, search_term):
        """
        Génère un filtre OR pour toutes les colonnes textuelles.
        Gère les valeurs NaN et les caractères spéciaux.
        """
        if not search_term:
            return ""

        # Sécurise la chaîne de recherche contre les caractères spéciaux
        safe_term = re.escape(search_term.strip())

        # Liste des colonnes textuelles (dtype 'object')
        string_cols = [col for col in self.df.columns if self.df[col].dtype == 'object']

        # Génère les conditions de filtrage en gérant les NaN
        conditions = [
            f"{col}.fillna('').str.contains('{safe_term}', case=False, na=False)"
            for col in string_cols
        ]

        if not conditions:
            return ""

        return '(' + ' | '.join(conditions) + ')'

    def set_filter(self, query_str):
        """Nettoie et applique le filtre avec gestion de la casse"""
        # Remplacer `=` par `==` pour les comparaisons
        cleaned_query = query_str.replace('=', '==').strip()

        # Appliquer la normalisation pour ignorer la casse
        self.active_filter = self.normalize_query(cleaned_query)
        self.update_table_from_df()

    def set_quick_search(self, search_term):
        self.quick_search_term = search_term.strip()
        if search_term.strip():
            self.active_filter = ""  # Réinitialise le filtre principal
        self.update_table_from_df()

    def validate_quick_search(self, search_term):
        try:
            test_df = self.df.head(1).fillna('')
            query = self.build_quick_search_filter(search_term)
            if query:
                test_df.query(query)
            return True
        except Exception as e:
            logger.warning(f"Recherche rapide invalide : {e}")
            return False


# ========== CUT COPY PASTE ERASE ========== A clean et implementer

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

    def clone_item(self, item):
        new_item = QTableWidgetItem(item.text())
        new_item.setFlags(item.flags())
        new_item.setFont(item.font())
        new_item.setBackground(item.background())
        if not item.flags() & Qt.ItemIsEditable:
            new_item.setFlags(new_item.flags() & ~Qt.ItemIsEditable)
        logger.info(f"Élément cloné : {item.text()} avec flags : {item.flags()}")
        return new_item
  
    # ========== GESTION DES CELLULES VERROUILLÉES ========== # a clean
    def lock_cell(self, row, col):
        """Verrouille une cellule en utilisant l'index original du DataFrame"""
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
        logger.info(f"Cellule verrouillée : ({df_row}, {df_col})")

        item = self.item(row, col)
        if item:
            self.update_item_flags(item, True)
    
    def unlock_cell(self, row, col):
        """Déverrouille une cellule en utilisant l'index original du DataFrame"""
        df_row = self.filtered_index[row] if hasattr(self, 'filtered_index') and row < len(self.filtered_index) else row
        df_col = col  # Les colonnes sont stockées en index relatif

        self.locked_cells.discard((df_row, df_col))
        logger.info(f"Cellule déverrouillée : ({df_row}, {df_col})")

        item = self.item(row, col)
        if item:
            self.update_item_flags(item, False)
    
    def lock_selected_cells(self):
        """Verrouille toutes les cellules sélectionnées"""
        for index in self.selectedIndexes():
            self.lock_cell(index.row(), index.column())
        logger.info(f"🔒 {len(self.selectedIndexes())} cellules verrouillées")
        self.update_table_from_df()  # Mettre à jour la table après verrouillage
        
    def unlock_selected_cells(self):
        """Déverrouille toutes les cellules sélectionnées"""
        for index in self.selectedIndexes():
            self.unlock_cell(index.row(), index.column())
        logger.info(f"🔓 {len(self.selectedIndexes())} cellules déverrouillées")
        self.update_table_from_df()

    def clean_locked_empty_cells(self):
        """Supprime les verrous sur les cellules vides"""
        before = len(self.locked_cells)
        self.locked_cells = {
            (r, c) for (r, c) in self.locked_cells
            if not (
                r < len(self.df) and c < self.df.shape[1]
                and (self.df.iat[r, c] is None or str(self.df.iat[r, c]).strip() == "" or pd.isna(self.df.iat[r, c])))
        }
        after = len(self.locked_cells)
        if after < before:
            logger.info(f"Verrous nettoyés sur {before - after} cellule(s) vide(s)")

    def update_item_flags(self, item, is_locked):
        """Met à jour les flags et la police d'un item en fonction de son état de verrouillage."""
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

