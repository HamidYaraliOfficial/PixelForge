"""
PixelForge GUI - Image Queue Widget
======================================

Drag & drop target for files/folders. Every image gets a card: thumbnail,
filename, original size, estimated/final size, reduction, format, status.
All actual compression work happens on a QThread worker (PixelForgeWorker)
so the UI thread never blocks/freezes, per the "never freeze" requirement.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QIcon, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QFileDialog, QComboBox, QProgressBar,
)

from pipeline import PipelineOptions, process_single
from optimizer import Goal
from compression import AutoMode

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".jxl", ".tif", ".tiff",
             ".bmp", ".gif", ".ppm", ".pgm", ".heic", ".heif")


class CompressWorker(QThread):
    progress = Signal(str, object)     # path, CompressionReport | None
    failed = Signal(str, str)          # path, error message
    finished_all = Signal()

    def __init__(self, paths: list[str], options: PipelineOptions, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.options = options
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        for path in self.paths:
            if self._stop:
                break
            try:
                report = process_single(path, self.options)
                self.progress.emit(path, report)
            except Exception as exc:  # noqa: BLE001 - isolate per-file errors
                self.failed.emit(path, str(exc))
        self.finished_all.emit()


class QueueWidget(QWidget):
    def __init__(self, translator, db, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.db = db
        self.setAcceptDrops(True)
        self._worker: CompressWorker | None = None

        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.goal_box = QComboBox()
        for g in Goal:
            self.goal_box.addItem(translator.t(f"goal_{g.value}"), g.value)
        self.mode_box = QComboBox()
        for m in AutoMode:
            self.mode_box.addItem(translator.t(f"mode_{m.value}"), m.value)
        self.btn_add_files = QPushButton(translator.t("btn_add_files"))
        self.btn_add_folder = QPushButton(translator.t("btn_add_folder"))
        self.btn_start = QPushButton(translator.t("btn_start"))
        controls.addWidget(QLabel(translator.t("label_goal")))
        controls.addWidget(self.goal_box)
        controls.addWidget(QLabel(translator.t("label_mode")))
        controls.addWidget(self.mode_box)
        controls.addStretch(1)
        controls.addWidget(self.btn_add_files)
        controls.addWidget(self.btn_add_folder)
        controls.addWidget(self.btn_start)
        root.addLayout(controls)

        self.drop_hint = QLabel(translator.t("drop_hint"))
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setMinimumHeight(60)
        root.addWidget(self.drop_hint)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(48, 48))
        root.addWidget(self.list_widget, 1)

        self.progress_bar = QProgressBar()
        root.addWidget(self.progress_bar)

        self._pending: list[str] = []
        self._items_by_path: dict[str, QListWidgetItem] = {}

        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_folder.clicked.connect(self._pick_folder)
        self.btn_start.clicked.connect(self.start_compression)

    # ---- drag & drop -------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if os.path.isdir(local):
                for root_dir, _dirs, files in os.walk(local):
                    paths.extend(os.path.join(root_dir, f) for f in files if f.lower().endswith(IMAGE_EXT))
            elif local.lower().endswith(IMAGE_EXT):
                paths.append(local)
        self.add_paths(paths)

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self.translator.t("btn_add_files"))
        self.add_paths(files)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.translator.t("btn_add_folder"))
        if folder:
            paths = [os.path.join(r, f) for r, _d, fs in os.walk(folder) for f in fs
                      if f.lower().endswith(IMAGE_EXT)]
            self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        for p in paths:
            if p in self._items_by_path:
                continue
            item = QListWidgetItem(f"{os.path.basename(p)}  -  {_human_bytes(os.path.getsize(p))}  -  {self.translator.t('status_pending')}")
            thumb = self._make_thumbnail(p)
            if thumb:
                item.setIcon(QIcon(thumb))
            self.list_widget.addItem(item)
            self._items_by_path[p] = item
            self._pending.append(p)

    @staticmethod
    def _make_thumbnail(path: str) -> QPixmap | None:
        pix = QPixmap(path)
        if pix.isNull():
            return None
        return pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    # ---- compression --------------------------------------------------------------

    def start_compression(self) -> None:
        if not self._pending:
            return
        goal = Goal(self.goal_box.currentData())
        mode = AutoMode(self.mode_box.currentData())
        options = PipelineOptions(goal=goal, auto_mode=mode)

        self.progress_bar.setRange(0, len(self._pending))
        self.progress_bar.setValue(0)

        self._worker = CompressWorker(list(self._pending), options)
        self._worker.progress.connect(self._on_progress)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished_all.connect(self._on_finished_all)
        self._worker.start()

    def _on_progress(self, path: str, report) -> None:
        item = self._items_by_path.get(path)
        if item and report:
            item.setText(
                f"{os.path.basename(path)}  -  {_human_bytes(report.original_size)} -> "
                f"{_human_bytes(report.final_size)} (-{report.reduction_percent:.1f}%)  -  "
                f"{report.output_format}  -  {self.translator.t('status_done')}"
            )
        self.progress_bar.setValue(self.progress_bar.value() + 1)

    def _on_failed(self, path: str, message: str) -> None:
        item = self._items_by_path.get(path)
        if item:
            item.setText(f"{os.path.basename(path)}  -  {self.translator.t('status_failed')}: {message}")
        self.progress_bar.setValue(self.progress_bar.value() + 1)

    def _on_finished_all(self) -> None:
        self._pending.clear()


def _human_bytes(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
