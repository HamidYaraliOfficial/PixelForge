"""PixelForge GUI - Format Explorer: shows real codec availability on this machine."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtGui import QColor

from imgcodecs import available_codecs

_DESCRIPTIONS = {
    "JPEG": "Baseline/Progressive, libjpeg-turbo backed, wide compatibility.",
    "PNG": "Lossless, palette/alpha support, DEFLATE-based.",
    "WEBP": "Lossy & lossless, alpha, near-lossless, great web compatibility.",
    "AVIF": "Modern lossy/lossless AV1-based codec, excellent compression.",
    "JXL": "JPEG XL - lossless, VarDCT and Modular modes, high efficiency.",
    "HEIF": "Apple ecosystem / camera format, requires libheif.",
    "TIFF": "Lossless archival format, LZW/Deflate/PackBits.",
    "BMP": "Uncompressed raster, maximum compatibility.",
    "GIF": "Palette-based, animation support (static frames only here).",
    "PPM": "Simple portable pixmap format.",
}


class FormatExplorerWidget(QWidget):
    def __init__(self, translator, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Format", "Available", "Notes"])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        codecs = available_codecs()
        table.setRowCount(len(codecs))
        for row, (fmt, ok) in enumerate(sorted(codecs.items())):
            table.setItem(row, 0, QTableWidgetItem(fmt))
            status_item = QTableWidgetItem("Yes" if ok else "No (install plugin)")
            status_item.setForeground(QColor("#57d68d") if ok else QColor("#ff6b6b"))
            table.setItem(row, 1, status_item)
            table.setItem(row, 2, QTableWidgetItem(_DESCRIPTIONS.get(fmt, "")))
        layout.addWidget(table)
