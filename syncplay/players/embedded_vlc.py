"""Embedded libvlc player adapter.

Wraps `vlc.MediaPlayer` and drives it from inside our Qt window.
SyncplayClient calls into the BasePlayer surface (`askForStatus`,
`setPaused`, `setPosition`, `setSpeed`, `openFile`, `drop`); we delegate
those to libvlc and call `client.updatePlayerStatus(...)` back via the
client's existing `LoopingCall`-driven `askPlayer` loop.

THREADING — read before changing:

Under `qt5reactor` the Twisted reactor runs on the Qt main thread, so
everything from `client.askPlayer` → `player.askForStatus()` arrives on
the main thread. We can talk to libvlc directly from there.

libvlc's *event callbacks* (`MediaPlayerEndReached`, `MediaParsedChanged`,
etc.) fire on libvlc-internal worker threads. Anything in those callbacks
that touches the client or any Qt widget MUST be marshaled back via
`reactor.callFromThread(...)`.

MainWindow drops a reference to its `VideoWidget` into this module before
the reactor starts (`set_video_widget`); the player picks it up when
instantiated.
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from syncplay.players.basePlayer import BasePlayer


_pending_video_widget = None
_pending_fileinfo_sink: Optional[Callable[[dict], None]] = None
_vlc_instance = None


def set_video_widget(widget) -> None:
    """Register the VideoWidget the next player instance will attach to."""
    global _pending_video_widget
    _pending_video_widget = widget


def set_fileinfo_sink(sink: Optional[Callable[[dict], None]]) -> None:
    """Callback invoked when a media file finishes parsing.

    Receives a dict with keys ``duration`` (seconds, float), ``audio_tracks``
    and ``subtitle_tracks`` (lists of ``{id, label}``). Used by the Phase 4
    settings panel to populate track dropdowns.
    """
    global _pending_fileinfo_sink
    _pending_fileinfo_sink = sink


def _get_instance():
    """libvlc.Instance is process-wide and expensive — cache it."""
    global _vlc_instance
    if _vlc_instance is None:
        import vlc
        _vlc_instance = vlc.Instance([
            "--no-xlib",            # safer alongside Qt's X11 access
            "--quiet",
            "--no-video-title-show",
            "--no-osd",             # we render our own toasts
        ])
    return _vlc_instance


def _label(raw) -> str:
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return raw.decode("latin-1", errors="replace")
    return str(raw) if raw is not None else ""


class EmbeddedVlcPlayer(BasePlayer):

    speedSupported = True
    chatOSDSupported = False
    alertOSDSupported = False
    osdMessageSeparator = "\n"

    def __init__(self, client) -> None:
        import vlc
        self._client = client
        self._vlc = vlc
        instance = _get_instance()
        self._player = instance.media_player_new()
        self._video_widget = _pending_video_widget
        if self._video_widget is not None:
            self._video_widget.attach_player(self._player)
            self._video_widget.clear_placeholder()

        self._current_media = None
        self._opened_path: Optional[str] = None
        self._opened_duration: float = 0.0

        em = self._player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end_reached)
        em.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)

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

    # --- BasePlayer surface ----------------------------------------------

    def askForStatus(self) -> None:
        client = self._client
        if client is None:
            return
        time_ms = self._player.get_time()
        position = max(0.0, (time_ms or 0) / 1000.0)
        state = self._player.get_state()
        # We treat anything that isn't actively playing as paused so the
        # sync state machine doesn't try to advance during buffering.
        active = state == self._vlc.State.Playing
        client.updatePlayerStatus(not active, position)

    def setPaused(self, value: bool) -> None:
        if value:
            self._player.set_pause(1)
            return
        state = self._player.get_state()
        if state in (self._vlc.State.Stopped, self._vlc.State.Ended,
                     self._vlc.State.NothingSpecial):
            self._player.play()
        else:
            self._player.set_pause(0)

    def setPosition(self, value: float) -> None:
        self._player.set_time(int(max(0.0, value) * 1000))

    def setSpeed(self, value: float) -> None:
        self._player.set_rate(float(value))

    def openFile(self, filePath: str, resetPosition: bool = False) -> None:
        instance = _get_instance()
        media = instance.media_new(filePath)
        # Parse asynchronously; we listen for MediaParsedChanged to learn
        # duration and audio/subtitle tracks.
        try:
            media.parse_with_options(0, -1)  # MediaParseFlag.local, default timeout
        except Exception:
            pass

        em = media.event_manager()
        em.event_attach(self._vlc.EventType.MediaParsedChanged, self._on_parsed)

        self._current_media = media
        self._opened_path = filePath
        self._opened_duration = 0.0

        self._player.set_media(media)
        if self._video_widget is not None:
            self._video_widget.attach_player(self._player)
            self._video_widget.clear_placeholder()

        # Begin playback so the demuxer engages and the renderer attaches.
        # Sync state machine will pause us almost immediately if appropriate.
        self._player.play()
        if resetPosition:
            self._player.set_time(0)

        client = self._client
        if client is not None:
            try:
                client.updateFile(filePath, 0.0, filePath)
            except Exception:
                pass

    def displayMessage(self, message, duration=None, OSDType=None, mood=None):
        widget = self._video_widget
        if widget is None:
            return
        window = widget.window()
        toast = getattr(window, "_toast", None)
        if toast is not None and hasattr(toast, "show_message"):
            toast.show_message(str(message), duration=(duration or 2000))

    def displayChatMessage(self, username: str, message: str) -> None:
        return  # chatOSDSupported=False — client never calls this.

    def setFeatures(self, featureList) -> None:
        return

    def drop(self, dropErrorMessage=None) -> None:
        try:
            self._player.stop()
        except Exception:
            pass
        try:
            self._player.release()
        except Exception:
            pass
        self._client = None

    # --- libvlc event callbacks (fire on libvlc worker threads) ----------

    def _on_parsed(self, event) -> None:
        from twisted.internet import reactor

        def fire():
            media = self._current_media
            if media is None:
                return
            try:
                duration = max(0.0, (media.get_duration() or 0) / 1000.0)
            except Exception:
                duration = 0.0
            self._opened_duration = duration

            audio_tracks = [
                {"id": tid, "label": _label(label)}
                for tid, label in (self._player.audio_get_track_description() or [])
            ]
            subtitle_tracks = [
                {"id": tid, "label": _label(label)}
                for tid, label in (self._player.video_get_spu_description() or [])
            ]

            sink = _pending_fileinfo_sink
            if sink is not None:
                try:
                    sink({
                        "duration": duration,
                        "audio_tracks": audio_tracks,
                        "subtitle_tracks": subtitle_tracks,
                    })
                except Exception:
                    pass

            client = self._client
            if client is not None and self._opened_path and duration > 0:
                try:
                    client.updateFile(self._opened_path, duration, self._opened_path)
                except Exception:
                    pass

        try:
            reactor.callFromThread(fire)
        except Exception:
            pass

    def _on_end_reached(self, event) -> None:
        from twisted.internet import reactor

        def fire():
            client = self._client
            if client is None:
                return
            handler = getattr(client, "eofReportedByPlayer", None)
            if handler is None:
                return
            try:
                handler()
            except Exception:
                pass

        try:
            reactor.callFromThread(fire)
        except Exception:
            pass

    def _on_error(self, event) -> None:
        from twisted.internet import reactor

        def fire():
            client = self._client
            if client is None or not hasattr(client, "ui"):
                return
            try:
                client.ui.showErrorMessage("Playback error reported by libvlc")
            except Exception:
                pass

        try:
            reactor.callFromThread(fire)
        except Exception:
            pass

    # --- API used by the Phase 4 settings panel --------------------------

    def get_audio_tracks(self) -> list:
        return [
            {"id": tid, "label": _label(label)}
            for tid, label in (self._player.audio_get_track_description() or [])
        ]

    def get_subtitle_tracks(self) -> list:
        return [
            {"id": tid, "label": _label(label)}
            for tid, label in (self._player.video_get_spu_description() or [])
        ]

    def set_audio_track(self, track_id: int) -> None:
        self._player.audio_set_track(int(track_id))

    def set_subtitle_track(self, track_id: int) -> None:
        self._player.video_set_spu(int(track_id))

    def set_subtitle_delay_ms(self, delay_ms: int) -> None:
        # python-vlc takes microseconds.
        self._player.video_set_spu_delay(int(delay_ms) * 1000)
