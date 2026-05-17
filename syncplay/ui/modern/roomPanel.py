"""Room tab: current-state view of the room.

Three vertical regions:

1. **User table** — every user in the room with their ready dot, name,
   self marker, and currently-loaded filename. Re-rendered whole on
   every `RoomSnapshot`.
2. **Event log** — scrolling chronological feed of join / leave / ready
   / file-load events derived from snapshot diffs.
3. **Ready toggle** — single button whose label reflects the local
   user's current ready state. Clicking emits `readyToggleRequested`;
   MainWindow connects it to `client.toggleReady(...)`.

The panel renders state — it doesn't decide it. RoomState produces the
events; this panel just paints them.
"""

from __future__ import annotations

import html
import time
from typing import Iterable

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern.events import RoomSnapshot


class RoomPanel(QtWidgets.QWidget):

    readyToggleRequested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._room_label = QtWidgets.QLabel("(no room)")
        self._room_label.setStyleSheet("color:#666; font-size: 11px; padding: 4px 6px 0 6px;")

        self._user_table = QtWidgets.QTableWidget(0, 3)
        self._user_table.setHorizontalHeaderLabels(["", "User", "File"])
        self._user_table.verticalHeader().setVisible(False)
        self._user_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self._user_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._user_table.setShowGrid(False)
        self._user_table.setFocusPolicy(QtCore.Qt.NoFocus)
        header = self._user_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)

        log_header = QtWidgets.QLabel("Activity")
        log_header.setStyleSheet("color:#666; font-size: 11px; padding: 6px 6px 0 6px;")

        self._log = QtWidgets.QTextBrowser(self)
        self._log.setOpenExternalLinks(False)
        self._log.document().setDefaultStyleSheet(
            "p { margin: 2px 0; }"
            ".joined { color: #2a8; }"
            ".left { color: #888; }"
            ".ready { color: #2a8; font-weight: bold; }"
            ".notready { color: #a35; }"
            ".file { color: #1d6fa5; }"
            ".timestamp { color: #aaa; font-size: 10px; }"
        )

        self._ready_btn = QtWidgets.QPushButton("I'm ready")
        self._ready_btn.setMinimumHeight(36)
        self._ready_btn.clicked.connect(self.readyToggleRequested.emit)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(2)
        layout.addWidget(self._room_label, 0)
        layout.addWidget(self._user_table, 2)
        layout.addWidget(log_header, 0)
        layout.addWidget(self._log, 3)
        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(6, 4, 6, 0)
        button_row.addWidget(self._ready_btn, 1)
        layout.addLayout(button_row, 0)

    # --- Public API --------------------------------------------------------

    def set_snapshot(self, snap: RoomSnapshot) -> None:
        self._room_label.setText(f"Room: {snap.room}" if snap.room else "(no room)")

        # Rebuild the user table from scratch — small enough that
        # incremental updates aren't worth the complexity.
        self._user_table.setRowCount(len(snap.users))
        for row, user in enumerate(snap.users):
            ready = bool(user.get("ready"))
            is_self = bool(user.get("is_self"))
            name = str(user.get("name", "?"))
            filename = str(user.get("filename") or "")

            dot_item = QtWidgets.QTableWidgetItem("🟢" if ready else "⚪")
            dot_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self._user_table.setItem(row, 0, dot_item)

            display_name = f"{name} (you)" if is_self else name
            name_item = QtWidgets.QTableWidgetItem(display_name)
            if is_self:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            self._user_table.setItem(row, 1, name_item)

            file_item = QtWidgets.QTableWidgetItem(filename if filename else "—")
            if not filename:
                file_item.setForeground(QtGui.QBrush(QtGui.QColor("#aaa")))
            self._user_table.setItem(row, 2, file_item)

        # Ready button reflects local user's state and is gated on having
        # a file loaded — readiness without media is meaningless and would
        # only confuse peers, who'd see "alice is ready" without knowing
        # what for.
        self_has_file = any(
            u.get("is_self") and u.get("filename")
            for u in snap.users
        )
        if snap.is_ready:
            self._ready_btn.setText("I'm not ready")
            self._ready_btn.setStyleSheet("QPushButton { background:#2a8; color:white; font-weight:bold; }")
        else:
            self._ready_btn.setText("I'm ready")
            self._ready_btn.setStyleSheet("QPushButton { background:#444; color:white; font-weight:bold; }")
        self._ready_btn.setEnabled(snap.current_user is not None and self_has_file)
        self._ready_btn.setToolTip(
            "" if self_has_file else "Open a video file before marking yourself ready"
        )

    def append_log_line(self, html_class: str, text: str, timestamp: float | None = None) -> None:
        ts = time.strftime("%H:%M:%S", time.localtime(timestamp or time.time()))
        line = (
            f'<p class="{html_class}"><span class="timestamp">{ts}</span> '
            f'{html.escape(text)}</p>'
        )
        cursor = self._log.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        # Force a new QTextDocument block before each fragment — without
        # this, successive insertHtml() calls coalesce into the same
        # paragraph and the events run together on one line.
        if cursor.position() > 0:
            cursor.insertBlock()
        cursor.insertHtml(line)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
