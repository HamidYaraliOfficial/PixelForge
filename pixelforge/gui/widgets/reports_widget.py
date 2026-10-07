"""PixelForge GUI - Reports panel: view + export batch/job reports."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QFileDialog

from database import Database


class ReportsWidget(QWidget):
    def __init__(self, translator, db: Database, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.db = db
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.btn_export_json = QPushButton(translator.t("btn_export_json"))
        self.btn_export_csv = QPushButton(translator.t("btn_export_csv"))
        self.btn_export_html = QPushButton(translator.t("btn_export_html"))
        controls.addWidget(self.btn_export_json)
        controls.addWidget(self.btn_export_csv)
        controls.addWidget(self.btn_export_html)
        layout.addLayout(controls)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

        self.btn_export_json.clicked.connect(lambda: self._export("json"))
        self.btn_export_csv.clicked.connect(lambda: self._export("csv"))
        self.btn_export_html.clicked.connect(lambda: self._export("html"))
        self.refresh()

    def refresh(self) -> None:
        summary = self.db.dashboard_summary()
        self.text.setPlainText(
            f"Files processed: {summary['files']}\n"
            f"Original bytes: {summary['original_bytes']:,}\n"
            f"Final bytes: {summary['final_bytes']:,}\n"
            f"Saved bytes: {summary['saved_bytes']:,}\n"
            f"Average reduction: {summary['avg_reduction_percent']:.2f}%\n"
            f"Average estimated quality: {summary['avg_estimated_quality']:.2f}\n"
            f"Total processing time: {summary['total_processing_time_s']:.2f}s\n"
        )

    def _export(self, fmt: str) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export report", f"report.{fmt}")
        if not path:
            return
        summary = self.db.dashboard_summary()
        if fmt == "json":
            import json
            content = json.dumps(summary, indent=2)
        elif fmt == "csv":
            content = "metric,value\n" + "\n".join(f"{k},{v}" for k, v in summary.items())
        else:
            content = "<html><body><h1>PixelForge Report</h1><pre>" + \
                      "\n".join(f"{k}: {v}" for k, v in summary.items()) + "</pre></body></html>"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
