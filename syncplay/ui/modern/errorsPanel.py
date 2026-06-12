"""Errors tab: persistent log of ErrorEvent entries.

Read-only, copyable. Auto-scrolls. Exposes a `cleared` signal so the sidebar
can reset its unread badge when the user clears manually.
"""

from __future__ import annotations

import html
import time

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern import theme as theme_mod
from syncplay.ui.modern.events import ErrorEvent, ErrorSeverity
from syncplay.ui.modern.i18n import tr


# Severity-coded colours used inline on each error line. Theme-aware so
# the "INFO" / "WARNING" / "ERROR" / "CRITICAL" tags stay readable on a
# dark background instead of fading into it.
_SEVERITY_COLORS_LIGHT = {
    ErrorSeverity.INFO: "#5a5a5a",
    ErrorSeverity.WARNING: "#a37a00",
    ErrorSeverity.ERROR: "#a23",
    ErrorSeverity.CRITICAL: "#7a0000",
}
_SEVERITY_COLORS_DARK = {
    ErrorSeverity.INFO: "#bbbbbb",
    ErrorSeverity.WARNING: "#d4a64f",
    ErrorSeverity.ERROR: "#e08090",
    ErrorSeverity.CRITICAL: "#ff7070",
}


def _severity_color(theme: str, severity: ErrorSeverity) -> str:
    table = _SEVERITY_COLORS_DARK if theme_mod.normalize(theme) == theme_mod.DARK else _SEVERITY_COLORS_LIGHT
    return table.get(severity, table[ErrorSeverity.ERROR])


class ErrorsPanel(QtWidgets.QWidget):

    cleared = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._theme: str = theme_mod.DEFAULT

        self._log = QtWidgets.QTextBrowser(self)
        self._log.setOpenExternalLinks(False)
        self._log.document().setDefaultStyleSheet(self._build_doc_css(self._theme))

        self._clear_btn = QtWidgets.QPushButton(tr("errors-clear"), self)
        self._clear_btn.clicked.connect(self._on_clear)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(self._log, 1)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._clear_btn)
        layout.addLayout(button_row, 0)

    def retranslate(self) -> None:
        self._clear_btn.setText(tr("errors-clear"))

    # --- Theme ------------------------------------------------------------

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self._log.document().setDefaultStyleSheet(self._build_doc_css(theme))

    @staticmethod
    def _build_doc_css(theme: str) -> str:
        p = theme_mod.palette(theme)
        return (
            "p { margin: 2px 0; font-family: monospace; font-size: 12px; }"
            f".timestamp {{ color: {p['timestamp']}; }}"
            f".category {{ color: {p['errors-category']}; }}"
        )

    def render_error(self, event: ErrorEvent) -> None:
        color = _severity_color(self._theme, event.severity)
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
