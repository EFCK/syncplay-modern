"""Tab strip swapping between ChatPanel and ErrorsPanel with unread badge."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class SidebarTabs(QtWidgets.QTabWidget):

    CHAT_INDEX = 0
    ERRORS_INDEX = 1

    def __init__(self, chat_panel: QtWidgets.QWidget, errors_panel: QtWidgets.QWidget,
                 parent=None) -> None:
        super().__init__(parent)
        self._unread = 0
        self.addTab(chat_panel, "Chat")
        self.addTab(errors_panel, "Errors")
        self.currentChanged.connect(self._on_changed)
        self._refresh_errors_label()

    def note_error(self) -> None:
        if self.currentIndex() == self.ERRORS_INDEX:
            return
        self._unread += 1
        self._refresh_errors_label()

    def reset_unread(self) -> None:
        self._unread = 0
        self._refresh_errors_label()

    def _on_changed(self, index: int) -> None:
        if index == self.ERRORS_INDEX:
            self.reset_unread()

    def _refresh_errors_label(self) -> None:
        if self._unread:
            self.setTabText(self.ERRORS_INDEX, f"Errors ●{self._unread}")
        else:
            self.setTabText(self.ERRORS_INDEX, "Errors")
