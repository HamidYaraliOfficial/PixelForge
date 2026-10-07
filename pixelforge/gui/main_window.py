"""
PixelForge GUI - Main Window
===============================

Assembles every panel behind a Windows-11-style side navigation: Dashboard,
Image Queue, Compression Workspace (= Queue widget doubles as workspace entry
point), Comparison Viewer, Batch Manager, Format Explorer, Presets, Advanced
Settings (Expert Mode), Reports, Logs, History, Settings.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QStackedWidget,
    QButtonGroup, QLabel,
)

from database import Database
from gui.i18n_manager import Translator, apply_layout_direction
from gui.theme_manager import apply_theme
from gui.widgets import (
    DashboardWidget, QueueWidget, ComparisonViewer, BatchManagerWidget,
    FormatExplorerWidget, PresetsWidget, AdvancedSettingsWidget, ReportsWidget,
    LogsWidget, HistoryWidget, SettingsWidget,
)


class MainWindow(QMainWindow):
    def __init__(self, app, db_path: str = "pixelforge.db"):
        super().__init__()
        self.app = app
        self.db = Database(db_path)
        self.translator = Translator("en")

        self.setWindowTitle(self.translator.t("app_title"))
        self.resize(1280, 800)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        self.side_nav = QWidget()
        self.side_nav.setObjectName("SideNav")
        self.side_nav.setFixedWidth(220)
        nav_layout = QVBoxLayout(self.side_nav)
        nav_layout.setContentsMargins(0, 12, 0, 12)

        self.stack = QStackedWidget()

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self._pages: list[tuple[str, QWidget]] = []
        self._nav_buttons: list[QPushButton] = []

        def add_page(key: str, widget: QWidget) -> None:
            btn = QPushButton(self.translator.t(key))
            btn.setCheckable(True)
            self.nav_group.addButton(btn)
            nav_layout.addWidget(btn)
            self.stack.addWidget(widget)
            self._pages.append((key, widget))
            self._nav_buttons.append(btn)
            index = len(self._pages) - 1
            btn.clicked.connect(lambda: self.stack.setCurrentIndex(index))

        self.dashboard = DashboardWidget(self.db, self.translator)
        self.queue = QueueWidget(self.translator, self.db)
        self.comparison = ComparisonViewer(self.translator)
        self.batch = BatchManagerWidget(self.translator, self.db)
        self.formats = FormatExplorerWidget(self.translator)
        self.presets = PresetsWidget(self.translator)
        self.advanced = AdvancedSettingsWidget(self.translator)
        self.reports = ReportsWidget(self.translator, self.db)
        self.logs = LogsWidget()
        self.history = HistoryWidget(self.translator, self.db)
        self.settings = SettingsWidget(self.translator)

        add_page("nav_dashboard", self.dashboard)
        add_page("nav_queue", self.queue)
        add_page("nav_comparison", self.comparison)
        add_page("nav_batch", self.batch)
        add_page("nav_formats", self.formats)
        add_page("nav_presets", self.presets)
        add_page("nav_advanced", self.advanced)
        add_page("nav_reports", self.reports)
        add_page("nav_logs", self.logs)
        add_page("nav_history", self.history)
        add_page("nav_settings", self.settings)

        nav_layout.addStretch(1)
        self._nav_buttons[0].setChecked(True)

        root.addWidget(self.side_nav)
        root.addWidget(self.stack, 1)

        self.settings.theme_changed.connect(self._on_theme_changed)
        self.settings.language_changed.connect(self._on_language_changed)

        apply_theme(self.app, "windows")

    def _on_theme_changed(self, theme_name: str) -> None:
        apply_theme(self.app, theme_name)

    def _on_language_changed(self, lang_code: str) -> None:
        self.translator.load(lang_code)
        apply_layout_direction(self.app, self.translator)
        self.setWindowTitle(self.translator.t("app_title"))
        for key, btn in zip((p[0] for p in self._pages), self._nav_buttons):
            btn.setText(self.translator.t(key))
        self.dashboard.retranslate()

    def closeEvent(self, event) -> None:
        self.db.close()
        super().closeEvent(event)
