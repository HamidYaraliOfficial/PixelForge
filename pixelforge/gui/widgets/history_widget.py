"""PixelForge GUI - History: revert-able list of past compression runs."""

from __future__ import annotations

import os
import shutil

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QHeaderView,
)

from database import Database


class HistoryWidget(QWidget):
    def __init__(self, translator, db: Database, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.db = db
        self._row_ids: list[int] = []
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_revert = QPushButton("Revert Selected")
        controls.addWidget(self.btn_refresh)
        controls.addWidget(self.btn_revert)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Original", "Output", "Date", "Reverted"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_revert.clicked.connect(self._revert_selected)
        self.refresh()

    def refresh(self) -> None:
        rows = self.db.get_history()
        self._row_ids = [r["id"] for r in rows]
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["original_path"] or ""))
            self.table.setItem(i, 1, QTableWidgetItem(r["output_path"] or ""))
            self.table.setItem(i, 2, QTableWidgetItem(str(r["created_at"])))
            self.table.setItem(i, 3, QTableWidgetItem("Yes" if r["reverted"] else "No"))

    def _revert_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        original = self.table.item(row, 0).text()
        output = self.table.item(row, 1).text()
        # PixelForge never overwrites the source file: "revert" means discarding
        # the generated output file and marking the history entry as reverted.
        try:
            if output and os.path.exists(output) and os.path.abspath(output) != os.path.abspath(original):
                os.remove(output)
        except OSError:
            pass
        history_id = self._row_ids[row] if row < len(self._row_ids) else None
        if history_id is not None:
            self.db.conn.execute("UPDATE history SET reverted=1 WHERE id=?", (history_id,))
            self.db.conn.commit()
        self.table.setItem(row, 3, QTableWidgetItem("Yes"))
