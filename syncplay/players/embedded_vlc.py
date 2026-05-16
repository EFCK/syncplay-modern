"""Embedded libvlc player adapter.

Phase 2: stub that satisfies SyncplayClient's BasePlayer contract end-to-end
without doing any actual playback. This lets two clients exchange chat and
sync events via the real protocol while we develop the UI separately.

Phase 3: replace the internals with python-vlc / libvlc draw-into-our-QWidget.
Threading note for Phase 3: libvlc event callbacks fire on libvlc-internal
worker threads. Anything those callbacks touch in the client or any Qt
widget must be marshaled back via `reactor.callFromThread(...)`. The
position-polling tick (driven by `client.scheduleAskPlayer`) runs on the Qt
main thread (also the Twisted reactor thread under qt5reactor), so it
itself does not need marshaling.
"""

from __future__ import annotations

from syncplay.players.basePlayer import BasePlayer


class EmbeddedVlcPlayer(BasePlayer):

    speedSupported = True
    chatOSDSupported = False
    alertOSDSupported = False
    osdMessageSeparator = "\n"

    def __init__(self, client) -> None:
        self._client = client
        self._paused = True
        self._position = 0.0
        self._speed = 1.0
        self._file: dict | None = None

    # --- Class / factory methods used by PlayerFactory --------------------

    @staticmethod
    def getDefaultPlayerPathsList():
        return ["__embedded_vlc__"]

    @staticmethod
    def isValidPlayerPath(path: str) -> bool:
        return path == "__embedded_vlc__"

    @staticmethod
    def getIconPath(path: str):
        return None

    @staticmethod
    def getExpandedPath(path: str) -> str:
        return path

    @staticmethod
    def getPlayerPathErrors(playerPath: str, filePath: str):
        return None

    @staticmethod
    def run(client, playerPath, filePath, args):
        player = EmbeddedVlcPlayer(client)
        if filePath:
            player.openFile(filePath)
        client.initPlayer(player)
        return player

    # --- BasePlayer surface called by SyncplayClient ----------------------

    def askForStatus(self) -> None:
        client = self._client
        if client is None:
            return
        client.updatePlayerStatus(self._paused, self._position)

    def setPaused(self, value: bool) -> None:
        self._paused = bool(value)

    def setPosition(self, value: float) -> None:
        self._position = float(value)

    def setSpeed(self, value: float) -> None:
        self._speed = float(value)

    def openFile(self, filePath: str, resetPosition: bool = False) -> None:
        self._file = {"name": filePath, "duration": 0.0, "path": filePath}
        if resetPosition:
            self._position = 0.0
        # Notify the client so it can broadcast the file change.
        client = self._client
        if client is not None and filePath:
            try:
                client.updateFile(filePath, 0.0, filePath)
            except Exception:
                pass

    def displayMessage(self, message, duration=None, OSDType=None, mood=None):
        return  # Stub — Phase 3 will surface via toast.py / our own corner overlay.

    def displayChatMessage(self, username: str, message: str) -> None:
        return  # chatOSDSupported=False, so client routes to ui only.

    def setFeatures(self, featureList) -> None:
        return

    def drop(self, dropErrorMessage=None) -> None:
        self._client = None
