"""PixelForge GUI - Settings: theme + language selection, applied live."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QComboBox

from gui.theme_manager import list_themes


class SettingsWidget(QWidget):
    theme_changed = Signal(str)
    language_changed = Signal(str)

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self.translator = translator
        layout = QFormLayout(self)

        self.theme_box = QComboBox()
        self.theme_box.addItems(list_themes())
        layout.addRow(translator.t("label_theme"), self.theme_box)

        self.lang_box = QComboBox()
        self.lang_box.addItem("English", "en")
        self.lang_box.addItem("فارسی (Persian)", "fa")
        self.lang_box.addItem("中文 (Chinese)", "zh")
        layout.addRow(translator.t("label_language"), self.lang_box)

        self.theme_box.currentTextChanged.connect(self.theme_changed.emit)
        self.lang_box.currentIndexChanged.connect(
            lambda i: self.language_changed.emit(self.lang_box.itemData(i))
        )
