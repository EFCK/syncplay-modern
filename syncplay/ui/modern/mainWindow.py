"""MainWindow — the syncplay-modern UI shell.

Implements the UI contract `SyncplayClient` calls into (it is the `ui` object
passed in via `clientManager.py`). Internally it delegates non-rendering
responsibilities to a Qt-free `MessageRouter` (for unit-testability) and
renders router events through the chat/errors/user widgets.

Threading: under `qt5reactor` the Twisted reactor runs on the Qt main thread,
so every UiManager call lands here on the main thread and we can touch Qt
widgets directly. No `callFromThread` plumbing required at this layer.
"""

from __future__ import annotations

import sys
import time
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay import constants
from syncplay.players import embedded_vlc

from syncplay.ui.modern.chatPanel import ChatPanel
from syncplay.ui.modern.errorsPanel import ErrorsPanel
from syncplay.ui.modern.events import (
    ChatMessage,
    ConnectionState,
    ConnectionStateKind,
    ErrorEvent,
    SyncEvent,
    UserPresence,
)
from syncplay.ui.modern.messageRouter import MessageRouter
from syncplay.ui.modern.sidebarTabs import SidebarTabs
from syncplay.ui.modern.userStrip import UserStrip
from syncplay.ui.modern.videoWidget import VideoWidget


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, passedBar=None) -> None:  # noqa: N803 — keep upstream name
        super().__init__()
        self.uiMode = constants.GRAPHICAL_UI_MODE
        self.setWindowTitle("syncplay-modern")
        self.resize(1100, 660)

        self._client = None
        self._router = MessageRouter()
        self._router.subscribe(self._on_router_event)

        # --- Left: embedded libvlc render surface
        self.videoWidget = VideoWidget()
        self.videoWidget.fileDropped.connect(self._on_file_dropped)
        # Register with the player module — the EmbeddedVlcPlayer instance
        # (constructed later, when the reactor calls EmbeddedVlcPlayer.run)
        # picks this up to attach libvlc's render surface.
        embedded_vlc.set_video_widget(self.videoWidget)

        # --- Right: user strip on top, sidebar tabs below
        self._user_strip = UserStrip()
        self._chat_panel = ChatPanel()
        self._errors_panel = ErrorsPanel()
        self._tabs = SidebarTabs(self._chat_panel, self._errors_panel)

        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._user_strip, 0)
        right_layout.addWidget(self._tabs, 1)

        # --- Splitter
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self._splitter.addWidget(self.videoWidget)
        self._splitter.addWidget(right_container)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([700, 320])

        self.setCentralWidget(self._splitter)

        # --- Menu bar
        self._build_menu()

        # --- Status bar
        self._status_room = QtWidgets.QLabel("(no room)")
        self._status_room.setStyleSheet("color:#666;")
        self._status_conn = QtWidgets.QLabel("●")
        self._status_conn.setStyleSheet("color:#bbb;")
        self._status_conn.setToolTip("Connection: idle")

        self.statusBar().addWidget(self._status_room, 1)
        self.statusBar().addPermanentWidget(self._status_conn, 0)

        # --- Wiring
        self._chat_panel.chatSubmitted.connect(self._on_chat_submit)

        self.show()

    # ----------------------------------------------------------------------
    # UI contract — SyncplayClient.UiManager calls these directly.
    # We delegate to MessageRouter, which classifies and emits typed events.
    # ----------------------------------------------------------------------

    def addClient(self, client) -> None:
        self._client = client
        self._router.addClient(client)
        self._maybe_schedule_autochat()

    def showChatMessage(self, username, userMessage):
        own = self._own_username()
        if username == own and own is not None:
            # Echo of our own message — render as is_self so it appears as
            # the "me" bubble; emit a tailored ChatMessage instead of letting
            # the router default to is_self=False.
            self._render_chat_self(username, userMessage)
            return
        self._router.showChatMessage(username, userMessage)

    def showMessage(self, message, noTimestamp=False, isMotd=False):
        self._router.showMessage(message, noTimestamp=noTimestamp, isMotd=isMotd)
        if getattr(constants, "DEBUG_MODE", False):
            print(f"[GUI] {message}", file=sys.stderr, flush=True)

    def showOSDMessage(self, message, duration=None, OSDType=None, mood=None):
        return  # OSD overlays suppressed — chat panel surfaces equivalents.

    def showErrorMessage(self, message, criticalerror=False):
        self._router.showErrorMessage(message, criticalerror=criticalerror)
        if getattr(constants, "DEBUG_MODE", False):
            print(f"[ERR] {message}", file=sys.stderr, flush=True)

    def showDebugMessage(self, message):
        if getattr(constants, "DEBUG_MODE", False):
            print(f"[debug] {message}", file=sys.stderr, flush=True)

    def showUserList(self, currentUser, rooms):
        users: list[dict] = []
        current_room = ""
        for room_name, members in rooms.items():
            for user in members:
                users.append({
                    "name": getattr(user, "username", "?"),
                    "ready": user.isReady() if hasattr(user, "isReady") else False,
                    "is_self": (user is currentUser),
                })
            if currentUser in members:
                current_room = room_name
        self._user_strip.setRoom(current_room)
        self._user_strip.setUsers(users)

    def updateRoomName(self, room=""):
        self._status_room.setText(f"Room: {room}" if room else "(no room)")
        self._user_strip.setRoom(room)

    def updateAutoPlayState(self, newState):
        return

    def addRoomToList(self, *args, **kwargs):
        return

    def userListChange(self):
        client = self._client
        if client is None:
            return
        ul = getattr(client, "userlist", None)
        if ul is None:
            return
        currentUser = getattr(ul, "currentUser", None)
        rooms_attr = getattr(ul, "_rooms", None) or getattr(ul, "rooms", None)
        if currentUser is None or rooms_attr is None:
            return
        try:
            self.showUserList(currentUser, rooms_attr)
        except Exception:
            return

    def markEndOfUserlist(self):
        return

    def promptFor(self, prompt=">", message=""):
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Syncplay", message or prompt
        )
        return text if ok else ""

    def setSSLMode(self, sslMode, sslInfo=""):
        if sslMode:
            self._status_conn.setToolTip("Connection: TLS")
        return

    def setControllerStatus(self, username, isController):
        return

    def setFeatures(self, featureList):
        return

    def addFileToPlaylist(self, item):
        return

    def setPlaylist(self, newPlaylist, newIndexFilename=None):
        return

    def setPlaylistIndexFilename(self, filename):
        return

    def fileSwitchFoundFiles(self):
        return

    def executeCommand(self, command):
        return

    def drop(self):
        return

    def getUIMode(self):
        return "GUI"

    # ----------------------------------------------------------------------
    # Internals
    # ----------------------------------------------------------------------

    def _on_router_event(self, event) -> None:
        if isinstance(event, ChatMessage):
            self._chat_panel.render_chat(event)
        elif isinstance(event, SyncEvent):
            self._chat_panel.render_sync(event)
        elif isinstance(event, ErrorEvent):
            self._errors_panel.render_error(event)
            self._tabs.note_error()
            self._chat_panel.render_error_notice()
        elif isinstance(event, ConnectionState):
            self._on_connection_state(event)
        elif isinstance(event, UserPresence):
            self._user_strip.setRoom(event.room)
            self._user_strip.setUsers(event.users)

    def _on_connection_state(self, event: ConnectionState) -> None:
        if event.state == ConnectionStateKind.CONNECTED:
            self._status_conn.setStyleSheet("color:#2a8;")
            self._status_conn.setToolTip("Connection: connected")
        elif event.state == ConnectionStateKind.DISCONNECTED:
            self._status_conn.setStyleSheet("color:#c33;")
            self._status_conn.setToolTip("Connection: disconnected")
        elif event.state == ConnectionStateKind.RECONNECTING:
            self._status_conn.setStyleSheet("color:#fb3;")
            self._status_conn.setToolTip("Connection: reconnecting")
        elif event.state == ConnectionStateKind.CONNECTING:
            self._status_conn.setStyleSheet("color:#fb3;")
            self._status_conn.setToolTip("Connection: connecting")

    def _on_chat_submit(self, text: str) -> None:
        if self._client is None or not text:
            return
        if hasattr(self._client, "sendChat"):
            self._client.sendChat(text)

    def _on_file_dropped(self, path: str) -> None:
        self._open_local_file(path)

    def _open_local_file(self, path: str) -> None:
        if not path:
            return
        if self._client is None or not hasattr(self._client, "openFile"):
            return
        try:
            self._client.openFile(path, fromUser=True)
        except TypeError:
            # Older client signature
            self._client.openFile(path)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")

        open_file = QtGui.QAction("&Open File…", self)
        open_file.setShortcut(QtGui.QKeySequence.Open)
        open_file.triggered.connect(self._dialog_open_file)
        file_menu.addAction(open_file)

        open_url = QtGui.QAction("Open &URL…", self)
        open_url.triggered.connect(self._dialog_open_url)
        file_menu.addAction(open_url)

        file_menu.addSeparator()

        quit_act = QtGui.QAction("&Quit", self)
        quit_act.setShortcut(QtGui.QKeySequence.Quit)
        quit_act.triggered.connect(QtWidgets.QApplication.quit)
        file_menu.addAction(quit_act)

    def _dialog_open_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Media",
            "",
            "Media files (*.mkv *.mp4 *.avi *.mov *.webm *.m4v *.flv *.wmv *.mpg *.mpeg *.ts);;All files (*)",
        )
        if path:
            self._open_local_file(path)

    def _dialog_open_url(self) -> None:
        url, ok = QtWidgets.QInputDialog.getText(
            self, "Open URL", "Stream URL:", QtWidgets.QLineEdit.Normal, ""
        )
        if ok and url.strip():
            self._open_local_file(url.strip())

    def _render_chat_self(self, username: str, text: str) -> None:
        self._chat_panel.render_chat(
            ChatMessage(user=username, text=text, is_self=True, timestamp=time.time())
        )

    def _maybe_schedule_autochat(self) -> None:
        # Debug-only hook used by the headless two-instance smoke test:
        # SYNCPLAY_AUTOCHAT_MSG=foo SYNCPLAY_AUTOCHAT_AFTER_S=4 schedules a
        # one-shot client.sendChat("foo") via the Twisted reactor 4s after
        # the client is registered. Has no effect in normal runs.
        import os
        msg = os.environ.get("SYNCPLAY_AUTOCHAT_MSG")
        after_s = os.environ.get("SYNCPLAY_AUTOCHAT_AFTER_S")
        if not msg or not after_s:
            return
        try:
            delay = float(after_s)
        except ValueError:
            return
        from twisted.internet import reactor

        def fire():
            if self._client is not None and hasattr(self._client, "sendChat"):
                self._client.sendChat(msg)
        reactor.callLater(delay, fire)

    def _own_username(self) -> Optional[str]:
        client = self._client
        if client is None:
            return None
        cfg = getattr(client, "_config", None) or {}
        return cfg.get("name")
