"""Tab strip cycling Room / Chat / Queue / Errors with an unread badge on Errors."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class SidebarTabs(QtWidgets.QTabWidget):

    ROOM_INDEX = 0
    CHAT_INDEX = 1
    QUEUE_INDEX = 2
    ERRORS_INDEX = 3

    def __init__(
        self,
        room_panel: QtWidgets.QWidget,
        chat_panel: QtWidgets.QWidget,
        queue_panel: QtWidgets.QWidget,
        errors_panel: QtWidgets.QWidget,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._unread = 0
        self.addTab(room_panel, "Room")
        self.addTab(chat_panel, "Chat")
        self.addTab(queue_panel, "Queue")
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
