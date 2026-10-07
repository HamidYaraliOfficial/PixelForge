#!/usr/bin/env bash
# PixelForge - build portable executables (Linux) using PyInstaller.
set -euo pipefail
source .venv/bin/activate 2>/dev/null || true
pip install --quiet pyinstaller

echo "-- Building CLI executable --"
pyinstaller --noconfirm --onefile --name pixelforge-cli main.py

echo "-- Building GUI executable --"
pyinstaller --noconfirm --onefile --windowed --name pixelforge-gui \
    --add-data "gui/themes:gui/themes" --add-data "gui/i18n:gui/i18n" gui/app.py

echo "Build artifacts are in ./dist/"
