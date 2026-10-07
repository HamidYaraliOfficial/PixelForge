"""PixelForge GUI - Expert Mode: direct access to raw encoder parameters."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QComboBox, QSpinBox, QCheckBox, QDoubleSpinBox, QLabel,
)

from imgcodecs import available_codecs


class AdvancedSettingsWidget(QWidget):
    """Direct per-codec parameter controls, for users who want to bypass the
    Decision Engine entirely (Expert Mode)."""

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)

        self.format_box = QComboBox()
        for fmt, ok in available_codecs().items():
            if ok:
                self.format_box.addItem(fmt)
        layout.addRow(translator.t("label_format"), self.format_box)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(85)
        layout.addRow(translator.t("label_quality"), self.quality_spin)

        self.progressive_check = QCheckBox("Progressive (JPEG)")
        self.progressive_check.setChecked(True)
        layout.addRow(self.progressive_check)

        self.optimize_check = QCheckBox("Optimize / Huffman-optimize")
        self.optimize_check.setChecked(True)
        layout.addRow(self.optimize_check)

        self.lossless_check = QCheckBox("Lossless (WebP / JXL)")
        layout.addRow(self.lossless_check)

        self.method_spin = QSpinBox()
        self.method_spin.setRange(0, 6)
        self.method_spin.setValue(6)
        layout.addRow("Method/Effort", self.method_spin)

        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(0.0, 15.0)
        self.distance_spin.setSingleStep(0.1)
        self.distance_spin.setValue(1.0)
        layout.addRow("JXL Distance", self.distance_spin)

        self.subsampling_box = QComboBox()
        self.subsampling_box.addItems(["4:4:4", "4:2:2", "4:2:0"])
        self.subsampling_box.setCurrentIndex(2)
        layout.addRow("Chroma Subsampling (JPEG)", self.subsampling_box)

    def to_params(self) -> dict:
        fmt = self.format_box.currentText()
        if fmt == "JPEG":
            return dict(format=fmt, quality=self.quality_spin.value(),
                        progressive=self.progressive_check.isChecked(),
                        optimize=self.optimize_check.isChecked(),
                        subsampling=self.subsampling_box.currentIndex())
        if fmt == "WEBP":
            return dict(format=fmt, quality=self.quality_spin.value(),
                        lossless=self.lossless_check.isChecked(), method=self.method_spin.value())
        if fmt == "JXL":
            return dict(format=fmt, lossless=self.lossless_check.isChecked(),
                        distance=self.distance_spin.value(), effort=self.method_spin.value())
        if fmt == "AVIF":
            return dict(format=fmt, quality=self.quality_spin.value(), speed=self.method_spin.value())
        return dict(format=fmt)
