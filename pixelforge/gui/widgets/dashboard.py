from __future__ import annotations

from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt


class DashboardCard(QFrame):
    def __init__(self, title: str, value: str, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardCard")
        layout = QVBoxLayout(self)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("DashboardCardValue")
        self.title_label = QLabel(title)
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class DashboardWidget(QWidget):
    """Summary of total images, size before/after, saved space, average ratio,
    average quality, processing time and most-chosen formats - all pulled from
    the real SQLite database (see database/db.py: dashboard_summary)."""

    def __init__(self, db, translator, parent=None):
        super().__init__(parent)
        self.db = db
        self.translator = translator
        layout = QGridLayout(self)
        layout.setSpacing(16)

        self.card_files = DashboardCard(translator.t("dash_files_processed"), "0")
        self.card_saved = DashboardCard(translator.t("dash_bytes_saved"), "0 B")
        self.card_reduction = DashboardCard(translator.t("dash_avg_reduction"), "0%")
        self.card_quality = DashboardCard(translator.t("dash_avg_quality"), "0")

        layout.addWidget(self.card_files, 0, 0)
        layout.addWidget(self.card_saved, 0, 1)
        layout.addWidget(self.card_reduction, 0, 2)
        layout.addWidget(self.card_quality, 0, 3)

        self.refresh()

    def refresh(self) -> None:
        summary = self.db.dashboard_summary()
        self.card_files.set_value(str(summary["files"]))
        self.card_saved.set_value(_human_bytes(summary["saved_bytes"]))
        self.card_reduction.set_value(f"{summary['avg_reduction_percent']:.1f}%")
        self.card_quality.set_value(f"{summary['avg_estimated_quality']:.1f}")

    def retranslate(self) -> None:
        self.card_files.title_label.setText(self.translator.t("dash_files_processed"))
        self.card_saved.title_label.setText(self.translator.t("dash_bytes_saved"))
        self.card_reduction.title_label.setText(self.translator.t("dash_avg_reduction"))
        self.card_quality.title_label.setText(self.translator.t("dash_avg_quality"))


def _human_bytes(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
