"""Dark modern QSS theme for CarIntel."""

DARK_THEME = """
/* ── Global ─────────────────────────────────────────────────────────── */
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #0d1117;
}

/* ── Scroll bars ─────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #161b22;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #58a6ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: #161b22;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #30363d;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #58a6ff; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Splitter ────────────────────────────────────────────────────────── */
QSplitter::handle {
    background: #21262d;
    width: 2px;
}

/* ── Tab widget ─────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #21262d;
    background: #161b22;
    border-radius: 6px;
}
QTabBar::tab {
    background: #161b22;
    color: #8b949e;
    padding: 8px 20px;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #21262d;
    color: #58a6ff;
    border-color: #30363d;
}
QTabBar::tab:hover:!selected { color: #e6edf3; }

/* ── Push buttons ───────────────────────────────────────────────────── */
QPushButton {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
    color: #58a6ff;
}
QPushButton:pressed { background-color: #0d1117; }
QPushButton:disabled { color: #484f58; border-color: #21262d; }

QPushButton#primary {
    background-color: #1f6feb;
    border-color: #1f6feb;
    color: #ffffff;
}
QPushButton#primary:hover { background-color: #388bfd; border-color: #388bfd; }
QPushButton#primary:pressed { background-color: #1158c7; }

QPushButton#view_btn {
    background-color: transparent;
    border: 1px solid #30363d;
    color: #58a6ff;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton#view_btn:hover {
    background-color: #1f6feb22;
    border-color: #58a6ff;
}

/* ── Line edit / Text edit ──────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    color: #e6edf3;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #58a6ff;
}

/* ── Labels ─────────────────────────────────────────────────────────── */
QLabel#section_title {
    font-size: 16px;
    font-weight: 700;
    color: #e6edf3;
}
QLabel#subtitle {
    font-size: 11px;
    color: #8b949e;
}
QLabel#tier_badge_S { color: #ffd700; font-weight: 700; font-size: 14px; }
QLabel#tier_badge_A { color: #3fb950; font-weight: 700; font-size: 14px; }
QLabel#tier_badge_B { color: #58a6ff; font-weight: 700; font-size: 14px; }
QLabel#tier_badge_C { color: #d29922; font-weight: 700; font-size: 14px; }
QLabel#tier_badge_D { color: #f85149; font-weight: 700; font-size: 14px; }
QLabel#tier_badge_F { color: #6e7681; font-weight: 700; font-size: 14px; }

QLabel#price_label {
    color: #3fb950;
    font-size: 15px;
    font-weight: 700;
}
QLabel#mileage_label {
    color: #58a6ff;
    font-size: 12px;
}
QLabel#source_label {
    color: #8b949e;
    font-size: 11px;
}

/* ── Car card frame ─────────────────────────────────────────────────── */
QFrame#car_card {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 4px;
}
QFrame#car_card:hover {
    border-color: #30363d;
}

/* ── Chat panel ─────────────────────────────────────────────────────── */
QFrame#chat_panel {
    background-color: #0d1117;
    border-right: 1px solid #21262d;
}

QTextBrowser#chat_history {
    background-color: #0d1117;
    border: none;
    font-size: 13px;
    color: #e6edf3;
    padding: 8px;
}

/* ── Progress bar ───────────────────────────────────────────────────── */
QProgressBar {
    background-color: #21262d;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #58a6ff;
    border-radius: 4px;
}

/* ── Status bar ─────────────────────────────────────────────────────── */
QStatusBar {
    background: #161b22;
    color: #8b949e;
    font-size: 12px;
    border-top: 1px solid #21262d;
}

/* ── Combo box ──────────────────────────────────────────────────────── */
QComboBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 5px 10px;
    color: #e6edf3;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
    color: #e6edf3;
}

/* ── Tool tips ──────────────────────────────────────────────────────── */
QToolTip {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 8px;
}
"""

TIER_COLORS = {
    "S": "#ffd700",
    "A": "#3fb950",
    "B": "#58a6ff",
    "C": "#d29922",
    "D": "#f85149",
    "F": "#6e7681",
}

TIER_CARD_BORDERS = {
    "S": "#ffd70055",
    "A": "#3fb95055",
    "B": "#58a6ff55",
    "C": "#d2992255",
    "D": "#f8514955",
    "F": "#30363d",
}
