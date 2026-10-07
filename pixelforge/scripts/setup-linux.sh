#!/usr/bin/env bash
# PixelForge - Linux environment setup
# Installs system packages, creates a virtual environment, and installs
# every Python dependency needed to run PixelForge (GUI + CLI).
set -euo pipefail

echo "== PixelForge Linux Setup =="

if command -v apt-get >/dev/null 2>&1; then
    echo "-- Installing system packages (apt) --"
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip build-essential \
        libgl1 libxkbcommon-x11-0 libxcb-cursor0
else
    echo "!! apt-get not found. Please install Python 3.10+ and a C build toolchain manually."
fi

echo "-- Creating virtual environment (.venv) --"
python3 -m venv .venv
source .venv/bin/activate

echo "-- Upgrading pip --"
pip install --upgrade pip

echo "-- Installing PixelForge Python dependencies --"
pip install -r requirements.txt

echo "-- Verifying installation --"
python3 -c "import PIL, numpy, skimage, imagehash, PySide6; print('All core libraries import successfully.')"

echo ""
echo "Setup complete. Activate the environment with:"
echo "    source .venv/bin/activate"
echo "Then run the GUI with:  python main.py"
echo "Or the CLI with:        python main.py formats"
