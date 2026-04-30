"""CarIntel main application window."""

from __future__ import annotations

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.models import CarProfile
from core.workers import SearchWorker
from ui.chat_panel import ChatPanel
from ui.results_panel import ResultsPanel
from ui.styles import DARK_THEME

log = logging.getLogger(__name__)

APP_TITLE = "CarIntel — AI-Powered Car Search"
WINDOW_MIN_WIDTH = 1100
WINDOW_MIN_HEIGHT = 700


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._search_worker: SearchWorker | None = None
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(1280, 800)

        # ── Central widget ─────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top bar ────────────────────────────────────────────────────
        topbar = self._build_topbar()
        root_layout.addWidget(topbar)

        # ── Main content splitter ──────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: #21262d; }")

        self._chat_panel = ChatPanel()
        splitter.addWidget(self._chat_panel)

        self._results_panel = ResultsPanel()
        splitter.addWidget(self._results_panel)

        splitter.setSizes([340, 940])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root_layout.addWidget(splitter, 1)

        # ── Status bar ─────────────────────────────────────────────────
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_label = QLabel("Ready — chat with the AI to begin your search.")
        self._status_bar.addWidget(self._status_label, 1)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setFixedHeight(14)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        self._status_bar.addPermanentWidget(self._progress)

        self._results_panel.show_empty_state()

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #161b22, stop:1 #0d1117); "
            "border-bottom: 1px solid #21262d;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        logo = QLabel("◈")
        logo.setStyleSheet("color: #58a6ff; font-size: 22px; font-weight: 700;")
        layout.addWidget(logo)

        title = QLabel("CarIntel")
        title.setStyleSheet("color: #e6edf3; font-size: 18px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(title)

        tagline = QLabel("  AI-Powered Car Search Aggregator")
        tagline.setStyleSheet("color: #484f58; font-size: 12px;")
        layout.addWidget(tagline)

        layout.addStretch()

        model_badge = QLabel("gemma4:e2b  ·  ollama")
        model_badge.setStyleSheet(
            "color: #3fb950; background: #3fb95015; border: 1px solid #3fb95040; "
            "border-radius: 4px; padding: 3px 10px; font-size: 11px;"
        )
        layout.addWidget(model_badge)

        return bar

    def _connect_signals(self):
        self._chat_panel.search_requested.connect(self._start_search)

    # ── Search pipeline ─────────────────────────────────────────────────

    def _start_search(self, profile: CarProfile):
        if self._search_worker and self._search_worker.isRunning():
            return

        log.info("Starting search for: %s", profile.to_search_summary())
        self._results_panel.show_empty_state("Searching…  please wait.")
        self._progress.show()
        self._progress.setValue(0)
        self._set_status("Launching search pipeline…")

        worker = SearchWorker(profile)
        self._search_worker = worker

        worker.status_update.connect(self._set_status)
        worker.progress_update.connect(self._on_progress)
        worker.results_ready.connect(self._on_results_ready)
        worker.error_occurred.connect(self._on_search_error)
        worker.finished.connect(lambda: self._progress.hide())

        worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self._progress.setValue(int(current / total * 100))

    def _on_results_ready(self, listings: list):
        self._results_panel.load_listings(listings)
        count = len(listings)
        self._set_status(f"Done — {count} listings ranked and summarized.")
        self._progress.setValue(100)

    def _on_search_error(self, error: str):
        self._results_panel.show_empty_state(f"Search failed: {error}")
        self._set_status(f"Error: {error}")

    def _set_status(self, text: str):
        self._status_label.setText(text)


def run_app():
    import sys

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_THEME)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())
