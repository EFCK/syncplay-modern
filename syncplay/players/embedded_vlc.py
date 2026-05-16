"""Embedded libvlc player adapter.

Threading hazard: libvlc event callbacks fire on libvlc-internal worker
threads. Anything those callbacks touch in the SyncplayClient or in any Qt
widget must be marshaled back to the reactor/Qt main thread via
`reactor.callFromThread(...)`. The position-polling tick is driven by QTimer
on the Qt main thread, which is also the Twisted reactor thread under
qt5reactor, so it does not need marshaling.

Phase 1 stub: raises if instantiated. Real implementation lands in Phase 3.
"""

from __future__ import annotations

from syncplay.players.basePlayer import BasePlayer


class EmbeddedVlcPlayer(BasePlayer):
    speedSupported = True
    chatOSDSupported = False
    alertOSDSupported = False
    osdMessageSeparator = "\n"

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "EmbeddedVlcPlayer is not yet implemented (Phase 3)."
        )

    # --- Discovery helpers used by PlayerFactory --------------------------

    @staticmethod
    def getDefaultPlayerPathsList():
        # libvlc is loaded in-process via python-vlc; no external path.
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
        raise NotImplementedError("EmbeddedVlcPlayer.run not yet implemented (Phase 3).")
