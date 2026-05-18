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

import os
import sys
from typing import Callable, Optional

from syncplay.players.basePlayer import BasePlayer


def _ensure_vlc_plugin_path() -> None:
    """Set VLC_PLUGIN_PATH so libvlc can find its plugins.

    System-installed Python finds them by default, but PyInstaller-frozen
    builds often can't because the embedded loader strips out the dynamic
    discovery hints. We probe a small list of canonical locations and set
    the env var ourselves if needed. No-op on Windows/macOS where the
    bundled VLC supplies its own plugins dir.
    """
    if os.environ.get("VLC_PLUGIN_PATH"):
        return
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return
    candidates = [
        "/usr/lib/x86_64-linux-gnu/vlc/plugins",
        "/usr/lib64/vlc/plugins",
        "/usr/lib/vlc/plugins",
        "/usr/local/lib/vlc/plugins",
    ]
    for path in candidates:
        if os.path.isdir(path):
            os.environ["VLC_PLUGIN_PATH"] = path
            return


def apply_vlc_install_path(path: str) -> None:
    """Point libvlc at a user-configured VLC install directory.

    `path` is the folder the user picked in the onboarding dialog
    (e.g. ``C:\\Program Files\\VideoLAN\\VLC`` on Windows,
    ``/Applications/VLC.app`` on macOS, the VLC libdir on Linux).
    Empty/None/non-existent = no-op, defer to the platform probe.

    Idempotent — safe to call repeatedly. Always called *before* the
    first ``vlc.Instance()`` so the env is in place when ctypes loads
    libvlc.
    """
    if not path:
        return
    path = os.path.expanduser(path).rstrip(os.sep)
    if not os.path.isdir(path):
        return

    if sys.platform.startswith("win"):
        # ctypes.CDLL("libvlc.dll") searches PATH; prepend our dir.
        existing = os.environ.get("PATH", "")
        parts = existing.split(os.pathsep) if existing else []
        if path not in parts:
            os.environ["PATH"] = path + os.pathsep + existing
        plugins = os.path.join(path, "plugins")
        if os.path.isdir(plugins):
            os.environ["VLC_PLUGIN_PATH"] = plugins
    elif sys.platform == "darwin":
        # Accept either '/Applications/VLC.app' or its inner libdir.
        plugin_candidates = [
            os.path.join(path, "Contents", "MacOS", "plugins"),
            os.path.join(path, "plugins"),
        ]
        for cand in plugin_candidates:
            if os.path.isdir(cand):
                os.environ["VLC_PLUGIN_PATH"] = cand
                break
        lib_dir = os.path.join(path, "Contents", "MacOS", "lib")
        if os.path.isdir(lib_dir):
            existing = os.environ.get("DYLD_LIBRARY_PATH", "")
            parts = existing.split(os.pathsep) if existing else []
            if lib_dir not in parts:
                os.environ["DYLD_LIBRARY_PATH"] = lib_dir + os.pathsep + existing
    else:
        # Linux: user may have picked the plugins dir itself, its parent,
        # or the directory holding libvlc.so. Set VLC_PLUGIN_PATH from
        # the first plausible candidate.
        if os.path.basename(path) == "plugins":
            os.environ["VLC_PLUGIN_PATH"] = path
        else:
            plugins = os.path.join(path, "plugins")
            if os.path.isdir(plugins):
                os.environ["VLC_PLUGIN_PATH"] = plugins
            else:
                os.environ["VLC_PLUGIN_PATH"] = path


_ensure_vlc_plugin_path()


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
    """libvlc.Instance is process-wide and expensive — cache it.

    Some libvlc builds (notably PyInstaller-frozen runs where the plugin
    path discovery is shakier) return None when an arg list is passed.
    We attempt the preferred arg list first, then fall back to no args.
    """
    global _vlc_instance
    if _vlc_instance is not None:
        return _vlc_instance
    import vlc
    preferred_args = [
        "--no-xlib",            # safer alongside Qt's X11 access
        "--quiet",
        "--no-video-title-show",
        "--no-osd",             # we render our own toasts
        # Keep libvlc's mouse handling enabled so its built-in overlay
        # (play / pause / fullscreen buttons, seek bar) renders and is
        # clickable. Disable only the keyboard grab so Qt owns letter
        # shortcuts (Space, F, K, etc.) — without this libvlc would
        # consume them on its X11 subwindow and our QShortcuts would
        # never fire.
        "--no-keyboard-events",
    ]
    try:
        instance = vlc.Instance(preferred_args)
    except Exception:
        instance = None
    if instance is None:
        # Retry without the arg list — preserves a working player at the
        # cost of losing some flags (those become defaults).
        try:
            instance = vlc.Instance()
        except Exception:
            instance = None
    if instance is None:
        raise RuntimeError(
            "libvlc failed to initialise. Is VLC installed? "
            "(Ubuntu/Debian: 'sudo apt install vlc'.)"
        )
    _vlc_instance = instance
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
        # `:start-paused` tells libvlc to load and parse the file but keep
        # playback paused on the first frame. Without this the player
        # auto-plays the moment a file is dropped in, before the user has
        # had a chance to ready up — and before the sync state machine has
        # decided whether playback should actually begin.
        try:
            media.add_option(":start-paused")
        except Exception:
            pass
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

        # `play()` is still required so libvlc engages the demuxer and the
        # renderer attaches to our X window — without it the video surface
        # stays black. `:start-paused` above ensures it pauses on frame 1.
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

    # --- Helpers used by keyboard shortcuts (Phase 5) --------------------

    def is_paused(self) -> bool:
        return self._player.get_state() != self._vlc.State.Playing

    def toggle_pause(self) -> None:
        if self.is_paused():
            self.setPaused(False)
        else:
            self.setPaused(True)

    def position_seconds(self) -> float:
        return max(0.0, (self._player.get_time() or 0) / 1000.0)

    def length_seconds(self) -> float:
        try:
            return max(0.0, (self._player.get_length() or 0) / 1000.0)
        except Exception:
            return 0.0

    def is_ended(self) -> bool:
        try:
            return self._player.get_state() == self._vlc.State.Ended
        except Exception:
            return False

    def seek_by_seconds(self, delta_s: float) -> None:
        new_position = max(0.0, self.position_seconds() + delta_s)
        self.setPosition(new_position)

    def set_volume(self, volume: int) -> None:
        # Cap at 100 (unity gain). libvlc technically accepts up to
        # 200, but software amplification clips audio everywhere and
        # the Windows audio backends saturate around 140 — so any
        # value above 100 is either inaudible or distorted. Keep the
        # keyboard volume-up shortcut from pushing past this cap.
        volume = max(0, min(100, int(volume)))
        self._player.audio_set_volume(volume)

    def get_volume(self) -> int:
        try:
            return int(self._player.audio_get_volume())
        except Exception:
            return 100

    def adjust_volume(self, delta: int) -> int:
        new_vol = self.get_volume() + int(delta)
        self.set_volume(new_vol)
        return self.get_volume()

    def toggle_mute(self) -> None:
        self._player.audio_toggle_mute()

    def is_muted(self) -> bool:
        try:
            return bool(self._player.audio_get_mute())
        except Exception:
            return False

    def adjust_subtitle_delay_ms(self, delta_ms: int) -> int:
        try:
            current_us = self._player.video_get_spu_delay()
        except Exception:
            current_us = 0
        new_us = int(current_us) + int(delta_ms) * 1000
        self._player.video_set_spu_delay(new_us)
        return new_us // 1000

    def adjust_audio_delay_ms(self, delta_ms: int) -> int:
        try:
            current_us = self._player.audio_get_delay()
        except Exception:
            current_us = 0
        new_us = int(current_us) + int(delta_ms) * 1000
        self._player.audio_set_delay(new_us)
        return new_us // 1000

    def get_speed(self) -> float:
        try:
            return float(self._player.get_rate())
        except Exception:
            return 1.0

    def adjust_speed(self, multiplier: float) -> float:
        new_rate = max(0.25, min(4.0, self.get_speed() * float(multiplier)))
        self._player.set_rate(new_rate)
        return new_rate

    def reset_speed(self) -> float:
        self._player.set_rate(1.0)
        return 1.0

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

    def cycle_audio_track(self) -> str:
        """Switch to the next audio track. Returns the new track's label."""
        tracks = self.get_audio_tracks()
        if not tracks:
            return ""
        try:
            current_id = self._player.audio_get_track()
        except Exception:
            current_id = tracks[0]["id"]
        ids = [t["id"] for t in tracks]
        try:
            idx = ids.index(current_id)
            next_id = ids[(idx + 1) % len(ids)]
        except ValueError:
            next_id = ids[0]
        self._player.audio_set_track(int(next_id))
        next_track = next(t for t in tracks if t["id"] == next_id)
        return next_track["label"]

    def cycle_subtitle_track(self) -> str:
        """Switch to the next subtitle track. Returns the new track's label."""
        tracks = self.get_subtitle_tracks()
        if not tracks:
            return ""
        try:
            current_id = self._player.video_get_spu()
        except Exception:
            current_id = tracks[0]["id"]
        ids = [t["id"] for t in tracks]
        try:
            idx = ids.index(current_id)
            next_id = ids[(idx + 1) % len(ids)]
        except ValueError:
            next_id = ids[0]
        self._player.video_set_spu(int(next_id))
        next_track = next(t for t in tracks if t["id"] == next_id)
        return next_track["label"]

    def set_subtitle_delay_ms(self, delay_ms: int) -> None:
        # python-vlc takes microseconds.
        self._player.video_set_spu_delay(int(delay_ms) * 1000)
