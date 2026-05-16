"""Slim user-presence strip rendered above the sidebar tabs.

Renders a short horizontal list of users in the current room: initial + name.
Ready users get a green dot prefix; controllers get a small key icon (text
placeholder for v1).
"""

from __future__ import annotations

from typing import Iterable

from PySide6 import QtCore, QtWidgets


class UserStrip(QtWidgets.QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(8)
        self._room_label = QtWidgets.QLabel("(no room)")
        self._room_label.setStyleSheet("color:#666; font-size: 11px;")
        self._layout.addWidget(self._room_label)
        self._layout.addStretch(1)
        self._user_widgets: list[QtWidgets.QLabel] = []

    def setRoom(self, room: str) -> None:
        self._room_label.setText(f"Room: {room}" if room else "(no room)")

    def setUsers(self, users: Iterable[dict]) -> None:
        # Tear down old labels
        for w in self._user_widgets:
            w.setParent(None)
            w.deleteLater()
        self._user_widgets.clear()

        # Insert before the stretch (which is the last item)
        stretch_index = self._layout.count() - 1
        for entry in users:
            name = entry.get("name", "?")
            ready = bool(entry.get("ready"))
            is_self = bool(entry.get("is_self"))
            dot = "🟢" if ready else "⚪"
            self_marker = " *" if is_self else ""
            label = QtWidgets.QLabel(f"{dot} {name}{self_marker}")
            label.setStyleSheet("font-size: 12px;")
            self._layout.insertWidget(stretch_index, label)
            self._user_widgets.append(label)
            stretch_index += 1
