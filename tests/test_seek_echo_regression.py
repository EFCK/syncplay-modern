"""Regression tests for the post-seek "video reverts" bug.

When user X seeks forward, the symptom was:
  1. Y's libvlc set_time(T) is async, so Y's cached _playerPosition
     stays at the pre-seek value for the ~30-120 ms until the next
     askPlayer tick.
  2. Y receives X's seek state. protocols.handleState immediately
     echoes Y's local state back to the server via getLocalState() ->
     getPlayerPosition(), which extrapolates from the stale
     _playerPosition. Y reports OLD position.
  3. Server stores Y's watcher.position = OLD.
  4. Server's per-watcher 1s timer fires Room.getPosition(); when
     age > 1, the min-watcher fallback picks Y (OLD < T) and snaps
     the room back to OLD with setBy=Y.
  5. The next broadcast tells X "go to OLD"; X rewinds.

The two fixes covered here:
  - Fix 1 (client): SyncplayClient.getLocalState() prefers
    getGlobalPosition() when _lastGlobalUpdate > _lastPlayerUpdate,
    so Y echoes the position it just applied, not stale OLD.
  - Fix 3 (server): Room.setPosition() resets _lastUpdate, so the
    min-watcher fallback can't fire for ~1 s after a real seek.
"""

from __future__ import annotations

import time

import pytest

from syncplay.client import SyncplayClient
from syncplay.server import Room


# ---------------------------------------------------------------------------
# Fix 1 — client-side getLocalState
# ---------------------------------------------------------------------------


def _make_client_stub(
    *,
    last_player_update: float | None,
    last_global_update: float | None,
    player_position: float,
    global_position: float,
    paused: bool,
) -> SyncplayClient:
    """Bypass __init__ and set just the attributes getLocalState needs."""
    client = SyncplayClient.__new__(SyncplayClient)
    client._lastPlayerUpdate = last_player_update
    client._lastGlobalUpdate = last_global_update
    client._playerPosition = player_position
    client._globalPosition = global_position
    client._playerPaused = paused
    client._globalPaused = paused
    client._config = {"dontSlowDownWithMe": False}
    return client


def test_get_local_state_prefers_global_when_global_update_is_fresher():
    """Right after a server seek arrives, before askPlayer resamples.

    _lastGlobalUpdate just got set in
    _changePlayerStateAccordingToGlobalState; _lastPlayerUpdate is
    from the previous askPlayer tick. getLocalState must echo the
    just-applied global position, not the stale player extrapolation.
    """
    now = time.time()
    client = _make_client_stub(
        last_player_update=now - 0.5,
        last_global_update=now - 0.001,
        player_position=100.0,   # stale OLD
        global_position=500.0,   # T (where the seek went)
        paused=True,
    )

    position, paused, seeked, state_change = client.getLocalState()

    assert position == pytest.approx(500.0, abs=0.05)
    assert paused is True
    assert seeked is False  # never claim a seek on the echo


def test_get_local_state_uses_player_in_steady_state():
    """Normal playback: askPlayer fires every 100 ms (faster than the
    server's 1 s state cadence), so _lastPlayerUpdate is usually newer
    than _lastGlobalUpdate. In that case we must NOT substitute global —
    the server relies on each client reporting its real position so
    drift correction works.
    """
    now = time.time()
    client = _make_client_stub(
        last_player_update=now - 0.05,
        last_global_update=now - 0.8,
        player_position=200.0,
        global_position=198.0,
        paused=False,
    )

    position, _paused, _seeked, _sc = client.getLocalState()

    # Within ~50 ms of last sample, getPlayerPosition extrapolates
    # roughly 0.05 s past player_position when not paused.
    assert position == pytest.approx(200.05, abs=0.1)


def test_get_local_state_falls_back_to_player_when_no_global_yet():
    """Before the first server state has arrived, there's nothing to
    fall back to — return the player position as today.
    """
    now = time.time()
    client = _make_client_stub(
        last_player_update=now - 0.05,
        last_global_update=None,
        player_position=42.0,
        global_position=0.0,
        paused=True,
    )

    result = client.getLocalState()

    # Existing contract: no global => (None, None, None, None).
    assert result == (None, None, None, None)


# ---------------------------------------------------------------------------
# Fix 3 — server-side Room.getPosition min-watcher cooldown
# ---------------------------------------------------------------------------


class _FakeWatcher:
    """Just enough surface for Room.getPosition's min(watchers.values())."""

    def __init__(self, name: str, position: float):
        self._name = name
        self._position = position
        self._file = {"path": "fake.mkv"}  # truthy => valid for __lt__

    def getName(self):
        return self._name

    def getPosition(self):
        return self._position

    def setPosition(self, position):
        # Room.setPosition writes through to every watcher; in the real
        # server this updates the per-watcher cached position with
        # extrapolation timestamps. For tests we just store it so the
        # subsequent min(watchers) comparison sees consistent data.
        self._position = position

    def __lt__(self, other):
        if self._position is None or self._file is None:
            return False
        if other.getPosition() is None or other._file is None:
            return True
        return self._position < other.getPosition()


def _make_room_with_watchers(*watchers) -> Room:
    room = Room("test-room", roomsdbhandle=None)
    for w in watchers:
        room._watchers[w.getName()] = w
    return room


def test_room_getposition_skips_min_watcher_immediately_after_setposition():
    """After a real seek to T, server applies room.setPosition(T, X).
    Watcher Y may briefly still report a stale OLD position (because
    Y's first echo races the libvlc seek). The room must not snap to
    Y's stale OLD during this window — that's the bug.
    """
    x = _FakeWatcher("alice", 500.0)
    y = _FakeWatcher("bob", 100.0)

    room = _make_room_with_watchers(x, y)
    # The room has been running long enough for min-watcher to be
    # eligible (age > 1 since last reset). This is the realistic state
    # before a seek arrives in a steady-state room.
    room._lastUpdate = time.time() - 5

    # Simulate a real seek arriving: room takes X's position and writes
    # it through to all watchers' caches.
    room.setPosition(500.0, setBy=x)
    # Simulate Y's stale echo arriving moments later: Y's client echoes
    # the pre-seek position via getLocalState; server.updateState calls
    # Y.setPosition(OLD).
    y.setPosition(100.0)

    # Server's next periodic Room.getPosition call (any time within
    # ~1 s of the setPosition) must return ~500, not snap back to Y's
    # 100. The fix resets _lastUpdate inside setPosition so age < 1.
    pos = room.getPosition()

    assert pos == pytest.approx(500.0, abs=0.1)


def test_room_getposition_uses_min_watcher_after_cooldown_passes():
    """The min-watcher logic is real upstream behavior (anchor to the
    slowest watcher so everyone catches up). We only suppress it for
    the brief post-seek window; once the cooldown elapses, normal
    behavior resumes.
    """
    x = _FakeWatcher("alice", 500.0)
    y = _FakeWatcher("bob", 100.0)

    room = _make_room_with_watchers(x, y)
    room.setPosition(500.0, setBy=x)
    y.setPosition(100.0)  # stale echo

    # Backdate _lastUpdate so we're past the 1 s cooldown.
    room._lastUpdate = time.time() - 5

    pos = room.getPosition()

    # Slowest watcher (Y at 100) pulls room back — original behavior.
    assert pos == pytest.approx(100.0, abs=0.1)
    assert room._setBy is y
