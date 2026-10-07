"""PixelForge GUI - Presets panel."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel

from optimizer import list_presets


class PresetsWidget(QWidget):
    def __init__(self, translator, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(translator.t("nav_presets")))
        self.list_widget = QListWidget()
        for p in list_presets():
            item = QListWidgetItem(f"{p['name']}  -  {p['description']}")
            item.setData(1000, p)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
