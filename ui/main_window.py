"""CarIntel main application window."""

from __future__ import annotations

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.models import CarProfile
from core.profile_manager import ProfileManager, UserProfile
from core.workers import SearchWorker
from ui.chat_panel import ChatPanel
from ui.profile_dialog import ProfileDialog
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
        self._active_user_profile: UserProfile | None = None
        ProfileManager.ensure_defaults_exist()
        self._build_ui()
        self._load_initial_profile()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(1280, 800)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_topbar())

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

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self._status_label = QLabel("Ready — select a profile and start chatting.")
        status_bar.addWidget(self._status_label, 1)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setFixedHeight(14)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        status_bar.addPermanentWidget(self._progress)

        self._results_panel.show_empty_state()
        self._chat_panel.search_requested.connect(self._start_search)

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
        layout.setSpacing(10)

        logo = QLabel("◈")
        logo.setStyleSheet("color: #58a6ff; font-size: 22px; font-weight: 700;")
        layout.addWidget(logo)

        title = QLabel("CarIntel")
        title.setStyleSheet(
            "color: #e6edf3; font-size: 18px; font-weight: 700; letter-spacing: 1px;"
        )
        layout.addWidget(title)

        layout.addSpacing(24)

        # ── Profile selector ─────────────────────────────────────────
        profile_label = QLabel("Profile:")
        profile_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(profile_label)

        self._profile_combo = QComboBox()
        self._profile_combo.setFixedWidth(200)
        self._profile_combo.setStyleSheet(
            "QComboBox { background: #21262d; border: 1px solid #30363d; "
            "border-radius: 5px; padding: 4px 10px; color: #e6edf3; font-size: 12px; }"
            "QComboBox::drop-down { border: none; width: 20px; }"
            "QComboBox QAbstractItemView { background: #161b22; border: 1px solid #30363d; "
            "selection-background-color: #1f6feb; color: #e6edf3; }"
        )
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        layout.addWidget(self._profile_combo)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedSize(44, 28)
        edit_btn.setToolTip("Edit selected profile")
        edit_btn.clicked.connect(self._on_edit_profile)
        layout.addWidget(edit_btn)

        new_btn = QPushButton("+")
        new_btn.setFixedSize(28, 28)
        new_btn.setToolTip("Create new profile")
        new_btn.setStyleSheet(
            "QPushButton { font-size: 16px; font-weight: 700; padding: 0; "
            "border: 1px solid #30363d; border-radius: 5px; background: #21262d; color: #58a6ff; }"
            "QPushButton:hover { background: #1f6feb22; border-color: #58a6ff; }"
        )
        new_btn.clicked.connect(self._on_new_profile)
        layout.addWidget(new_btn)

        layout.addStretch()

        model_badge = QLabel("gemma4:e2b  ·  ollama")
        model_badge.setStyleSheet(
            "color: #3fb950; background: #3fb95015; border: 1px solid #3fb95040; "
            "border-radius: 4px; padding: 3px 10px; font-size: 11px;"
        )
        layout.addWidget(model_badge)

        return bar

    # ── Profile management ───────────────────────────────────────────────

    def _load_initial_profile(self):
        self._refresh_profile_combo()
        active = ProfileManager.get_active_profile()
        if active:
            self._apply_profile(active)

    def _refresh_profile_combo(self, select_id: str = ""):
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        profiles = ProfileManager.list_profiles()
        target_idx = 0
        for i, p in enumerate(profiles):
            label = f"{p.display_name}"
            self._profile_combo.addItem(label, userData=p.id)
            if p.id == select_id or (not select_id and p.id == ProfileManager.get_active_id()):
                target_idx = i
        self._profile_combo.blockSignals(False)
        self._profile_combo.setCurrentIndex(target_idx)

    def _on_profile_selected(self, index: int):
        profile_id = self._profile_combo.itemData(index)
        if not profile_id:
            return
        profile = ProfileManager.load(profile_id)
        if profile:
            self._apply_profile(profile)

    def _apply_profile(self, profile: UserProfile):
        self._active_user_profile = profile
        ProfileManager.set_active_id(profile.id)
        self._chat_panel.load_profile(profile)
        self._results_panel.show_empty_state()
        self._set_status(
            f"Profile: {profile.display_name}  ·  {profile.framework_label()}"
        )

    def _on_new_profile(self):
        dlg = ProfileDialog(parent=self)
        if dlg.exec_() and dlg.get_profile():
            new_profile = dlg.get_profile()
            self._refresh_profile_combo(select_id=new_profile.id)
            self._apply_profile(new_profile)

    def _on_edit_profile(self):
        if not self._active_user_profile:
            return
        dlg = ProfileDialog(profile=self._active_user_profile, parent=self)
        if dlg.exec_():
            updated = dlg.get_profile()
            profiles = ProfileManager.list_profiles()
            if not profiles:
                # All deleted — recreate defaults
                ProfileManager.ensure_defaults_exist()
                self._refresh_profile_combo()
                active = ProfileManager.get_active_profile()
                if active:
                    self._apply_profile(active)
            elif updated:
                self._refresh_profile_combo(select_id=updated.id)
                self._apply_profile(updated)
            else:
                # Active profile was deleted — switch to first available
                self._refresh_profile_combo()
                self._on_profile_selected(0)

    # ── Search pipeline ──────────────────────────────────────────────────

    def _start_search(self, car_profile: CarProfile, user_profile: UserProfile):
        if self._search_worker and self._search_worker.isRunning():
            return

        log.info(
            "Search started | profile=%s | framework=%s | query=%s",
            user_profile.display_name,
            user_profile.framework,
            car_profile.to_search_summary(),
        )

        self._results_panel.show_empty_state("Searching…  please wait.")
        self._progress.show()
        self._progress.setValue(0)
        self._set_status("Launching search pipeline…")
        self._chat_panel.start_truck()

        worker = SearchWorker(car_profile, user_profile)
        self._search_worker = worker

        worker.status_update.connect(self._set_status)
        worker.progress_update.connect(self._on_progress)
        worker.results_ready.connect(self._on_results_ready)
        worker.error_occurred.connect(self._on_search_error)
        worker.finished.connect(lambda: self._progress.hide())
        worker.finished.connect(self._chat_panel.stop_truck)

        worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self._progress.setValue(int(current / total * 100))

    def _on_results_ready(self, listings: list):
        self._results_panel.load_listings(listings)
        self._set_status(f"Done — {len(listings)} listings ranked and summarized.")
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
    app.setFont(QFont("Segoe UI", 10))

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())
