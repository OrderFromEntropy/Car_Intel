"""Results panel: QTabWidget with one tab per tier, each containing scrollable car cards."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.agents import tier_label
from core.models import TIERS, CarListing
from ui.car_card import CarCard
from ui.styles import TIER_COLORS


class TierTab(QWidget):
    def __init__(self, tier: str, parent=None):
        super().__init__(parent)
        self.tier = tier
        self._cards: list[CarCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.horizontalScrollBar().setEnabled(False)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)
        self._layout.addStretch()

        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def add_card(self, listing: CarListing):
        card = CarCard(listing)
        # Insert before the trailing stretch
        insert_idx = self._layout.count() - 1
        self._layout.insertWidget(insert_idx, card)
        self._cards.append(card)

    def clear_cards(self):
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

    def count(self) -> int:
        return len(self._cards)


class ResultsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs: dict[str, TierTab] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_widget = QTabWidget()
        self._tab_widget.setTabPosition(QTabWidget.North)

        for tier in TIERS:
            tab = TierTab(tier)
            self._tabs[tier] = tab
            color = TIER_COLORS.get(tier, "#e6edf3")
            label = f"{tier} — {tier_label(tier)}"
            self._tab_widget.addTab(tab, label)
            idx = self._tab_widget.count() - 1
            self._tab_widget.tabBar().setTabTextColor(idx, _qcolor(color))

        layout.addWidget(self._tab_widget)

    def load_listings(self, listings: list[CarListing]):
        # Clear existing cards
        for tab in self._tabs.values():
            tab.clear_cards()

        # Bucket by tier
        for listing in listings:
            tier = listing.tier if listing.tier in TIERS else "F"
            self._tabs[tier].add_card(listing)

        # Update tab labels with counts
        for i, tier in enumerate(TIERS):
            count = self._tabs[tier].count()
            color = TIER_COLORS.get(tier, "#e6edf3")
            label = f"{tier}  ({count})" if count else tier
            self._tab_widget.setTabText(i, label)
            self._tab_widget.tabBar().setTabTextColor(i, _qcolor(color))

        # Jump to the best populated tier
        for i, tier in enumerate(TIERS):
            if self._tabs[tier].count() > 0:
                self._tab_widget.setCurrentIndex(i)
                break

    def show_empty_state(self, message: str = "Run a search to see results here."):
        for tab in self._tabs.values():
            tab.clear_cards()

        for i, tier in enumerate(TIERS):
            self._tab_widget.setTabText(i, tier)

        # Show placeholder in first tab
        s_tab = self._tabs["S"]
        placeholder = QLabel(message)
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #484f58; font-size: 14px; padding: 40px;")
        s_tab._layout.insertWidget(0, placeholder)
        self._tab_widget.setCurrentIndex(0)


def _qcolor(hex_color: str):
    from PyQt5.QtGui import QColor
    return QColor(hex_color)
