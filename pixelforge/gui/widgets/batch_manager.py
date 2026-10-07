"""
PixelForge GUI - Batch Manager
=================================

Table view bound to a BatchQueue: shows every file's status/priority, with
Pause / Resume / Cancel / Retry controls that call straight into the real
queue (pipeline/batch.py), which itself runs on background threads.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton,
    QFileDialog, QHeaderView,
)

from database import Database
from pipeline import BatchQueue, PipelineOptions
from optimizer import Goal
from compression import AutoMode


class _BatchRunner(QThread):
    file_done = Signal(object)   # BatchResult
    all_done = Signal()

    def __init__(self, queue: BatchQueue, parent=None):
        super().__init__(parent)
        self.queue = queue

    def run(self) -> None:
        self.queue.on_progress = lambda r: self.file_done.emit(r)
        self.queue.run(blocking=True)
        self.all_done.emit()


class BatchManagerWidget(QWidget):
    def __init__(self, translator, db: Database, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.db = db
        self.queue: BatchQueue | None = None
        self._runner: _BatchRunner | None = None

        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.btn_add_folder = QPushButton(translator.t("btn_add_folder"))
        self.btn_start = QPushButton(translator.t("btn_start"))
        self.btn_pause = QPushButton(translator.t("btn_pause"))
        self.btn_resume = QPushButton(translator.t("btn_resume"))
        self.btn_cancel = QPushButton(translator.t("btn_cancel"))
        for b in (self.btn_add_folder, self.btn_start, self.btn_pause, self.btn_resume, self.btn_cancel):
            controls.addWidget(b)
        root.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Status", "Original", "Final"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        root.addWidget(self.table)

        self._rows: dict[int, int] = {}
        self._folder: str | None = None

        self.btn_add_folder.clicked.connect(self._pick_folder)
        self.btn_start.clicked.connect(self._start)
        self.btn_pause.clicked.connect(lambda: self.queue and self.queue.pause())
        self.btn_resume.clicked.connect(lambda: self.queue and self.queue.resume())
        self.btn_cancel.clicked.connect(lambda: self.queue and self.queue.cancel_all())

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.translator.t("btn_add_folder"))
        if folder:
            self._folder = folder

    def _start(self) -> None:
        if not self._folder:
            return
        exts = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".tif", ".tiff", ".bmp", ".gif", ".ppm")
        paths = [os.path.join(r, f) for r, _d, fs in os.walk(self._folder) for f in fs
                  if f.lower().endswith(exts)]
        options = PipelineOptions(goal=Goal.BALANCED, auto_mode=AutoMode.FAST)
        self.queue = BatchQueue(self.db, options, max_workers=None)
        job_id = self.queue.add_files(paths)

        self.table.setRowCount(0)
        self._rows.clear()
        for p in paths:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(os.path.basename(p)))
            self.table.setItem(row, 1, QTableWidgetItem(self.translator.t("status_pending")))
            self.table.setItem(row, 2, QTableWidgetItem(""))
            self.table.setItem(row, 3, QTableWidgetItem(""))
            self._rows[p] = row

        self._runner = _BatchRunner(self.queue)
        self._runner.file_done.connect(self._on_file_done)
        self._runner.start()

    def _on_file_done(self, result) -> None:
        row = self._rows.get(result.input_path)
        if row is None:
            return
        if result.report:
            status = self.translator.t("status_skipped") if result.kept_original else self.translator.t("status_done")
            self.table.setItem(row, 1, QTableWidgetItem(status))
            self.table.setItem(row, 2, QTableWidgetItem(str(result.report.original_size)))
            self.table.setItem(row, 3, QTableWidgetItem(str(result.report.final_size)))
        else:
            self.table.setItem(row, 1, QTableWidgetItem(f"{self.translator.t('status_failed')}: {result.error}"))
