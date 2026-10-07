# PixelForge

**Universal Intelligent Image Compression Studio**

PixelForge analyzes every image before compressing it - extracting real
statistical and perceptual features (colour space, entropy, edge density,
noise, alpha, content type) - and uses a transparent Decision Engine to pick
the best format, codec and parameters for *that specific image*, then
benchmarks real candidates, verifies the result with a Quality Guardian, and
reports exactly why it chose what it chose.

- **Formats**: JPEG, PNG, WebP, AVIF, JPEG XL, TIFF, BMP, GIF, PPM/PGM, HEIC/HEIF
- **Interfaces**: full Qt 6 desktop GUI (PySide6) + a headless CLI for CI/CD
- **Themes**: Light, Dark, Windows Default, Blue, Red, High Contrast, AMOLED
- **Languages**: English, فارسی (Persian, RTL), 中文 (Chinese)
- **Storage**: local SQLite database (WAL mode) for history, presets, rules

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the module map and
**[docs/DECISION_ENGINE.md](docs/DECISION_ENGINE.md)** for exactly how images
are analyzed and how candidates are scored.

For full trilingual (English / Persian / Chinese) installation instructions,
screenshots-free usage guide and FAQ, see the standalone `README (1).markdown`
file shipped alongside this project.

## Quick start

```bash
# Linux
bash scripts/setup-linux.sh
source .venv/bin/activate
python main.py            # GUI
python main.py formats    # CLI

# Windows (PowerShell)
./scripts/setup-windows.ps1
./.venv/Scripts/Activate.ps1
python main.py
```

## Running the tests

```bash
bash scripts/test.sh        # Linux
./scripts/test.ps1          # Windows
```

## License

MIT - see [LICENSE](LICENSE).
