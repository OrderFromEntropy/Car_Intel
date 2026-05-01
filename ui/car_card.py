"""CarCard widget — displays a single listing in a rich card layout."""

from __future__ import annotations

import webbrowser

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from core.agents import tier_label
from core.models import CarListing
from ui.styles import TIER_CARD_BORDERS, TIER_COLORS


class CarCard(QFrame):
    def __init__(self, listing: CarListing, parent=None):
        super().__init__(parent)
        self.listing = listing
        self._build_ui()

    def _build_ui(self):
        tier = self.listing.tier or "F"
        border_color = TIER_CARD_BORDERS.get(tier, "#30363d")
        tier_color = TIER_COLORS.get(tier, "#6e7681")

        self.setObjectName("car_card")
        self.setStyleSheet(
            f"QFrame#car_card {{ "
            f"background-color: #161b22; "
            f"border: 1px solid {border_color}; "
            f"border-radius: 10px; "
            f"padding: 2px; "
            f"}}"
            f"QFrame#car_card:hover {{ border-color: {tier_color}; }}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(6)

        # ── Header row: tier badge + title + source ──────────────────
        header = QHBoxLayout()
        header.setSpacing(10)

        badge = QLabel(f"{tier}")
        badge.setObjectName(f"tier_badge_{tier}")
        badge.setStyleSheet(
            f"color: {tier_color}; font-weight: 700; font-size: 13px; "
            f"background: {tier_color}22; border-radius: 4px; padding: 2px 8px;"
        )
        badge.setFixedWidth(34)
        badge.setAlignment(Qt.AlignCenter)
        header.addWidget(badge)

        label_text = tier_label(tier)
        tier_desc = QLabel(label_text)
        tier_desc.setStyleSheet(f"color: {tier_color}; font-size: 11px; font-weight: 600;")
        header.addWidget(tier_desc)

        header.addStretch()

        if self.listing.source:
            source_lbl = QLabel(self.listing.source)
            source_lbl.setObjectName("source_label")
            header.addWidget(source_lbl)

        root.addLayout(header)

        # ── Title ─────────────────────────────────────────────────────
        title_text = self.listing.title or "Unknown Listing"
        title = QLabel(title_text)
        title.setStyleSheet("color: #e6edf3; font-size: 14px; font-weight: 600;")
        title.setWordWrap(True)
        root.addWidget(title)

        # ── Price / Mileage row ───────────────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(16)

        if self.listing.price:
            price = QLabel(self.listing.price)
            price.setObjectName("price_label")
            meta_row.addWidget(price)

        if self.listing.mileage:
            miles = QLabel(f"  {self.listing.mileage}")
            miles.setObjectName("mileage_label")
            meta_row.addWidget(miles)

        meta_row.addStretch()
        root.addLayout(meta_row)

        # ── Tier reasoning ────────────────────────────────────────────
        if self.listing.tier_reasoning:
            reasoning = QLabel(f"⟩ {self.listing.tier_reasoning}")
            reasoning.setStyleSheet(
                f"color: {tier_color}99; font-size: 11px; font-style: italic;"
            )
            reasoning.setWordWrap(True)
            root.addWidget(reasoning)

        # ── Disqualifiers (red) ───────────────────────────────────────
        for disq in self.listing.disqualifiers:
            row = QHBoxLayout()
            row.setSpacing(6)
            icon = QLabel("✕")
            icon.setStyleSheet("color: #f85149; font-size: 11px; font-weight: 700;")
            icon.setFixedWidth(14)
            row.addWidget(icon)
            text = QLabel(disq)
            text.setStyleSheet(
                "color: #f85149; font-size: 11px; "
                "background: #f8514912; border-radius: 3px; padding: 1px 4px;"
            )
            text.setWordWrap(True)
            row.addWidget(text, 1)
            root.addLayout(row)

        # ── Flags (amber) ─────────────────────────────────────────────
        for flag in self.listing.flags:
            row = QHBoxLayout()
            row.setSpacing(6)
            icon = QLabel("⚑")
            icon.setStyleSheet("color: #d29922; font-size: 11px;")
            icon.setFixedWidth(14)
            row.addWidget(icon)
            text = QLabel(flag)
            text.setStyleSheet(
                "color: #d29922; font-size: 11px; "
                "background: #d2992212; border-radius: 3px; padding: 1px 4px;"
            )
            text.setWordWrap(True)
            row.addWidget(text, 1)
            root.addLayout(row)

        # ── Divider before summary if we had disq/flags ───────────────
        if self.listing.disqualifiers or self.listing.flags or self.listing.tier_reasoning:
            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet("color: #21262d;")
            root.addWidget(divider)

        # ── Summary / Snippet ─────────────────────────────────────────
        summary_text = self.listing.summary or self.listing.snippet
        if summary_text:
            summary = QLabel(summary_text[:400])
            summary.setStyleSheet("color: #8b949e; font-size: 12px; line-height: 1.5;")
            summary.setWordWrap(True)
            root.addWidget(summary)

        # ── Footer: view button ───────────────────────────────────────
        footer = QHBoxLayout()
        footer.addStretch()

        if self.listing.url:
            view_btn = QPushButton("View Listing →")
            view_btn.setObjectName("view_btn")
            view_btn.setCursor(Qt.PointingHandCursor)
            view_btn.setFixedHeight(28)
            url = self.listing.url
            view_btn.clicked.connect(lambda _, u=url: webbrowser.open(u))
            footer.addWidget(view_btn)

        root.addLayout(footer)
