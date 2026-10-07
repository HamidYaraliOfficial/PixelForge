#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate 2>/dev/null || true
export QT_QPA_PLATFORM=offscreen
python -m pytest tests/ -v
