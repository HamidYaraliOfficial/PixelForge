. .\.venv\Scripts\Activate.ps1
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/ -v
