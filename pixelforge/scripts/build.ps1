# PixelForge - build portable executables (Windows) using PyInstaller.
. .\.venv\Scripts\Activate.ps1
pip install --quiet pyinstaller

Write-Host "-- Building CLI executable --" -ForegroundColor Cyan
pyinstaller --noconfirm --onefile --name pixelforge-cli main.py

Write-Host "-- Building GUI executable --" -ForegroundColor Cyan
pyinstaller --noconfirm --onefile --windowed --name pixelforge-gui `
    --add-data "gui/themes;gui/themes" --add-data "gui/i18n;gui/i18n" gui/app.py

Write-Host "Build artifacts are in .\dist\" -ForegroundColor Green
