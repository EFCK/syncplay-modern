"""Errors tab: persistent log of ErrorEvent entries.

Read-only, copyable. Auto-scrolls. Exposes a `cleared` signal so the sidebar
can reset its unread badge when the user clears manually.
"""

from __future__ import annotations

import html
import time

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern.events import ErrorEvent, ErrorSeverity


_SEVERITY_COLOR = {
    ErrorSeverity.INFO: "#5a5a5a",
    ErrorSeverity.WARNING: "#a37a00",
    ErrorSeverity.ERROR: "#a23",
    ErrorSeverity.CRITICAL: "#7a0000",
}


class ErrorsPanel(QtWidgets.QWidget):

    cleared = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._log = QtWidgets.QTextBrowser(self)
        self._log.setOpenExternalLinks(False)
        self._log.document().setDefaultStyleSheet(
            "p { margin: 2px 0; font-family: monospace; font-size: 12px; }"
            ".timestamp { color: #888; }"
            ".category { color: #555; }"
        )

        clear_btn = QtWidgets.QPushButton("Clear", self)
        clear_btn.clicked.connect(self._on_clear)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(self._log, 1)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(clear_btn)
        layout.addLayout(button_row, 0)

    def render_error(self, event: ErrorEvent) -> None:
        color = _SEVERITY_COLOR.get(event.severity, "#a23")
        ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp or time.time()))
        text = html.escape(event.text)
        category = html.escape(event.category)
        severity = html.escape(event.severity.value.upper())
        line = (
            f'<p>'
            f'<span class="timestamp">{ts}</span> '
            f'<span style="color:{color};"><b>[{severity}]</b></span> '
            f'<span class="category">({category})</span> '
            f'<span>{text}</span>'
            f'</p>'
        )
        cursor = self._log.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertHtml(line)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_clear(self) -> None:
        self._log.clear()
        self.cleared.emit()
