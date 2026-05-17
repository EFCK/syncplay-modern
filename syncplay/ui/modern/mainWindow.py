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
    PlaylistAppended,
    PlaylistChanged,
    PlaylistIndexChanged,
    RoomSnapshot,
    SyncEvent,
    UserFileChanged,
    UserJoined,
    UserLeft,
    UserReadyChanged,
)
from syncplay.ui.modern.messageRouter import MessageRouter
from syncplay.ui.modern.queuePanel import QueuePanel
from syncplay.ui.modern.roomPanel import RoomPanel
from syncplay.ui.modern.roomState import RoomState
from syncplay.ui.modern.settingsPanel import PlaybackDialog, SettingsDialog
from syncplay.ui.modern import theme as theme_mod
from syncplay.ui.modern.sidebarTabs import SidebarTabs
from syncplay.ui.modern.toast import Toast
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

        # Apply the saved theme as early as possible so freshly-created
        # widgets pick it up on first paint instead of flashing the
        # default palette. The real saved value lands later in
        # addClient() once the SyncplayClient instance is attached;
        # until then we use the module default.
        self._theme: str = theme_mod.DEFAULT
        self._apply_theme(self._theme)

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
        self._playback_dialog: Optional[PlaybackDialog] = None

        # Fullscreen state
        self._is_fullscreen = False
        self._overlay: Optional[QtWidgets.QFrame] = None
        self._saved_chat_visible: bool = True
        self._mouse_filter = _MouseEdgeFilter(self)
        self._autohide_timer = QtCore.QTimer(self)
        self._autohide_timer.setSingleShot(True)
        self._autohide_timer.timeout.connect(self._fs_hide_overlay)

        # --- Right: sidebar tabs (Room / Chat / Errors). The old
        # `UserStrip` row above the tabs was redundant with the Room
        # tab's user table and the status-bar room label, and rendered
        # as a black gap once the wrapper went black-filled, so it's
        # been removed.
        self._chat_panel = ChatPanel()
        self._room_panel = RoomPanel()
        self._room_panel.readyToggleRequested.connect(self._on_ready_toggle)
        self._errors_panel = ErrorsPanel()
        self._queue_panel = QueuePanel()
        self._queue_panel.addFilesRequested.connect(self._on_queue_add_files)
        self._queue_panel.indexChangeRequested.connect(self._on_queue_play)
        self._queue_panel.removeAtIndexRequested.connect(self._on_queue_remove)
        self._tabs = SidebarTabs(
            self._room_panel, self._chat_panel, self._queue_panel, self._errors_panel
        )

        self._right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(self._right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
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
        # Fixed-width strip that fills the full row height so the entire
        # gutter between video and chat is clickable, not just a small
        # square in the middle.
        self._chat_toggle.setFixedWidth(22)
        self._chat_toggle.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding
        )
        self._chat_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._chat_toggle.setToolTip("Hide chat")
        self._chat_toggle.setFocusPolicy(QtCore.Qt.NoFocus)
        # Transparent background; only the chevron glyph paints. Stylesheet
        # is rebuilt by `_restyle_chat_toggle()` whenever the theme flips
        # so the chevron stays readable on both light and dark wrapper bgs.
        self._restyle_chat_toggle()
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
        # No alignment → button fills its 22-px-wide column from top to
        # bottom, so the whole strip between video and chat is a
        # clickable target.
        self._main_layout.addWidget(self._chat_toggle, 0)
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

        # Status bar removed — the Room tab already shows the current
        # room, and the connection state is reflected via chat / errors
        # tabs. Hidden rather than left null so any upstream code that
        # still calls `self.statusBar()` doesn't crash.
        self.statusBar().hide()

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

        # --- Toast (in-video corner notifications)
        # Created last so it floats above VideoControls. embedded_vlc
        # picks it up via `getattr(window, "_toast", None)`.
        self._toast = Toast(self)
        self._toast_reposition()

        self.show()

    # ----------------------------------------------------------------------
    # UI contract — SyncplayClient.UiManager calls these directly.
    # We delegate to MessageRouter, which classifies and emits typed events.
    # ----------------------------------------------------------------------

    def addClient(self, client) -> None:
        self._client = client
        self._router.addClient(client)
        self._maybe_schedule_autochat()
        # Pull the persisted theme out of the live config now that we
        # have a client; re-apply only if it differs from the default
        # used at startup.
        cfg = getattr(client, "_config", None) or {}
        saved = theme_mod.normalize(cfg.get("theme") or theme_mod.DEFAULT)
        if saved != self._theme:
            self._theme = saved
            self._apply_theme(self._theme)
            text, tip = theme_mod.button_label_for(self._theme)
            self._theme_btn.setText(text)
            self._theme_btn.setToolTip(tip)

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
        # The Room tab consumes the same data via RoomState — feed it
        # the diffed/typed events plus a fresh RoomSnapshot.
        try:
            self._room_state.update_from_rooms(currentUser, rooms)
        except Exception:
            if getattr(constants, "DEBUG_MODE", False):
                import traceback
                traceback.print_exc()

    def updateRoomName(self, room=""):
        # The Room tab's label is the source of truth for current room
        # name; the bottom status bar that used to mirror it has been
        # removed.
        return

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
        # Was used to set a "Connection: TLS" tooltip on the status-bar
        # connection dot; the status bar has been removed.
        return

    def setControllerStatus(self, username, isController):
        return

    def setFeatures(self, featureList):
        return

    def addFileToPlaylist(self, item):
        self._router.addFileToPlaylist(item)

    def setPlaylist(self, newPlaylist, newIndexFilename=None):
        self._router.setPlaylist(newPlaylist, newIndexFilename)

    def setPlaylistIndexFilename(self, filename):
        self._router.setPlaylistIndexFilename(filename)

    def fileSwitchFoundFiles(self):
        return

    def executeCommand(self, command):
        return

    def drop(self):
        return

    def getUIMode(self):
        return "GUI"

    def closeEvent(self, event):
        """Tear down libvlc and the Twisted reactor on window close.

        Without this the default Qt close hides the window but
        SyncplayClient.stop() never runs — libvlc worker threads keep
        the Python process alive and audio keeps playing. Particularly
        bad on Windows where the user has no terminal to Ctrl+C from
        and has to kill the process via Task Manager.

        Hides the top-level toast first so quitOnLastWindowClosed isn't
        held off by it, calls _client.stop() (the canonical Syncplay
        teardown: destroyProtocol → player.drop → reactor.stop), then
        schedules a QApplication.quit fallback in case qt5reactor's
        reactor-to-Qt propagation doesn't fire on Windows.
        """
        try:
            toast = getattr(self, "_toast", None)
            if toast is not None:
                toast.hide()
        except Exception:
            pass
        try:
            if self._client is not None and hasattr(self._client, "stop"):
                self._client.stop()
        except Exception:
            pass
        QtCore.QTimer.singleShot(300, QtWidgets.QApplication.quit)
        super().closeEvent(event)

    # ----------------------------------------------------------------------
    # Internals
    # ----------------------------------------------------------------------

    def _on_router_event(self, event) -> None:
        if isinstance(event, ChatMessage):
            self._chat_panel.render_chat(event)
            self._maybe_toast_chat(event)
        elif isinstance(event, SyncEvent):
            self._chat_panel.render_sync(event)
        elif isinstance(event, ErrorEvent):
            self._errors_panel.render_error(event)
            self._tabs.note_error()
            self._chat_panel.render_error_notice()
        elif isinstance(event, ConnectionState):
            self._on_connection_state(event)
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
        elif isinstance(event, (PlaylistChanged, PlaylistAppended, PlaylistIndexChanged)):
            self._queue_panel.on_playlist_event(event)

    def _on_connection_state(self, event: ConnectionState) -> None:
        # Was used to drive the status-bar connection dot's colour and
        # tooltip; with the status bar removed there's no surface to
        # show it. Connect/disconnect/reconnect lines still show up in
        # the Errors tab (and the chat-tab pointer), which is enough.
        return

    def _on_chat_submit(self, text: str) -> None:
        if self._client is None or not text:
            return
        if hasattr(self._client, "sendChat"):
            self._client.sendChat(text)

    def _playlist_or_none(self):
        client = self._client
        if client is None:
            return None
        return getattr(client, "playlist", None)

    def _on_queue_add_files(self, paths: list) -> None:
        """Queue user-picked files into the room's shared playlist.

        Two-step per file: openFile() to register the absolute path
        with the client (so fileSwitch.findFilepath() can later resolve
        the basename back to a real path), then playlist.addToPlaylist()
        with the BASENAME — upstream's playlist convention is
        basename-only so the same playlist works across users with the
        file at different paths. Without the openFile step, the
        immediate `switchToNewPlaylistIndex` triggered inside
        `addToPlaylist` fails with "Could not find file ... in media
        directories for playlist switch" because the file isn't yet
        known to fileSwitch.
        """
        if self._client is None:
            return
        playlist = self._playlist_or_none()
        if playlist is None:
            return
        import os
        for path in paths:
            if not path:
                continue
            basename = os.path.basename(path)
            try:
                # Register the path. openFile also starts playback —
                # acceptable here since the user just asked to queue
                # something, and the just-queued file becomes the new
                # current item anyway.
                self._client.openFile(path, fromUser=True)
            except TypeError:
                # Older client signature (no fromUser kw).
                try:
                    self._client.openFile(path)
                except Exception:
                    if getattr(constants, "DEBUG_MODE", False):
                        import traceback
                        traceback.print_exc()
                    continue
            except Exception:
                if getattr(constants, "DEBUG_MODE", False):
                    import traceback
                    traceback.print_exc()
                continue
            try:
                playlist.addToPlaylist(basename)
            except Exception:
                if getattr(constants, "DEBUG_MODE", False):
                    import traceback
                    traceback.print_exc()

    def _on_queue_play(self, filename: str) -> None:
        playlist = self._playlist_or_none()
        if playlist is None or not filename:
            return
        try:
            playlist.changeToPlaylistIndexFromFilename(filename)
        except Exception:
            if getattr(constants, "DEBUG_MODE", False):
                import traceback
                traceback.print_exc()

    def _on_queue_remove(self, index: int) -> None:
        playlist = self._playlist_or_none()
        if playlist is None or index < 0:
            return
        try:
            playlist.deleteAtIndex(index)
        except Exception:
            if getattr(constants, "DEBUG_MODE", False):
                import traceback
                traceback.print_exc()

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
        # Route through self.close() so closeEvent runs the libvlc /
        # reactor teardown — QApplication.quit() alone leaves audio
        # threads playing.
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        # Playback gets its own top-level entry next to File — the audio
        # / subtitle / sub-delay controls are the ones users reach for
        # most, so they're one click away rather than buried in Settings.
        playback_act = QtGui.QAction("&Playback…", self)
        playback_act.triggered.connect(self._open_playback)
        bar.addAction(playback_act)

        # Settings (everything except live playback) — no sibling menu
        # actions, so use a direct top-level action that opens the
        # tabbed dialog on click.
        settings_act = QtGui.QAction("&Settings…", self)
        settings_act.setShortcut("Ctrl+,")
        settings_act.triggered.connect(self._open_settings)
        bar.addAction(settings_act)

        # Theme toggle button in the top-right corner of the menu bar.
        # `setCornerWidget(..., TopRightCorner)` is Qt's official slot for
        # this — no extra layout gymnastics needed.
        text, tip = theme_mod.button_label_for(self._theme)
        self._theme_btn = QtWidgets.QToolButton(self)
        self._theme_btn.setText(text)
        self._theme_btn.setToolTip(tip)
        self._theme_btn.setAutoRaise(True)
        self._theme_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._theme_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self._theme_btn.setStyleSheet(
            "QToolButton { padding: 2px 10px; font-size: 14px; border: none; }"
            "QToolButton:hover { background: rgba(127,127,127,40); border-radius: 3px; }"
        )
        self._theme_btn.clicked.connect(self._toggle_theme)
        bar.setCornerWidget(self._theme_btn, QtCore.Qt.TopRightCorner)

    def _apply_theme(self, theme: str) -> None:
        """Push the corresponding stylesheet onto the QApplication and
        propagate the theme to per-component panels that maintain their
        own theme-aware colour palettes (chat / errors / room logs,
        toggle button glyph).
        """
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme_mod.stylesheet_for(theme))
        # Component-level theme propagation. The QApplication-wide
        # stylesheet covers generic Qt widgets, but anything that emits
        # custom HTML or sets per-widget stylesheets has to be told
        # explicitly. These attribute checks tolerate this method being
        # called from `__init__` before all widgets exist.
        for panel in (
            getattr(self, "_chat_panel", None),
            getattr(self, "_errors_panel", None),
            getattr(self, "_room_panel", None),
        ):
            if panel is not None and hasattr(panel, "apply_theme"):
                try:
                    panel.apply_theme(theme)
                except Exception:
                    pass
        if getattr(self, "_chat_toggle", None) is not None:
            self._restyle_chat_toggle()

    def _restyle_chat_toggle(self) -> None:
        """Recolour the chat-show/hide chevron for the current theme.

        The toggle has a transparent background, so the wrapper widget's
        themed bg shows through; the chevron foreground colour has to
        flip to keep contrast in both modes.
        """
        p = theme_mod.palette(self._theme)
        # Build with %-formatting to dodge the double-brace `{{` / `}}`
        # escape trap that bites when mixing f-strings and plain literals
        # in a Qt stylesheet (Qt then warns "Could not parse stylesheet").
        qss = (
            "QToolButton { background: transparent; color: %(fg)s; "
            "border: none; font-size: 14px; font-weight: bold; padding: 0; }"
            "QToolButton:hover { background: %(hbg)s; color: %(hfg)s; }"
            "QToolButton:pressed { background: %(pbg)s; }"
        ) % {
            "fg": p["chat-toggle-fg"],
            "hbg": p["chat-toggle-hover-bg"],
            "hfg": p["chat-toggle-hover-fg"],
            "pbg": p["chat-toggle-pressed-bg"],
        }
        self._chat_toggle.setStyleSheet(qss)

    def _toggle_theme(self) -> None:
        self._theme = theme_mod.toggled(self._theme)
        self._apply_theme(self._theme)
        text, tip = theme_mod.button_label_for(self._theme)
        self._theme_btn.setText(text)
        self._theme_btn.setToolTip(tip)
        # Persist through the same path the settings dialog uses, so the
        # value lands in the INI under [gui] alongside every other UI
        # preference. No-op when no client is attached yet (early UI).
        try:
            self._persist_setting("theme", self._theme)
        except Exception:
            pass

    def _install_shortcuts(self) -> None:
        """VLC-style keyboard shortcuts.

        Window-scoped (not widget-scoped) so the user doesn't have to
        click the video first — on Windows the native HWND child can
        swallow mouse-down events before Qt sees them, and the focus
        never moves to the video widget, leaving widget-scoped
        shortcuts dead. Each handler is wrapped in a focus-guard so
        typing in chat input still works: while a text input has
        focus, every shortcut except Escape is suppressed and the key
        flows through to the input. Escape is always live so the user
        can exit fullscreen from anywhere.
        """
        scope = QtCore.Qt.WindowShortcut

        def make(seq, handler, *, always: bool = False):
            def guarded():
                if always or not self._shortcut_blocked():
                    handler()
            sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self)
            sc.setContext(scope)
            sc.activated.connect(guarded)
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
        make("Escape", self._kb_exit_fullscreen, always=True)

    def _shortcut_blocked(self) -> bool:
        """True if a text input has focus — let the input handle the key."""
        w = QtWidgets.QApplication.focusWidget()
        if w is None:
            return False
        return isinstance(
            w,
            (
                QtWidgets.QLineEdit,
                QtWidgets.QTextEdit,
                QtWidgets.QPlainTextEdit,
                QtWidgets.QComboBox,
                QtWidgets.QSpinBox,
                QtWidgets.QDoubleSpinBox,
            ),
        )

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
    VC_BAR_MARGIN_H = 8        # left / right inset from the video edge
    VC_BAR_MARGIN_BOTTOM = 0   # flush with the video bottom edge
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
        width = video_rect.width() - 2 * self.VC_BAR_MARGIN_H
        if width < self.VC_MIN_BAR_WIDTH:
            return False
        x = win_top_left.x() + self.VC_BAR_MARGIN_H
        y = (
            win_top_left.y()
            + video_rect.height()
            - self.VC_BAR_HEIGHT
            - self.VC_BAR_MARGIN_BOTTOM
        )
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
            self._vc_hide_bar()
            return
        if not self._video_controls.isVisible():
            # Sync to the player before the bar appears so the user
            # doesn't see a half-second of default state (volume 100,
            # time 0:00, etc.).
            self._vc_refresh_state()
            self._video_controls.show()
            self._video_controls.raise_()

    def _vc_hide_bar(self) -> None:
        if not self._video_controls.isVisible():
            return
        # Capture where the bar sat (in videoWidget-local coords) before
        # hiding, so we can ask the video widget to repaint that region
        # with black. On Windows libvlc doesn't redraw the letterbox at
        # the bottom of the video, so the part of the bar that overlapped
        # the letterbox stays on screen otherwise.
        bar_top_left_global = self._video_controls.mapToGlobal(QtCore.QPoint(0, 0))
        bar_local_in_video = self.videoWidget.mapFromGlobal(bar_top_left_global)
        clear_rect = QtCore.QRect(bar_local_in_video, self._video_controls.size())
        self._video_controls.hide()
        self.videoWidget.request_black_repaint(clear_rect)

    def _client_has_media(self) -> bool:
        player = self._player_or_none()
        if player is None or not hasattr(player, "length_seconds"):
            return False
        return player.length_seconds() > 0

    def _vc_tick(self) -> None:
        """Cursor-polling tick — show/hide the bar based on activity."""
        if not self._client_has_media():
            self._vc_hide_bar()
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
    OVERLAY_WIDTH_FRACTION = 0.17  # overlay covers this much of the screen width
                                   # (slightly less than the windowed 20% so it
                                   # feels like a floating panel, not a slab).
    OVERLAY_TOP_INSET = 96         # px dropped from the top so the chat floats.
    OVERLAY_BOTTOM_INSET = 96      # px lifted off the bottom so the chat input
                                   # clears the auto-hide progress bar.

    def _fs_enter(self) -> None:
        if self._is_fullscreen:
            return
        self._is_fullscreen = True

        # Snapshot the chat scroll position before the reparent — Qt's
        # QTextBrowser resets its scrollbar to 0 when the widget is
        # removed from its parent layout, so we capture-and-restore.
        chat_scroll = self._chat_panel.scroll_state()

        # Remember whether the chat was visible so we can restore it on
        # exit; the toggle strip is also hidden while fullscreen.
        self._saved_chat_visible = self._chat_visible
        self._chat_toggle.setVisible(False)
        self.menuBar().setVisible(False)

        # In fullscreen only the Chat tab is useful — the Room/Errors
        # tabs add noise on top of the video. Hide the tab bar and
        # force Chat, then put everything back on exit.
        self._saved_tab_index = self._tabs.currentIndex()
        self._tabs.setCurrentIndex(SidebarTabs.CHAT_INDEX)
        self._tabs.tabBar().setVisible(False)

        # Build the overlay frame parented to MainWindow so it floats above
        # the video area. Keeping this as a regular child widget (no
        # `WA_TranslucentBackground`) means the look is the same on every
        # platform — true transparency over a libvlc native X window
        # needs a compositor and would only work on some setups, which
        # is intentionally deferred for now.
        self._overlay = QtWidgets.QFrame(self)
        self._overlay.setObjectName("fsOverlay")
        self._overlay.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._overlay.setStyleSheet(
            # Dark, opaque-ish wash with rounded corners so it reads as a
            # floating chat panel rather than a screen-edge slab.
            "QFrame#fsOverlay { background: rgb(22, 22, 22); "
            "border: 1px solid #444; border-radius: 8px; }"
            "QFrame#fsOverlay QTabWidget::pane { background: transparent; border: none; }"
            "QFrame#fsOverlay QWidget { background: transparent; color: #f0f0f0; }"
            "QFrame#fsOverlay QTextBrowser { background: transparent; "
            "color: #f5f5f5; border: none; padding: 4px; }"
            "QFrame#fsOverlay QLineEdit { background: #2a2a2a; "
            "color: #ffffff; border: 1px solid #555; "
            "border-radius: 4px; padding: 4px; }"
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
        self._toast_reposition()
        # Defer to next event tick so the QTextBrowser has been laid
        # out in its new parent; otherwise scrollbar.maximum() lags.
        QtCore.QTimer.singleShot(
            0, lambda: self._chat_panel.restore_scroll(chat_scroll)
        )

        # Track mouse globally so we can reveal on edge approach even when
        # the cursor is over the video widget.
        QtWidgets.QApplication.instance().installEventFilter(self._mouse_filter)

        autohide = 120
        if self._client is not None:
            cfg = getattr(self._client, "_config", {}) or {}
            try:
                autohide = int(cfg.get("fullscreenAutohideMs") or 120)
            except (TypeError, ValueError):
                autohide = 120
        # Floor at 40 ms (basically instant — but not zero, so a quick
        # mouse-out / mouse-in doesn't flash-flicker the overlay). Cap
        # at 5 s so a typo in the INI can't make the overlay stick.
        self._autohide_timer.setInterval(max(40, min(autohide, 5000)))

        # Reflect the new fullscreen state on the bar's button icon
        # without waiting for the 500 ms refresh tick.
        self._vc_refresh_state()

    def _fs_exit(self) -> None:
        if not self._is_fullscreen:
            return
        self._is_fullscreen = False
        self._autohide_timer.stop()
        QtWidgets.QApplication.instance().removeEventFilter(self._mouse_filter)

        # Snapshot the chat scroll position before reparenting — see
        # _fs_enter for why this is needed.
        chat_scroll = self._chat_panel.scroll_state()

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

        # Bring the tab bar back and restore whatever tab the user was on.
        self._tabs.tabBar().setVisible(True)
        try:
            self._tabs.setCurrentIndex(self._saved_tab_index)
        except Exception:
            pass

        self.menuBar().setVisible(True)
        self.showNormal()

        if overlay is not None:
            overlay.setParent(None)
            overlay.deleteLater()

        self._vc_refresh_state()
        # Defer the chat scroll restore — see _fs_enter for the same
        # pattern. Without it the chat resets to the top when leaving
        # fullscreen, hiding the most recent messages the user was
        # reading.
        QtCore.QTimer.singleShot(
            0, lambda: self._chat_panel.restore_scroll(chat_scroll)
        )

    def _fs_reposition_overlay(self) -> None:
        if self._overlay is None:
            return
        width = max(280, int(self.width() * self.OVERLAY_WIDTH_FRACTION))
        top = self.OVERLAY_TOP_INSET
        height = max(160, self.height() - top - self.OVERLAY_BOTTOM_INSET)
        self._overlay.setGeometry(self.width() - width, top, width, height)

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
        # Don't hide while the user is actively typing a message —
        # but "actively typing" means there's unsent text in the
        # input. Pressing Enter clears the input yet leaves focus on
        # the QLineEdit; treating focus alone as "still typing" would
        # keep the overlay pinned open forever after the first send.
        focus = QtWidgets.QApplication.focusWidget()
        if focus is not None and focus is not self.videoWidget:
            parent = focus
            while parent is not None:
                if parent is self._overlay:
                    if self._chat_panel.has_pending_input():
                        self._autohide_timer.start()
                        return
                    break
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
        self._toast_reposition()

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
        self._toast_reposition()

    def _vc_reposition_if_visible(self) -> None:
        if getattr(self, "_video_controls", None) is None:
            return
        if not self._video_controls.isVisible():
            return
        if not self._vc_position_bar():
            # Video pane shrank below the minimum — hide instead of
            # leaving the bar at a stale (overflowing) geometry.
            self._vc_hide_bar()

    def _brief_status(self, text: str, duration_ms: int = 1500) -> None:
        toast = getattr(self, "_toast", None)
        if toast is None:
            return
        # Reposition before showing so the top-level toast window appears
        # at the correct screen location on the first frame (no flash).
        self._toast_reposition()
        toast.show_message(text, duration=duration_ms)

    def _toast_reposition(self) -> None:
        toast = getattr(self, "_toast", None)
        if toast is None:
            return
        video_widget = self.videoWidget
        # Toast is a top-level window — pass screen coordinates.
        top_left = video_widget.mapToGlobal(QtCore.QPoint(0, 0))
        rect = QtCore.QRect(top_left, video_widget.size())
        toast.reposition(rect)

    def _maybe_toast_chat(self, event: ChatMessage) -> None:
        # Respect the chatOnVideoEnabled setting (default False, INI-persisted).
        # Suppress self-echoes — the user just typed the line, they don't
        # need a corner toast of their own message.
        if event.is_self:
            return
        cfg = getattr(self._client, "_config", None) if self._client else None
        if not cfg or not cfg.get("chatOnVideoEnabled"):
            return
        toast = getattr(self, "_toast", None)
        if toast is None:
            return
        self._toast_reposition()
        toast.show_message(f"{event.user}: {event.text}", duration=4000)

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

    def _open_playback(self) -> None:
        if self._client is None:
            return
        config = getattr(self._client, "_config", {}) or {}
        dialog = PlaybackDialog(
            self,
            config=config,
            fileinfo=self._fileinfo,
            get_player=lambda: getattr(self._client, "_player", None),
            on_persist=self._persist_setting,
        )
        self._playback_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._playback_dialog = None

    def _on_fileinfo(self, fileinfo: dict) -> None:
        self._fileinfo = fileinfo
        # If either dialog is open, refresh whichever owns track lists.
        for dlg in (self._playback_dialog, self._settings_dialog):
            if dlg is None:
                continue
            try:
                dlg.set_fileinfo(fileinfo)
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
