from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QMenu, QAction, QInputDialog, QAbstractItemView, QHeaderView
from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QFont, QColor
import json
import os

class TokenTableWidget(QTableWidget):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.locked_cells = set()

        self.setFocusPolicy(Qt.StrongFocus)
        self.setSortingEnabled(True)
        self.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        header = self.horizontalHeader()
        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.setDragDropMode(QAbstractItemView.InternalMove)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        add_row_action = QAction("Ajouter une ligne", self)
        add_row_action.triggered.connect(self.add_row)
        menu.addAction(add_row_action)
        delete_row_action = QAction("Supprimer la ligne", self)
        delete_row_action.triggered.connect(self.delete_selected_row)
        menu.addAction(delete_row_action)
        duplicate_row_action = QAction("Dupliquer la ligne", self)
        duplicate_row_action.triggered.connect(self.duplicate_selected_row)
        menu.addAction(duplicate_row_action)
        clear_cells_action = QAction("Effacer les cellules sélectionnées", self)
        clear_cells_action.triggered.connect(self.clear_selected_cells)
        menu.addAction(clear_cells_action)
        lock_action = QAction("Verrouiller la sélection", self)
        lock_action.triggered.connect(self.lock_selected_cells)
        menu.addAction(lock_action)
        unlock_action = QAction("Déverrouiller la sélection", self)
        unlock_action.triggered.connect(self.unlock_selected_cells)
        menu.addAction(unlock_action)
        menu.exec_(self.viewport().mapToGlobal(pos))

    def add_row(self):
        row_position = self.rowCount()
        self.insertRow(row_position)
        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        checkbox_item.setCheckState(Qt.Unchecked)
        self.setItem(row_position, 0, checkbox_item)
        for col in range(1, self.columnCount()):
            self.setItem(row_position, col, QTableWidgetItem(""))
        self.update_df_from_table(skip_columns=[0])
        self.save_state_for_undo()

    def delete_selected_row(self):
        selected_rows = sorted(set(index.row() for index in self.selectedIndexes()), reverse=True)
        for row in selected_rows:
            self.removeRow(row)
        self.save_state_for_undo()

    def duplicate_selected_row(self):
        selected_rows = list(set(index.row() for index in self.selectedIndexes()))
        if not selected_rows:
            return
        times, ok = QInputDialog.getInt(self, "Dupliquer la ligne", "Combien de fois ?", 1, 1)
        if ok:
            for row in selected_rows:
                row_data = [self.item(row, col).text() if self.item(row, col) else "" for col in range(self.columnCount())]
                for _ in range(times):
                    row_position = self.rowCount()
                    self.insertRow(row_position)
                    for col_idx, value in enumerate(row_data):
                        self.setItem(row_position, col_idx, QTableWidgetItem(value))

    def clear_selected_cells(self):
        for item in self.selectedItems():
            if item is not None:
                item.setText("")

    def lock_selected_cells(self):
        for item in self.selectedIndexes():
            row, col = item.row(), item.column()
            model_col = col - 1
            if model_col >= 0:
                self.locked_cells.add((row, model_col))
                item_widget = self.item(row, col)
                if item_widget:
                    font = item_widget.font()
                    font.setBold(True)
                    item_widget.setFont(font)
                    item_widget.setBackground(QColor(80, 80, 80))

    def unlock_selected_cells(self):
        for item in self.selectedIndexes():
            row, col = item.row(), item.column()
            model_col = col - 1
            if model_col >= 0:
                self.locked_cells.discard((row, model_col))
                item_widget = self.item(row, col)
                if item_widget:
                    font = item_widget.font()
                    font.setBold(False)
                    item_widget.setFont(font)
                    item_widget.setBackground(QColor(0, 0, 0))

    def update_df_from_table(self, skip_columns=None):
        if self.manager.df is None:
            return
        if skip_columns is None:
            skip_columns = []
        for row in range(self.rowCount()):
            for col in range(1, self.columnCount()):
                model_col = col - 1
                if col in skip_columns:
                    continue
                if (row, model_col) in self.locked_cells: