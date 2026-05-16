"""Chat panel: user bubbles + inline gray sync events + brief error notices.

Errors are NOT rendered here in full — when one arrives we insert a single
short gray italic notice pointing the user at the Errors tab. The Errors tab
itself owns the persistent error log.
"""

from __future__ import annotations

import html
import time
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern.events import (
    ChatMessage,
    ErrorEvent,
    SyncEvent,
)


class ChatPanel(QtWidgets.QWidget):

    chatSubmitted = QtCore.Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._log = QtWidgets.QTextBrowser(self)
        self._log.setOpenExternalLinks(True)
        self._log.document().setDefaultStyleSheet(
            "p { margin: 4px 0; }"
            ".bubble-self { color: #1d6fa5; }"
            ".bubble-other { color: #222; }"
            ".sysline { color: #888; font-style: italic; }"
            ".errline { color: #a35; font-style: italic; }"
            ".timestamp { color: #aaa; font-size: 10px; }"
        )

        self._input = QtWidgets.QLineEdit(self)
        self._input.setPlaceholderText("Send a message…")
        self._input.returnPressed.connect(self._on_submit)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(self._log, 1)
        layout.addWidget(self._input, 0)

    # --- Public API --------------------------------------------------------

    def render_chat(self, msg: ChatMessage) -> None:
        cls = "bubble-self" if msg.is_self else "bubble-other"
        user = html.escape(msg.user)
        text = html.escape(msg.text)
        line = (
            f'<p class="{cls}"><span class="timestamp">{self._format_time(msg.timestamp)}</span>'
            f' <b>{user}:</b> {text}</p>'
        )
        self._append(line)

    def render_sync(self, event: SyncEvent) -> None:
        # Upstream often packs multiple events into one message separated
        # by literal "\n" newlines (formatted for terminal output).
        # Render each line as its own paragraph so they don't collapse
        # into a single run-on gray line.
        ts = self._format_time(event.timestamp)
        lines = [line for line in (event.detail or "").splitlines() if line.strip()]
        for line in lines:
            self._append(
                f'<p class="sysline"><span class="timestamp">{ts}</span>'
                f' → {html.escape(line)}</p>'
            )

    def render_error_notice(self) -> None:
        line = (
            '<p class="errline"><span class="timestamp">'
            f'{self._format_time(time.time())}</span>'
            ' → New error · see <b>Errors</b> tab</p>'
        )
        self._append(line)

    def focus_input(self) -> None:
        self._input.setFocus()

    # --- Internals ---------------------------------------------------------

    def _on_submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.chatSubmitted.emit(text)

    def _append(self, html_fragment: str) -> None:
        cursor = self._log.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        # `insertHtml` of a <p> element does NOT start a new QTextDocument
        # block — successive inserts coalesce into the same paragraph and
        # CSS margins between <p> tags get ignored. Force a block boundary
        # before each fragment so each event is its own paragraph.
        if cursor.position() > 0:
            cursor.insertBlock()
        cursor.insertHtml(html_fragment)
        # Auto-scroll
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    @staticmethod
    def _format_time(ts: float) -> str:
        if not ts:
            ts = time.time()
        return time.strftime("%H:%M:%S", time.localtime(ts))
