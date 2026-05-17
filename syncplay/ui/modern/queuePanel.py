"""Queue (shared playlist) tab.

Renders the room-wide shared playlist as a list with the current
item highlighted, exposes an "Add file…" button and drag-drop, and
emits signals back to MainWindow for the client to act on (the actual
network calls live in MainWindow because this widget stays
client-agnostic).
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern.events import (
    PlaylistAppended,
    PlaylistChanged,
    PlaylistIndexChanged,
)


class QueuePanel(QtWidgets.QWidget):

    addFilesRequested = QtCore.Signal(list)        # list[str] of paths
    indexChangeRequested = QtCore.Signal(str)      # filename selected
    removeAtIndexRequested = QtCore.Signal(int)    # 0-based index

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        self._files: list[str] = []
        self._current_filename: Optional[str] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._empty_hint = QtWidgets.QLabel(
            "Drag a video file here or click “Add file…” to "
            "start a shared queue. Items are visible to everyone in the room.",
            self,
        )
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self._empty_hint)

        self._list = QtWidgets.QListWidget(self)
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list, 1)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self._add_btn = QtWidgets.QPushButton("Add file…", self)
        self._add_btn.clicked.connect(self._on_add_clicked)
        button_row.addWidget(self._add_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self._refresh_visibility()

    # --- Public surface (called by MainWindow on router events) ----------

    def on_playlist_event(self, event) -> None:
        if isinstance(event, PlaylistChanged):
            self._files = list(event.files)
            if event.current_filename is not None:
                self._current_filename = event.current_filename
            self._rebuild_list()
        elif isinstance(event, PlaylistAppended):
            if event.filename and event.filename not in self._files:
                self._files.append(event.filename)
                self._rebuild_list()
        elif isinstance(event, PlaylistIndexChanged):
            self._current_filename = event.filename
            self._rebuild_list()

    # --- Drag-drop ---------------------------------------------------------

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if paths:
            self.addFilesRequested.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    # --- Internals ---------------------------------------------------------

    def _rebuild_list(self) -> None:
        self._list.clear()
        for filename in self._files:
            item = QtWidgets.QListWidgetItem(self._display_name(filename), self._list)
            item.setData(QtCore.Qt.UserRole, filename)
            if filename == self._current_filename:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
        self._refresh_visibility()

    def _refresh_visibility(self) -> None:
        is_empty = not self._files
        self._empty_hint.setVisible(is_empty)
        self._list.setVisible(not is_empty)

    @staticmethod
    def _display_name(filename: str) -> str:
        # Names from upstream are typically already basenames; strip any
        # path prefix defensively so the list stays readable.
        return os.path.basename(filename.replace("\\", "/")) or filename

    def _on_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        filename = item.data(QtCore.Qt.UserRole)
        if filename:
            self.indexChangeRequested.emit(str(filename))

    def _on_add_clicked(self) -> None:
        paths, _filter = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Add files to playlist",
            "",
            "Video files (*.mkv *.mp4 *.avi *.mov *.webm *.ts *.m4v);;All files (*)",
        )
        if paths:
            self.addFilesRequested.emit(list(paths))

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self)
        play_action = menu.addAction("Play this")
        remove_action = menu.addAction("Remove from queue")
        chosen = menu.exec(self._list.viewport().mapToGlobal(pos))
        if chosen is play_action:
            self._on_item_double_clicked(item)
        elif chosen is remove_action:
            index = self._list.row(item)
            if index >= 0:
                self.removeAtIndexRequested.emit(index)
