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
from typing import Iterable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern import theme as theme_mod
from syncplay.ui.modern.events import RoomSnapshot
from syncplay.ui.modern.i18n import tr


class RoomPanel(QtWidgets.QWidget):

    readyToggleRequested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._theme: str = theme_mod.DEFAULT
        self._room_label_text = tr("room-none")
        # Source of truth for the ready button's colour. Stored as bool
        # so we don't string-match the localized label (which used to
        # break the green/grey palette in non-English UIs).
        self._is_ready = False
        # Cache the latest snapshot so retranslate() can repaint
        # snapshot-driven labels (room name, ready button text, ready
        # tooltip) without waiting for the next server update.
        self._last_snapshot: Optional["RoomSnapshot"] = None

        self._room_label = QtWidgets.QLabel(self._room_label_text)
        self._user_table = QtWidgets.QTableWidget(0, 3)
        self._user_table.setHorizontalHeaderLabels(
            ["", tr("room-col-user"), tr("room-col-file")]
        )
        self._user_table.verticalHeader().setVisible(False)
        self._user_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self._user_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._user_table.setShowGrid(False)
        self._user_table.setFocusPolicy(QtCore.Qt.NoFocus)
        header = self._user_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)

        self._log_header = QtWidgets.QLabel(tr("room-activity"))

        self._log = QtWidgets.QTextBrowser(self)
        self._log.setOpenExternalLinks(False)

        # Initial paint of all theme-driven styles.
        self._apply_label_styles(self._theme)
        self._log.document().setDefaultStyleSheet(self._build_log_css(self._theme))

        self._ready_btn = QtWidgets.QPushButton(tr("ready-join"))
        self._ready_btn.setMinimumHeight(36)
        self._ready_btn.clicked.connect(self.readyToggleRequested.emit)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(2)
        layout.addWidget(self._room_label, 0)
        layout.addWidget(self._user_table, 2)
        layout.addWidget(self._log_header, 0)
        layout.addWidget(self._log, 3)
        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(6, 4, 6, 0)
        button_row.addWidget(self._ready_btn, 1)
        layout.addLayout(button_row, 0)

    # --- Theme ------------------------------------------------------------

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self._apply_label_styles(theme)
        self._log.document().setDefaultStyleSheet(self._build_log_css(theme))
        # Re-skin the ready button by re-running set_snapshot's button
        # branch — easier than tracking the last snapshot state.
        self._refresh_ready_button_style()
        # Re-colour the "—" placeholder cell in any existing rows.
        self._refresh_empty_filename_cells()

    def retranslate(self) -> None:
        self._user_table.setHorizontalHeaderLabels(
            ["", tr("room-col-user"), tr("room-col-file")]
        )
        self._log_header.setText(tr("room-activity"))
        # Repaint snapshot-driven labels in the new language. If we
        # haven't seen a snapshot yet, fall back to the empty-room
        # placeholder + the default "ready" button label.
        snap = self._last_snapshot
        if snap is None:
            self._room_label.setText(tr("room-none"))
            self._ready_btn.setText(tr("ready-join"))
            self._ready_btn.setToolTip("")
        else:
            self.set_snapshot(snap)

    def _apply_label_styles(self, theme: str) -> None:
        p = theme_mod.palette(theme)
        self._room_label.setStyleSheet(
            f"color: {p['muted-label']}; font-size: 11px; padding: 4px 6px 0 6px;"
        )
        self._log_header.setStyleSheet(
            f"color: {p['muted-label']}; font-size: 11px; padding: 6px 6px 0 6px;"
        )

    @staticmethod
    def _build_log_css(theme: str) -> str:
        p = theme_mod.palette(theme)
        return (
            "p { margin: 2px 0; }"
            f".joined {{ color: {p['joined']}; }}"
            f".left {{ color: {p['left']}; }}"
            f".ready {{ color: {p['ready']}; font-weight: bold; }}"
            f".notready {{ color: {p['notready']}; }}"
            f".file {{ color: {p['file']}; }}"
            f".timestamp {{ color: {p['timestamp']}; font-size: 10px; }}"
        )

    def _refresh_ready_button_style(self) -> None:
        # Mirror the same colour choice set_snapshot uses, picked from
        # the current theme's palette so both states stay readable.
        p = theme_mod.palette(self._theme)
        if self._is_ready:
            bg = p["ready"]   # currently ready → green-ish
        else:
            bg = "#555555" if theme_mod.normalize(self._theme) == theme_mod.DARK else "#444444"
        self._ready_btn.setStyleSheet(
            f"QPushButton {{ background:{bg}; color:white; font-weight:bold; }}"
        )

    def _refresh_empty_filename_cells(self) -> None:
        p = theme_mod.palette(self._theme)
        empty_color = QtGui.QBrush(QtGui.QColor(p["filename-empty"]))
        for row in range(self._user_table.rowCount()):
            item = self._user_table.item(row, 2)
            if item is not None and item.text() == "—":
                item.setForeground(empty_color)

    # --- Public API --------------------------------------------------------

    def set_snapshot(self, snap: RoomSnapshot) -> None:
        self._last_snapshot = snap
        self._room_label.setText(
            tr("room-label", room=snap.room) if snap.room else tr("room-none")
        )

        p = theme_mod.palette(self._theme)
        empty_color = QtGui.QBrush(QtGui.QColor(p["filename-empty"]))

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
                file_item.setForeground(empty_color)
            self._user_table.setItem(row, 2, file_item)

        # Ready button reflects local user's state and is gated on having
        # a file loaded — readiness without media is meaningless and would
        # only confuse peers, who'd see "alice is ready" without knowing
        # what for.
        self_has_file = any(
            u.get("is_self") and u.get("filename")
            for u in snap.users
        )
        # syncplay-modern: ready-gated sync — the label spells out
        # the consequence so the user knows pressing it changes
        # whether they're in the group sync, not just a flag.
        self._is_ready = bool(snap.is_ready)
        if self._is_ready:
            self._ready_btn.setText(tr("ready-leave"))
        else:
            self._ready_btn.setText(tr("ready-join"))
        self._refresh_ready_button_style()
        self._ready_btn.setEnabled(snap.current_user is not None and self_has_file)
        self._ready_btn.setToolTip(
            "" if self_has_file else tr("ready-needs-file")
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
