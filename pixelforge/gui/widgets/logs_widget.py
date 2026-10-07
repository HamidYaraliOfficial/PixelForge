"""PixelForge GUI - Live-tailing log viewer."""

from __future__ import annotations

import os

from PySide6.QtCore import QFileSystemWatcher
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit


class LogsWidget(QWidget):
    def __init__(self, log_path: str = "logs/pixelforge.log", parent=None):
        super().__init__(parent)
        self.log_path = log_path
        layout = QVBoxLayout(self)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        if not os.path.exists(log_path):
            open(log_path, "a").close()

        self.watcher = QFileSystemWatcher([log_path])
        self.watcher.fileChanged.connect(self._reload)
        self._reload()

    def _reload(self) -> None:
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()[-500:]
            self.text.setPlainText("".join(lines))
            self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())
        except FileNotFoundError:
            pass
