"""
PixelForge GUI - Theme Manager
=================================

Loads one of the seven bundled QSS stylesheets (Light, Dark, Windows Default,
Blue, Red, High Contrast, AMOLED) and applies it to the running QApplication.
"""

from __future__ import annotations

import os

THEMES_DIR = os.path.join(os.path.dirname(__file__), "themes")

THEME_FILES = {
    "light": "light.qss",
    "dark": "dark.qss",
    "windows": "windows.qss",
    "blue": "blue.qss",
    "red": "red.qss",
    "high_contrast": "high_contrast.qss",
    "amoled": "amoled.qss",
}


def list_themes() -> list[str]:
    return list(THEME_FILES.keys())


def load_stylesheet(theme_name: str) -> str:
    fname = THEME_FILES.get(theme_name, THEME_FILES["windows"])
    path = os.path.join(THEMES_DIR, fname)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def apply_theme(app, theme_name: str) -> None:
    app.setStyleSheet(load_stylesheet(theme_name))
