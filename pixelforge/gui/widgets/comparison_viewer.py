"""
PixelForge GUI - Comparison Viewer
=====================================

Real before/after viewer:
  * Split-view slider (drag to reveal more of "before" vs "after")
  * Mouse-wheel zoom
  * Checkerboard background so transparency is visible on both images
  * 100% view toggle
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QPainter, QBrush, QColor, QWheelEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QFileDialog,
)


def _checkerboard_brush(size: int = 12) -> QBrush:
    pix = QPixmap(size * 2, size * 2)
    pix.fill(QColor("#dddddd"))
    painter = QPainter(pix)
    painter.fillRect(0, 0, size, size, QColor("#bbbbbb"))
    painter.fillRect(size, size, size, size, QColor("#bbbbbb"))
    painter.end()
    return QBrush(pix)


class ComparisonViewer(QWidget):
    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self.translator = translator
        self._before_path: str | None = None
        self._after_path: str | None = None
        self._zoom = 1.0

        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.btn_open_before = QPushButton("Before...")
        self.btn_open_after = QPushButton("After...")
        self.btn_100 = QPushButton("100%")
        controls.addWidget(self.btn_open_before)
        controls.addWidget(self.btn_open_after)
        controls.addStretch(1)
        controls.addWidget(self.btn_100)
        root.addLayout(controls)

        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(_checkerboard_brush())
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.wheelEvent = self._wheel_event  # zoom with mouse wheel
        root.addWidget(self.view, 1)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.valueChanged.connect(self._update_split)
        root.addWidget(self.slider)

        self._before_item: QGraphicsPixmapItem | None = None
        self._after_item: QGraphicsPixmapItem | None = None

        self.btn_open_before.clicked.connect(lambda: self._open("before"))
        self.btn_open_after.clicked.connect(lambda: self._open("after"))
        self.btn_100.clicked.connect(self._reset_zoom)

    def _open(self, which: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open image")
        if not path:
            return
        if which == "before":
            self._before_path = path
        else:
            self._after_path = path
        self._reload()

    def load_pair(self, before_path: str, after_path: str) -> None:
        self._before_path = before_path
        self._after_path = after_path
        self._reload()

    def _reload(self) -> None:
        self.scene.clear()
        if self._before_path:
            self._before_item = QGraphicsPixmapItem(QPixmap(self._before_path))
            self.scene.addItem(self._before_item)
        if self._after_path:
            self._after_item = QGraphicsPixmapItem(QPixmap(self._after_path))
            self.scene.addItem(self._after_item)
        self._update_split(self.slider.value())
        self._reset_zoom()

    def _update_split(self, value: int) -> None:
        if not self._before_item or not self._after_item:
            return
        w = self._before_item.pixmap().width()
        cut = w * value / 100.0
        # show "before" fully, clip "after" to the right portion => classic split-compare
        self._after_item.setVisible(True)
        rect = QRectF(cut, 0, w - cut, self._after_item.pixmap().height())
        self._after_item.setPos(0, 0)
        self._after_item.setOffset(0, 0)
        # simple approach: crop the after pixmap dynamically for the reveal effect
        full = QPixmap(self._after_path) if self._after_path else None
        if full and not full.isNull():
            cropped = full.copy(int(cut), 0, int(w - cut), full.height())
            self._after_item.setPixmap(cropped)
            self._after_item.setPos(cut, 0)

    def _wheel_event(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom *= factor
        self.view.scale(factor, factor)

    def _reset_zoom(self) -> None:
        self.view.resetTransform()
        self._zoom = 1.0
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
