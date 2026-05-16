"""Qt-free router translating SyncplayClient's UiManager calls into typed events.

SyncplayClient (`client.py:1680-1788`) calls roughly twenty methods on the UI
object. We satisfy that contract here and republish each call as one of the
dataclasses in `events.py`. Panels subscribe via Qt signals exposed in the
PanelBridge wrapper (see `mainWindow.py`).

This module deliberately has no Qt imports so the classification logic can be
unit-tested without QApplication.
"""

from __future__ import annotations

import time
from typing import Callable, List

from syncplay import constants
from syncplay.ui.modern.events import (
    ChatMessage,
    ConnectionState,
    ConnectionStateKind,
    ErrorEvent,
    ErrorSeverity,
    SyncEvent,
    SyncEventKind,
)


Listener = Callable[[object], None]


class MessageRouter:
    def __init__(self) -> None:
        self._listeners: List[Listener] = []
        self._client = None
        self._ui_mode = constants.GRAPHICAL_UI_MODE if hasattr(
            constants, "GRAPHICAL_UI_MODE"
        ) else "GUI"

    # --- Subscription -----------------------------------------------------

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self, event: object) -> None:
        for listener in self._listeners:
            listener(event)

    # --- UiManager surface ------------------------------------------------

    def addClient(self, client) -> None:
        self._client = client

    def showChatMessage(self, username: str, userMessage: str) -> None:
        self._emit(
            ChatMessage(
                user=username,
                text=userMessage,
                is_self=False,
                timestamp=time.time(),
            )
        )

    def showMessage(self, message: str, noTimestamp: bool = False, isMotd: bool = False) -> None:
        # Sync events and informational messages from the client. We do not
        # try to parse them — the client formats localized strings. We render
        # them as a "generic" SyncEvent so the chat panel can display a single
        # gray italic line.
        self._emit(
            SyncEvent(
                kind=SyncEventKind.GENERIC,
                detail=message,
                timestamp=time.time(),
            )
        )

    def showOSDMessage(
        self,
        message: str,
        duration=getattr(constants, "OSD_DURATION", 3) * 1000,
        OSDType=None,
        mood=None,
    ) -> None:
        # By design we suppress OSD overlays on the video. The chat panel
        # already surfaces the same information.
        return

    def showErrorMessage(self, message: str, criticalerror: bool = False) -> None:
        severity = ErrorSeverity.CRITICAL if criticalerror else ErrorSeverity.ERROR
        self._emit(
            ErrorEvent(
                severity=severity,
                text=message,
                category="client",
                timestamp=time.time(),
            )
        )
        if "disconnection" in message.lower() or "disconnect" in message.lower():
            self._emit(ConnectionState(state=ConnectionStateKind.DISCONNECTED, detail=message))

    def showDebugMessage(self, message: str) -> None:
        return

    def showUserList(self, currentUser, rooms) -> None:
        return

    def updateRoomName(self, room: str = "") -> None:
        return

    def updateAutoPlayState(self, newState) -> None:
        return

    def addRoomToList(self, *args, **kwargs) -> None:
        return

    def userListChange(self) -> None:
        return

    def markEndOfUserlist(self) -> None:
        return

    def promptFor(self, prompt: str = ">", message: str = "") -> str:
        return ""

    def setSSLMode(self, sslMode, sslInfo: str = "") -> None:
        return

    def setControllerStatus(self, username: str, isController: bool) -> None:
        return

    def setFeatures(self, featureList) -> None:
        return

    def addFileToPlaylist(self, item) -> None:
        return

    def setPlaylist(self, newPlaylist, newIndexFilename=None) -> None:
        return

    def setPlaylistIndexFilename(self, filename) -> None:
        return

    def fileSwitchFoundFiles(self) -> None:
        return

    def executeCommand(self, command: str) -> None:
        return

    def drop(self) -> None:
        return

    def getUIMode(self) -> str:
        return self._ui_mode
