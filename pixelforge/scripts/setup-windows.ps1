# PixelForge - Windows environment setup
# Creates a virtual environment and installs every Python dependency needed
# to run PixelForge (GUI + CLI) on Windows 10/11.

Write-Host "== PixelForge Windows Setup ==" -ForegroundColor Cyan

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "Python was not found on PATH. Install Python 3.10+ from https://www.python.org/downloads/windows/ and re-run this script." -ForegroundColor Red
    exit 1
}

Write-Host "-- Python version --" -ForegroundColor Cyan
python --version

Write-Host "-- Creating virtual environment (.venv) --" -ForegroundColor Cyan
python -m venv .venv

Write-Host "-- Activating virtual environment --" -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

Write-Host "-- Upgrading pip --" -ForegroundColor Cyan
python -m pip install --upgrade pip

Write-Host "-- Installing PixelForge Python dependencies --" -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "-- Verifying installation --" -ForegroundColor Cyan
python -c "import PIL, numpy, skimage, imagehash, PySide6; print('All core libraries import successfully.')"

Write-Host ""
Write-Host "Setup complete. Activate the environment with:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "Then run the GUI with:  python main.py"
Write-Host "Or the CLI with:        python main.py formats"
