"""Chat side-panel: streaming Gemma interview with async token delivery."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QTextCursor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.interview import (
    PROFILE_READY_MARKER,
    extract_profile,
    initial_message,
    stream_reply,
)
from core.models import CarProfile

log = logging.getLogger(__name__)

_USER_BUBBLE_CSS = (
    "background-color: #1f6feb22; border-left: 3px solid #1f6feb; "
    "border-radius: 4px; padding: 8px 10px; margin: 4px 0;"
)
_AI_BUBBLE_CSS = (
    "background-color: #3fb95011; border-left: 3px solid #3fb950; "
    "border-radius: 4px; padding: 8px 10px; margin: 4px 0;"
)


class StreamWorker(QObject):
    """Runs the streaming LLM call in a thread, emitting tokens as they arrive."""

    token_received = pyqtSignal(str)
    reply_complete = pyqtSignal(str)  # full reply text
    error_occurred = pyqtSignal(str)

    def __init__(self, history: list[dict]):
        super().__init__()
        self.history = list(history)
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)

    def start(self):
        self._thread.start()

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            full_reply = loop.run_until_complete(self._stream())
            self.reply_complete.emit(full_reply)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            loop.close()
            self._thread.quit()

    async def _stream(self) -> str:
        collected = []
        async for token in stream_reply(self.history):
            collected.append(token)
            self.token_received.emit(token)
        return "".join(collected)


class ChatPanel(QWidget):
    """Side panel housing the interview chat UI."""

    profile_ready = pyqtSignal(object)   # emits CarProfile when interview complete
    search_requested = pyqtSignal(object)  # emits CarProfile when user wants to search

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[dict] = []
        self._stream_worker: StreamWorker | None = None
        self._current_profile: CarProfile | None = None
        self._ai_reply_buffer = ""
        self._build_ui()
        self._start_interview()

    def _build_ui(self):
        self.setObjectName("chat_panel")
        self.setMinimumWidth(300)
        self.setMaximumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background-color: #161b22; border-bottom: 1px solid #21262d;")
        header.setFixedHeight(52)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("CarIntel Assistant")
        title.setStyleSheet("color: #e6edf3; font-size: 14px; font-weight: 700;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setFixedSize(60, 28)
        self._reset_btn.setToolTip("Start a new interview")
        self._reset_btn.clicked.connect(self._reset_interview)
        h_layout.addWidget(self._reset_btn)

        root.addWidget(header)

        # Chat history
        self._chat_view = QTextBrowser()
        self._chat_view.setObjectName("chat_history")
        self._chat_view.setOpenExternalLinks(False)
        self._chat_view.setReadOnly(True)
        root.addWidget(self._chat_view, 1)

        # Typing indicator
        self._typing_label = QLabel("AI is thinking…")
        self._typing_label.setStyleSheet("color: #8b949e; font-size: 11px; padding: 4px 16px;")
        self._typing_label.hide()
        root.addWidget(self._typing_label)

        # Search trigger bar (shown after profile is ready)
        self._search_bar = QWidget()
        self._search_bar.setStyleSheet("background: #161b22; border-top: 1px solid #21262d;")
        sb_layout = QHBoxLayout(self._search_bar)
        sb_layout.setContentsMargins(12, 8, 12, 8)
        self._profile_summary = QLabel("")
        self._profile_summary.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._profile_summary.setWordWrap(True)
        sb_layout.addWidget(self._profile_summary, 1)

        self._search_btn = QPushButton("Search →")
        self._search_btn.setObjectName("primary")
        self._search_btn.setFixedHeight(32)
        self._search_btn.clicked.connect(self._on_search_clicked)
        sb_layout.addWidget(self._search_btn)
        self._search_bar.hide()
        root.addWidget(self._search_bar)

        # Input area
        input_container = QWidget()
        input_container.setStyleSheet("background: #161b22; border-top: 1px solid #21262d;")
        in_layout = QHBoxLayout(input_container)
        in_layout.setContentsMargins(12, 8, 12, 8)
        in_layout.setSpacing(8)

        self._input = QTextEdit()
        self._input.setObjectName("chat_input")
        self._input.setPlaceholderText("Type a message…")
        self._input.setFixedHeight(60)
        self._input.setAcceptRichText(False)
        self._input.installEventFilter(self)
        in_layout.addWidget(self._input)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("primary")
        self._send_btn.setFixedSize(60, 60)
        self._send_btn.clicked.connect(self._on_send)
        in_layout.addWidget(self._send_btn)

        root.addWidget(input_container)

    # ── Interview lifecycle ──────────────────────────────────────────────

    def _start_interview(self):
        greeting = initial_message()
        self._append_ai_message(greeting)
        self._history.append({"role": "assistant", "content": greeting})

    def _reset_interview(self):
        self._history.clear()
        self._current_profile = None
        self._chat_view.clear()
        self._search_bar.hide()
        self._input.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._start_interview()

    # ── Sending / receiving ──────────────────────────────────────────────

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if not text or self._stream_worker is not None:
            return
        self._input.clear()
        self._append_user_message(text)
        self._history.append({"role": "user", "content": text})
        self._send_btn.setEnabled(False)
        self._input.setEnabled(False)
        self._typing_label.show()
        self._start_stream()

    def _start_stream(self):
        worker = StreamWorker(self._history)
        self._stream_worker = worker
        # Reserve space for streaming AI reply
        self._ai_reply_buffer = ""
        self._append_ai_message_start()

        worker.token_received.connect(self._on_token)
        worker.reply_complete.connect(self._on_reply_complete)
        worker.error_occurred.connect(self._on_stream_error)
        worker.start()

    def _on_token(self, token: str):
        self._ai_reply_buffer += token
        # Update the last AI bubble in the chat view
        self._update_streaming_bubble(self._ai_reply_buffer)

    def _on_reply_complete(self, full_reply: str):
        self._typing_label.hide()
        self._stream_worker = None
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)

        # Strip PROFILE_READY block from display
        display_reply = full_reply
        if PROFILE_READY_MARKER in full_reply:
            display_reply = full_reply.split(PROFILE_READY_MARKER)[0].strip()
            # Parse profile asynchronously
            loop = asyncio.new_event_loop()
            try:
                profile = loop.run_until_complete(extract_profile(full_reply))
            finally:
                loop.close()
            if profile:
                self._current_profile = profile
                self._show_search_ready(profile)

        self._finalize_streaming_bubble(display_reply)
        self._history.append({"role": "assistant", "content": full_reply})

    def _on_stream_error(self, error: str):
        self._typing_label.hide()
        self._stream_worker = None
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)
        self._append_ai_message(f"⚠ Error connecting to AI: {error}\n\nMake sure Ollama is running.")

    def _on_search_clicked(self):
        if self._current_profile:
            self.search_requested.emit(self._current_profile)

    def _show_search_ready(self, profile: CarProfile):
        summary = profile.to_search_summary()
        self._profile_summary.setText(f"Ready: {summary}")
        self._search_bar.show()
        confirmation = (
            f"Great! I have everything I need. Here's your search profile:\n\n"
            f"**{summary}**\n\n"
            f"Click **Search →** below to find listings, or tell me if you'd like to adjust anything."
        )
        self._append_ai_message(confirmation)
        self._history.append({"role": "assistant", "content": confirmation})

    # ── Chat display helpers ─────────────────────────────────────────────

    def _append_user_message(self, text: str):
        html = (
            f'<div style="{_USER_BUBBLE_CSS}">'
            f'<span style="color:#1f6feb;font-weight:700;font-size:11px;">YOU</span><br>'
            f'<span style="color:#e6edf3;">{_escape(text)}</span>'
            f"</div><br>"
        )
        self._chat_view.append(html)
        self._scroll_to_bottom()

    def _append_ai_message_start(self):
        """Insert an empty AI bubble that will be filled by streaming tokens."""
        html = (
            f'<div id="stream_bubble" style="{_AI_BUBBLE_CSS}">'
            f'<span style="color:#3fb950;font-weight:700;font-size:11px;">CARINTEL AI</span><br>'
            f'<span id="stream_content" style="color:#e6edf3;"></span>'
            f"</div><br>"
        )
        self._chat_view.append(html)
        self._scroll_to_bottom()

    def _update_streaming_bubble(self, full_text: str):
        # QTextBrowser doesn't support live DOM manipulation easily,
        # so we rebuild the last block.
        self._replace_last_ai_bubble(full_text)

    def _finalize_streaming_bubble(self, text: str):
        self._replace_last_ai_bubble(text)

    def _replace_last_ai_bubble(self, text: str):
        # We track the full document and re-render the last AI block
        # by appending to the cursor position of our placeholder marker.
        # Simplest approach: store cursor position and use setHtml for last block.
        doc = self._chat_view.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)

        # Find and replace the streaming placeholder block
        full_html = self._chat_view.toHtml()
        marker = '<span id="stream_content"'
        if marker in full_html:
            rendered = _render_markdown_lite(text)
            new_block = (
                f'<div style="{_AI_BUBBLE_CSS}">'
                f'<span style="color:#3fb950;font-weight:700;font-size:11px;">CARINTEL AI</span><br>'
                f'<span style="color:#e6edf3;">{rendered}</span>'
                f"</div><br>"
            )
            # Replace the placeholder section with the updated content
            start = full_html.rfind(f'<div style="{_AI_BUBBLE_CSS}">')
            if start != -1:
                end = full_html.find("</div><br>", start) + len("</div><br>")
                updated = full_html[:start] + new_block + full_html[end:]
                self._chat_view.setHtml(updated)
                self._scroll_to_bottom()

    def _append_ai_message(self, text: str):
        rendered = _render_markdown_lite(text)
        html = (
            f'<div style="{_AI_BUBBLE_CSS}">'
            f'<span style="color:#3fb950;font-weight:700;font-size:11px;">CARINTEL AI</span><br>'
            f'<span style="color:#e6edf3;">{rendered}</span>'
            f"</div><br>"
        )
        self._chat_view.append(html)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        scrollbar = self._chat_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ── Event filter for Enter-to-send ───────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QKeyEvent
        if obj is self._input and event.type() == QEvent.KeyPress:
            if isinstance(event, QKeyEvent):
                from PyQt5.QtCore import Qt
                if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
                    self._on_send()
                    return True
        return super().eventFilter(obj, event)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )


def _render_markdown_lite(text: str) -> str:
    """Very light markdown → HTML for bold and line breaks."""
    import re
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Escape remaining HTML-sensitive chars (but preserve <b> tags)
    # We'll do a simple approach: escape first, then unescape bold tags
    escaped = (
        text.replace("&", "&amp;")
        .replace("<b>", "\x00BOLD_OPEN\x00")
        .replace("</b>", "\x00BOLD_CLOSE\x00")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\x00BOLD_OPEN\x00", "<b>")
        .replace("\x00BOLD_CLOSE\x00", "</b>")
        .replace("\n", "<br>")
    )
    return escaped
