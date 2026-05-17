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
    RoomSnapshot,
    SyncEvent,
    UserFileChanged,
    UserJoined,
    UserLeft,
    UserPresence,
    UserReadyChanged,
)
from syncplay.ui.modern.messageRouter import MessageRouter
from syncplay.ui.modern.roomPanel import RoomPanel
from syncplay.ui.modern.roomState import RoomState
from syncplay.ui.modern.settingsPanel import SettingsDialog
from syncplay.ui.modern.sidebarTabs import SidebarTabs
from syncplay.ui.modern.userStrip import UserStrip
from syncplay.ui.modern.videoControls import VideoControls
from syncplay.ui.modern.videoWidget import VideoWidget


class _MouseEdgeFilter(QtCore.QObject):
    """Application-wide mouse-move filter used while fullscreen.

    Forwards every MouseMove event to MainWindow so it can reveal the chat
    overlay when the cursor approaches the right edge of the screen.
    """

    def __init__(self, window):
        super().__init__(window)
        self._window = window

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseMove:
            try:
                self._window._fs_on_global_mouse_move(event.globalPosition().toPoint())
            except Exception:
                pass
        return False  # never consume the event


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, passedBar=None) -> None:  # noqa: N803 — keep upstream name
        super().__init__()
        self.uiMode = constants.GRAPHICAL_UI_MODE
        self.setWindowTitle("syncplay-modern")
        self.resize(1100, 660)

        self._client = None
        self._router = MessageRouter()
        self._router.subscribe(self._on_router_event)
        self._room_state = RoomState()
        self._room_state.subscribe(self._on_router_event)

        # --- Left: embedded libvlc render surface
        self.videoWidget = VideoWidget()
        self.videoWidget.fileDropped.connect(self._on_file_dropped)
        # Register with the player module — the EmbeddedVlcPlayer instance
        # (constructed later, when the reactor calls EmbeddedVlcPlayer.run)
        # picks this up to attach libvlc's render surface.
        embedded_vlc.set_video_widget(self.videoWidget)
        embedded_vlc.set_fileinfo_sink(self._on_fileinfo)

        # Latest parsed-media metadata; populated when libvlc parses a file.
        self._fileinfo: Optional[dict] = None
        self._settings_dialog: Optional[SettingsDialog] = None

        # Fullscreen state
        self._is_fullscreen = False
        self._overlay: Optional[QtWidgets.QFrame] = None
        self._saved_chat_visible: bool = True
        self._mouse_filter = _MouseEdgeFilter(self)
        self._autohide_timer = QtCore.QTimer(self)
        self._autohide_timer.setSingleShot(True)
        self._autohide_timer.timeout.connect(self._fs_hide_overlay)

        # --- Right: user strip on top, sidebar tabs below
        self._user_strip = UserStrip()
        self._chat_panel = ChatPanel()
        self._room_panel = RoomPanel()
        self._room_panel.readyToggleRequested.connect(self._on_ready_toggle)
        self._errors_panel = ErrorsPanel()
        self._tabs = SidebarTabs(self._room_panel, self._chat_panel, self._errors_panel)

        self._right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(self._right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._user_strip, 0)
        right_layout.addWidget(self._tabs, 1)

        # --- Main horizontal layout: video | toggle | chat at fixed 80/20.
        # Dragging an QSplitter over libvlc's native window was racy
        # (resize storm during the drag confused the X surface and the
        # control bar overlay flickered), so the split is now a fixed
        # ratio and the only knob is "chat visible / hidden", driven by
        # a thin clickable strip between the two panes.
        self._chat_visible = True
        self._chat_toggle = QtWidgets.QToolButton(self)
        self._chat_toggle.setText("❯")  # heavy right-pointing angle
        self._chat_toggle.setFixedSize(22, 22)  # square; vertically centered in its slot
        self._chat_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._chat_toggle.setToolTip("Hide chat")
        self._chat_toggle.setFocusPolicy(QtCore.Qt.NoFocus)
        self._chat_toggle.setStyleSheet(
            "QToolButton { background: transparent; color: #ccc; "
            "border: none; font-size: 14px; font-weight: bold; padding: 0; }"
            "QToolButton:hover { background: rgba(255, 255, 255, 30); "
            "color: #fff; border-radius: 3px; }"
            "QToolButton:pressed { background: rgba(0, 0, 0, 80); }"
        )
        self._chat_toggle.clicked.connect(self._toggle_chat_panel)

        main = QtWidgets.QWidget()
        # Black background on the wrapper: videoWidget has
        # WA_OpaquePaintEvent + an empty paintEvent (otherwise Qt would
        # repaint over libvlc), so when the chat is hidden the newly
        # uncovered region of the X window has no fresh paint and shows
        # stale chat pixels until libvlc's next frame. A black-filled
        # wrapper means the fall-through area is at least black.
        main.setAutoFillBackground(True)
        pal = main.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(0, 0, 0))
        main.setPalette(pal)
        self._main_layout = QtWidgets.QHBoxLayout(main)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)
        self._main_layout.addWidget(self.videoWidget, 4)
        self._main_layout.addWidget(self._chat_toggle, 0, QtCore.Qt.AlignVCenter)
        self._main_layout.addWidget(self._right_container, 1)
        self._main_wrapper = main

        self.setCentralWidget(main)

        # --- Menu bar
        self._build_menu()

        # --- Keyboard shortcuts (focus-aware: only fire when the video
        # widget or its descendants have focus, not when the chat input
        # has focus).
        self._install_shortcuts()

        # Default focus → video, so shortcuts work without an extra click
        self.videoWidget.setFocus()

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

        # --- Video control bar (auto-hiding overlay)
        self._video_controls = VideoControls(self)
        self._video_controls.hide()
        self._video_controls.playPauseRequested.connect(self._kb_toggle_pause)
        self._video_controls.seekToSecondsRequested.connect(self._on_seek_to_seconds)
        self._video_controls.volumeChangedTo.connect(self._on_volume_set)
        self._video_controls.muteToggleRequested.connect(self._kb_mute)
        self._video_controls.fullscreenToggleRequested.connect(self._kb_toggle_fullscreen)

        self._vc_last_cursor_pos = QtGui.QCursor.pos()
        self._vc_last_motion_time = time.monotonic()
        self._vc_poll_timer = QtCore.QTimer(self)
        self._vc_poll_timer.setInterval(120)
        self._vc_poll_timer.timeout.connect(self._vc_tick)
        self._vc_poll_timer.start()

        self._vc_state_timer = QtCore.QTimer(self)
        self._vc_state_timer.setInterval(500)
        self._vc_state_timer.timeout.connect(self._vc_refresh_state)
        self._vc_state_timer.start()

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
        # MOTD = server-side message of the day (e.g. "Syncplay latest
        # is available from http://syncplay.pl/"). Always suppress.
        if isMotd:
            return
        # Upstream's SyncplayClientManager.showChatMessage formats peer
        # chat as "<username> message" and feeds it through here — it
        # never calls our showChatMessage. Detect that pattern and
        # render it as a chat bubble instead of as a gray sync line.
        chat = self._detect_chat_message(message)
        if chat is not None:
            username, text = chat
            own = self._own_username()
            is_self = (own is not None and username == own)
            self._chat_panel.render_chat(
                ChatMessage(user=username, text=text, is_self=is_self, timestamp=time.time())
            )
            return
        self._router.showMessage(message, noTimestamp=noTimestamp, isMotd=isMotd)
        if getattr(constants, "DEBUG_MODE", False):
            print(f"[GUI] {message}", file=sys.stderr, flush=True)

    def _detect_chat_message(self, message: str):
        # Upstream format: "<{username}> {userMessage}". We don't verify
        # username is in the current userlist (that check was unreliable
        # under real upstream timing). Pattern + no whitespace/angles in
        # the username is enough — false positives on system messages
        # are rare and cosmetic.
        if not message or not message.startswith("<"):
            return None
        end = message.find("> ")
        if end < 2:
            return None
        username = message[1:end]
        if not username or any(c in username for c in "<>\n\r\t "):
            return None
        text = message[end + 2:]
        return username, text

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
        # Also feed the Room tab: diff against the previous snapshot and
        # emit the per-user typed events + a fresh RoomSnapshot.
        try:
            self._room_state.update_from_rooms(currentUser, rooms)
        except Exception:
            if getattr(constants, "DEBUG_MODE", False):
                import traceback
                traceback.print_exc()

    def updateRoomName(self, room=""):
        self._status_room.setText(f"Room: {room}" if room else "(no room)")
        self._user_strip.setRoom(room)

    def updateAutoPlayState(self, newState):
        return

    def addRoomToList(self, *args, **kwargs):
        return

    def userListChange(self):
        # Upstream's userlist stores users flat in `_users` and doesn't keep
        # a per-room dict — that has to be rebuilt from scratch. Delegating
        # to client.showUserList() routes through userlist.showUserList(),
        # which builds the rooms dict and calls back into our
        # showUserList(currentUser, rooms). Without this, the post-toggle
        # echo-back never refreshes the Room snapshot and the Ready button
        # label never flips.
        client = self._client
        if client is None:
            return
        try:
            client.showUserList()
        except Exception:
            if getattr(constants, "DEBUG_MODE", False):
                import traceback
                traceback.print_exc()

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
        elif isinstance(event, RoomSnapshot):
            self._room_panel.set_snapshot(event)
        elif isinstance(event, UserJoined):
            # Chat shows upstream's "X has joined the room: 'r'" line on
            # its own; here we only feed the short form to the Room tab
            # activity log so it doesn't double up.
            self._room_panel.append_log_line("joined", f"→ {event.user} joined", event.timestamp)
        elif isinstance(event, UserLeft):
            self._room_panel.append_log_line("left", f"← {event.user} left", event.timestamp)
        elif isinstance(event, UserReadyChanged):
            cls = "ready" if event.ready else "notready"
            verb = "is ready" if event.ready else "is not ready"
            self._room_panel.append_log_line(cls, f"• {event.user} {verb}", event.timestamp)
        elif isinstance(event, UserFileChanged):
            self._room_panel.append_log_line(
                "file",
                f"♪ {event.user} loaded {event.filename}",
                event.timestamp,
            )

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

    def _on_ready_toggle(self) -> None:
        if self._client is None:
            return
        # Compute the target from our snapshot, not from
        # client.userlist.currentUser.isReady(). Upstream's toggleReady
        # does `not isReady()` — but isReady() can transiently return
        # None (interpreted as falsy → "not ready"), so toggling from
        # None re-asserts ready instead of clearing it. Bypassing that
        # and calling _protocol.setReady(target, True) directly with
        # our snapshot's known state avoids the ambiguity.
        target_ready = not self._room_state.last_self_ready()
        protocol = getattr(self._client, "_protocol", None)
        if getattr(constants, "DEBUG_MODE", False):
            print(f"[ready] toggle → target={target_ready}", file=sys.stderr, flush=True)
        if protocol is not None and hasattr(protocol, "setReady"):
            try:
                protocol.setReady(target_ready, True)
                return
            except Exception as exc:
                if getattr(constants, "DEBUG_MODE", False):
                    print(f"[ready] protocol.setReady failed: {exc}",
                          file=sys.stderr, flush=True)
        # Fallback: upstream's wrapper. Works in the common case but
        # has the None-state ambiguity described above.
        if hasattr(self._client, "toggleReady"):
            try:
                self._client.toggleReady(manuallyInitiated=True)
            except TypeError:
                self._client.toggleReady()

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

        edit_menu = bar.addMenu("&Edit")
        settings_act = QtGui.QAction("&Settings…", self)
        settings_act.setShortcut("Ctrl+,")
        settings_act.triggered.connect(self._open_settings)
        edit_menu.addAction(settings_act)

    def _install_shortcuts(self) -> None:
        """VLC-style keyboard shortcuts, scoped to the video widget."""
        scope = QtCore.Qt.WidgetWithChildrenShortcut

        def make(seq, handler):
            sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self.videoWidget)
            sc.setContext(scope)
            sc.activated.connect(handler)
            return sc

        # Playback
        make("Space", self._kb_toggle_pause)
        make("K", self._kb_toggle_pause)
        # Seek
        make("Right", lambda: self._kb_seek(5.0))
        make("Left", lambda: self._kb_seek(-5.0))
        make("Shift+Right", lambda: self._kb_seek(10.0))
        make("Shift+Left", lambda: self._kb_seek(-10.0))
        make("Ctrl+Right", lambda: self._kb_seek(60.0))
        make("Ctrl+Left", lambda: self._kb_seek(-60.0))
        # Volume
        make("Up", lambda: self._kb_volume(5))
        make("Down", lambda: self._kb_volume(-5))
        make("M", self._kb_mute)
        # Delay tweaks
        make("J", lambda: self._kb_audio_delay(-50))
        make("L", lambda: self._kb_audio_delay(50))
        make("G", lambda: self._kb_subtitle_delay(-50))
        make("H", lambda: self._kb_subtitle_delay(50))
        # Speed
        make("[", lambda: self._kb_speed(1 / 1.1))
        make("]", lambda: self._kb_speed(1.1))
        make("=", self._kb_reset_speed)
        # Fullscreen
        make("F", self._kb_toggle_fullscreen)
        make("Escape", self._kb_exit_fullscreen)

    # --- Shortcut handlers ------------------------------------------------

    def _player_or_none(self):
        if self._client is None:
            return None
        return getattr(self._client, "_player", None)

    def _kb_toggle_pause(self):
        player = self._player_or_none()
        if player is None:
            return
        target_paused = not player.is_paused()
        # Route through SyncplayClient so the canonical state machine
        # (which manages _lastPlayerUpdate and broadcast timing) sees
        # this as a user-initiated change. Falling back to the player
        # directly only when there's no client yet — e.g. a file was
        # opened before the connection finished.
        if self._client is not None and hasattr(self._client, "setPaused"):
            self._client.setPaused(target_paused)
        else:
            player.setPaused(target_paused)

    def _kb_seek(self, delta_s: float):
        player = self._player_or_none()
        if player and hasattr(player, "seek_by_seconds"):
            player.seek_by_seconds(delta_s)

    def _kb_volume(self, delta: int):
        player = self._player_or_none()
        if player and hasattr(player, "adjust_volume"):
            new_vol = player.adjust_volume(delta)
            self._brief_status(f"Volume {new_vol}%")

    def _kb_mute(self):
        player = self._player_or_none()
        if player and hasattr(player, "toggle_mute"):
            player.toggle_mute()
            self._brief_status("Muted" if player.is_muted() else "Unmuted")

    def _kb_audio_delay(self, delta_ms: int):
        player = self._player_or_none()
        if player and hasattr(player, "adjust_audio_delay_ms"):
            new_ms = player.adjust_audio_delay_ms(delta_ms)
            self._brief_status(f"Audio delay {new_ms:+d} ms")

    def _kb_subtitle_delay(self, delta_ms: int):
        player = self._player_or_none()
        if player and hasattr(player, "adjust_subtitle_delay_ms"):
            new_ms = player.adjust_subtitle_delay_ms(delta_ms)
            self._brief_status(f"Subtitle delay {new_ms:+d} ms")

    def _kb_speed(self, multiplier: float):
        player = self._player_or_none()
        if player and hasattr(player, "adjust_speed"):
            new_rate = player.adjust_speed(multiplier)
            self._brief_status(f"Speed {new_rate:.2f}x")

    def _kb_reset_speed(self):
        player = self._player_or_none()
        if player and hasattr(player, "reset_speed"):
            player.reset_speed()
            self._brief_status("Speed 1.00x")

    def _kb_toggle_fullscreen(self):
        if self._is_fullscreen:
            self._fs_exit()
        else:
            self._fs_enter()

    def _kb_exit_fullscreen(self):
        if self._is_fullscreen:
            self._fs_exit()

    # --- Video control bar (auto-hide) -----------------------------------

    VC_HIDE_AFTER_S = 2.5      # auto-hide after no cursor motion for this long
    VC_BAR_HEIGHT = 34         # matches VideoControls.setFixedHeight
    VC_BAR_MARGIN = 8          # pixels of space below the bar
    VC_MIN_BAR_WIDTH = 280     # below this the bar is hidden — splitter too narrow

    def _on_seek_to_seconds(self, seconds: float) -> None:
        player = self._player_or_none()
        if player and hasattr(player, "setPosition"):
            player.setPosition(float(seconds))

    def _on_volume_set(self, value: int) -> None:
        player = self._player_or_none()
        if player and hasattr(player, "set_volume"):
            player.set_volume(int(value))

    def _vc_video_geometry_global(self) -> QtCore.QRect:
        """Return videoWidget's bounding rect in global screen coords."""
        top_left = self.videoWidget.mapToGlobal(QtCore.QPoint(0, 0))
        size = self.videoWidget.size()
        return QtCore.QRect(top_left, size)

    def _vc_position_bar(self) -> bool:
        """Position the bar inside the video area. Return False (and
        leave the bar untouched) if the area is too narrow to host it.
        """
        video_rect = self._vc_video_geometry_global()
        win_top_left = self.mapFromGlobal(video_rect.topLeft())
        width = video_rect.width() - 2 * self.VC_BAR_MARGIN
        if width < self.VC_MIN_BAR_WIDTH:
            return False
        x = win_top_left.x() + self.VC_BAR_MARGIN
        y = win_top_left.y() + video_rect.height() - self.VC_BAR_HEIGHT - self.VC_BAR_MARGIN
        self._video_controls.setGeometry(x, y, width, self.VC_BAR_HEIGHT)
        return True

    def _vc_cursor_over_video_or_bar(self) -> bool:
        pos = QtGui.QCursor.pos()
        if self._video_controls.isVisible():
            bar_rect = QtCore.QRect(
                self._video_controls.mapToGlobal(QtCore.QPoint(0, 0)),
                self._video_controls.size(),
            )
            if bar_rect.contains(pos):
                return True
        return self._vc_video_geometry_global().contains(pos)

    def _vc_show_bar(self) -> None:
        if not self._client_has_media():
            return
        if not self._vc_position_bar():
            # Video pane too narrow to host the bar — make sure it's
            # not lingering on screen from a previous wider layout.
            if self._video_controls.isVisible():
                self._video_controls.hide()
            return
        if not self._video_controls.isVisible():
            # Sync to the player before the bar appears so the user
            # doesn't see a half-second of default state (volume 100,
            # time 0:00, etc.).
            self._vc_refresh_state()
            self._video_controls.show()
            self._video_controls.raise_()

    def _vc_hide_bar(self) -> None:
        if self._video_controls.isVisible():
            self._video_controls.hide()

    def _client_has_media(self) -> bool:
        player = self._player_or_none()
        if player is None or not hasattr(player, "length_seconds"):
            return False
        return player.length_seconds() > 0

    def _vc_tick(self) -> None:
        """Cursor-polling tick — show/hide the bar based on activity."""
        if not self._client_has_media():
            if self._video_controls.isVisible():
                self._video_controls.hide()
            return

        now = time.monotonic()
        pos = QtGui.QCursor.pos()
        if pos != self._vc_last_cursor_pos:
            self._vc_last_cursor_pos = pos
            # Only count motion that's actually over the video or bar
            # as "user activity" — otherwise the bar stays visible
            # indefinitely whenever the user moves their mouse over
            # the sidebar or another window.
            if self._vc_cursor_over_video_or_bar():
                self._vc_last_motion_time = now
                self._vc_show_bar()
                return
            # Motion elsewhere — fall through to the hide-check.

        if not self._video_controls.isVisible():
            return

        # Keep visible while cursor sits over the bar itself.
        bar_rect = QtCore.QRect(
            self._video_controls.mapToGlobal(QtCore.QPoint(0, 0)),
            self._video_controls.size(),
        )
        if bar_rect.contains(pos):
            self._vc_last_motion_time = now
            return

        # Keep visible while paused — VLC does the same.
        player = self._player_or_none()
        if player is not None and hasattr(player, "is_paused"):
            try:
                if player.is_paused():
                    return
            except Exception:
                pass

        if now - self._vc_last_motion_time > self.VC_HIDE_AFTER_S:
            self._vc_hide_bar()

    def _vc_refresh_state(self) -> None:
        player = self._player_or_none()
        if player is None:
            return
        # No media yet → don't pump zeros into the bar.
        if not self._client_has_media():
            return
        try:
            length_s = player.length_seconds()
            position_s = player.position_seconds()
            is_paused = player.is_paused()
            is_ended = player.is_ended() if hasattr(player, "is_ended") else False
            volume = player.get_volume()
            is_muted = player.is_muted()
        except Exception:
            return
        self._video_controls.update_state(
            # State.Ended counts as "not playing" so the bar shows ▶,
            # not ⏸, when the file finished.
            is_playing=not (is_paused or is_ended),
            position_s=position_s,
            duration_s=length_s,
            volume=int(volume),
            is_muted=bool(is_muted),
            is_fullscreen=self._is_fullscreen,
        )

    # --- Fullscreen + chat overlay ---------------------------------------

    OVERLAY_EDGE_PX = 40        # mouse-X within this many px of right edge → reveal
    OVERLAY_WIDTH_FRACTION = 0.28  # overlay covers this much of the screen width

    def _fs_enter(self) -> None:
        if self._is_fullscreen:
            return
        self._is_fullscreen = True

        # Remember whether the chat was visible so we can restore it on
        # exit; the toggle strip is also hidden while fullscreen.
        self._saved_chat_visible = self._chat_visible
        self._chat_toggle.setVisible(False)
        self.menuBar().setVisible(False)
        self.statusBar().setVisible(False)

        # Build the overlay frame parented to MainWindow so it floats above
        # the video area without becoming a separate window.
        self._overlay = QtWidgets.QFrame(self)
        self._overlay.setObjectName("fsOverlay")
        self._overlay.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._overlay.setStyleSheet(
            "QFrame#fsOverlay { background: rgba(20, 20, 20, 217); "
            "border-left: 1px solid #444; }"
        )
        layout = QtWidgets.QVBoxLayout(self._overlay)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Reparent the chat sidebar out of the main layout into the overlay;
        # video now naturally fills the freed space (only stretching item).
        self._main_layout.removeWidget(self._right_container)
        self._right_container.setParent(self._overlay)
        self._right_container.setVisible(True)
        layout.addWidget(self._right_container)
        self._overlay.hide()

        self.showFullScreen()
        self._fs_reposition_overlay()

        # Track mouse globally so we can reveal on edge approach even when
        # the cursor is over the video widget.
        QtWidgets.QApplication.instance().installEventFilter(self._mouse_filter)

        autohide = 3000
        if self._client is not None:
            cfg = getattr(self._client, "_config", {}) or {}
            try:
                autohide = int(cfg.get("fullscreenAutohideMs") or 3000)
            except (TypeError, ValueError):
                autohide = 3000
        self._autohide_timer.setInterval(max(500, autohide))

        # Reflect the new fullscreen state on the bar's button icon
        # without waiting for the 500 ms refresh tick.
        self._vc_refresh_state()

    def _fs_exit(self) -> None:
        if not self._is_fullscreen:
            return
        self._is_fullscreen = False
        self._autohide_timer.stop()
        QtWidgets.QApplication.instance().removeEventFilter(self._mouse_filter)

        # Reparent the chat sidebar back into the main HBox at index 2
        # (after video + toggle strip) and restore the pre-fullscreen
        # show/hide state.
        overlay = self._overlay
        self._overlay = None
        self._right_container.setParent(None)
        self._main_layout.insertWidget(2, self._right_container, 1)
        self._chat_toggle.setVisible(True)
        self._chat_visible = self._saved_chat_visible
        self._right_container.setVisible(self._chat_visible)
        self._chat_toggle.setText("❯" if self._chat_visible else "❮")
        self._chat_toggle.setToolTip(
            "Hide chat" if self._chat_visible else "Show chat"
        )

        self.menuBar().setVisible(True)
        self.statusBar().setVisible(True)
        self.showNormal()

        if overlay is not None:
            overlay.setParent(None)
            overlay.deleteLater()

        self._vc_refresh_state()

    def _fs_reposition_overlay(self) -> None:
        if self._overlay is None:
            return
        width = max(280, int(self.width() * self.OVERLAY_WIDTH_FRACTION))
        self._overlay.setGeometry(self.width() - width, 0, width, self.height())

    def _fs_reveal_overlay(self) -> None:
        if self._overlay is None:
            return
        if not self._overlay.isVisible():
            self._fs_reposition_overlay()
            self._overlay.show()
            self._overlay.raise_()
            # Keep the video bar above the chat overlay where they
            # overlap (bottom-right). Otherwise the chat panel covers
            # the rightmost controls (mute, volume, fullscreen).
            if self._video_controls.isVisible():
                self._video_controls.raise_()
        self._autohide_timer.start()

    def _fs_hide_overlay(self) -> None:
        if self._overlay is None:
            return
        # Don't hide while user is actively typing in chat.
        focus = QtWidgets.QApplication.focusWidget()
        if focus is not None and focus is not self.videoWidget:
            parent = focus
            while parent is not None:
                if parent is self._overlay:
                    self._autohide_timer.start()
                    return
                parent = parent.parentWidget()
        self._overlay.hide()

    def _fs_on_global_mouse_move(self, global_pos: QtCore.QPoint) -> None:
        if not self._is_fullscreen:
            return
        # Map to MainWindow coordinates
        local = self.mapFromGlobal(global_pos)
        near_right = local.x() >= self.width() - self.OVERLAY_EDGE_PX
        if near_right and 0 <= local.y() < self.height():
            self._fs_reveal_overlay()
        elif self._overlay is not None and self._overlay.isVisible():
            self._autohide_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._is_fullscreen:
            self._fs_reposition_overlay()
        self._vc_reposition_if_visible()

    def _toggle_chat_panel(self) -> None:
        if self._is_fullscreen:
            return  # fullscreen has its own auto-hide overlay
        self._chat_visible = not self._chat_visible
        self._right_container.setVisible(self._chat_visible)
        self._chat_toggle.setText("❯" if self._chat_visible else "❮")
        self._chat_toggle.setToolTip(
            "Hide chat" if self._chat_visible else "Show chat"
        )
        # Force the HBox to recompute slot sizes immediately — some Qt
        # styles defer relayout until the next event tick, which leaves a
        # frame where the chat is invisible but its space hasn't been
        # given back to the video pane yet.
        self._main_layout.invalidate()
        self._main_layout.activate()
        # libvlc's X surface only redraws on its own frame tick, so the
        # area the video just grew into would otherwise show stale chat
        # pixels until the next frame. Ask the video widget to paint
        # itself black once — libvlc renders over it shortly after.
        self.videoWidget.request_black_repaint()
        # Video pane resized — keep the auto-hide control bar aligned.
        self._vc_reposition_if_visible()

    def _vc_reposition_if_visible(self) -> None:
        if getattr(self, "_video_controls", None) is None:
            return
        if not self._video_controls.isVisible():
            return
        if not self._vc_position_bar():
            # Video pane shrank below the minimum — hide instead of
            # leaving the bar at a stale (overflowing) geometry.
            self._video_controls.hide()

    def _brief_status(self, text: str, duration_ms: int = 1500) -> None:
        """Quick non-modal feedback in the status bar."""
        self.statusBar().showMessage(text, duration_ms)

    def _open_settings(self) -> None:
        if self._client is None:
            return
        config = getattr(self._client, "_config", {}) or {}
        dialog = SettingsDialog(
            self,
            config=config,
            fileinfo=self._fileinfo,
            get_player=lambda: getattr(self._client, "_player", None),
            on_persist=self._persist_setting,
        )
        self._settings_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._settings_dialog = None

    def _on_fileinfo(self, fileinfo: dict) -> None:
        self._fileinfo = fileinfo
        # If a settings dialog is open right now, refresh its dropdowns.
        if self._settings_dialog is not None:
            try:
                self._settings_dialog.set_fileinfo(fileinfo)
            except Exception:
                pass

    def _persist_setting(self, key: str, value) -> None:
        """Forward a settings-dialog change to the on-disk INI and the
        live config dict the client reads from."""
        if self._client is not None:
            cfg = getattr(self._client, "_config", None)
            if cfg is not None:
                cfg[key] = value
        try:
            from syncplay.ui.ConfigurationGetter import ConfigurationGetter
            ConfigurationGetter().setConfigOption(key, value)
        except Exception as exc:
            if getattr(constants, "DEBUG_MODE", False):
                print(f"[settings] persist {key} failed: {exc}",
                      file=sys.stderr, flush=True)

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
