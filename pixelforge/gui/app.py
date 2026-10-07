"""
PixelForge GUI - Application Entry Point
============================================

Run with: python main.py gui   (or just `python main.py` with no arguments)
"""

from __future__ import annotations

import sys

from pipeline.logging_setup import configure_logging


def run_gui() -> int:
    configure_logging()
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PixelForge")
    window = MainWindow(app)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
