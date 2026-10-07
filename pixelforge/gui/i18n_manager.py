"""
PixelForge GUI - Translator
==============================

A lightweight runtime translation system: JSON dictionaries per language
instead of compiled .ts/.qm files, so translations can be edited without a
Qt Linguist build step. Applies RightToLeft layout direction automatically
for Persian and LeftToRight for English/Chinese, exactly as required.
"""

from __future__ import annotations

import json
import os
from typing import Optional

I18N_DIR = os.path.join(os.path.dirname(__file__), "i18n")

RTL_LANGUAGES = {"fa"}


class Translator:
    def __init__(self, language: str = "en"):
        self.language = language
        self._strings: dict[str, str] = {}
        self.load(language)

    def load(self, language: str) -> None:
        path = os.path.join(I18N_DIR, f"{language}.json")
        if not os.path.exists(path):
            language = "en"
            path = os.path.join(I18N_DIR, "en.json")
        with open(path, encoding="utf-8") as fh:
            self._strings = json.load(fh)
        self.language = language

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self._strings.get(key, default if default is not None else key)

    @property
    def is_rtl(self) -> bool:
        return self.language in RTL_LANGUAGES

    def available_languages(self) -> list[str]:
        return sorted(
            os.path.splitext(f)[0] for f in os.listdir(I18N_DIR) if f.endswith(".json")
        )


def apply_layout_direction(app, translator: Translator) -> None:
    """Call after switching languages: sets the whole QApplication's layout
    direction to RTL for Persian, LTR otherwise (English & Chinese)."""
    try:
        from PySide6.QtCore import Qt
    except ImportError:
        return
    app.setLayoutDirection(Qt.RightToLeft if translator.is_rtl else Qt.LeftToRight)
