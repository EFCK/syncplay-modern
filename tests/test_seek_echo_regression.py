"""Regression tests for the post-seek / post-pause "state reverts" bug.

When user X seeks forward or presses play, the symptom was the same:
the room snapped back to its pre-action state seconds later, with
the revert attributed to a peer who hadn't touched anything.

The mechanism is the same RTT ping-pong in both cases:
  1. Y's libvlc applies the server's seek/unpause asynchronously
     (~30-120 ms), so Y's cached _playerPosition / _playerPaused
     stay at the pre-change values until the next askPlayer tick.
  2. Y receives the server's state. protocols.handleState
     immediately echoes Y's local state back via getLocalState(),
     which reads the stale cache and reports OLD position / OLD
     paused.
  3. Server stores Y's stale report.
  4a. Position case: server's per-watcher 1s timer fires
      Room.getPosition(); when age > 1, the min-watcher fallback
      picks Y (OLD < T) and snaps the room back.
  4b. Pause case: server's Watcher.updateState sees room.isPaused()
      disagrees with Y's reported paused, flips Room.setPaused with
      setBy=Y.
  5. Next broadcast tells everyone "go back"; X's video reverts.

Fixes covered here:
  - Fix 1 (client): SyncplayClient.getLocalState() prefers
    getGlobalPosition() AND getGlobalPaused() when
    _lastGlobalUpdate > _lastPlayerUpdate. Y echoes what it just
    applied, not stale OLD. Same code path covers both position
    and paused — they were always vulnerable to the same race.
  - Fix 3 (server): Room.setPosition() resets _lastUpdate, so the
    min-watcher fallback can't fire for ~1 s after a real seek.
    (No analogous server-side fix is needed for paused: the only
    path that flips Room.setPaused is Watcher.updateState, which
    is fed by watcher echoes — fixing the echo breaks the loop.)
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
    player_paused: bool | None = None,
    global_paused: bool | None = None,
) -> SyncplayClient:
    """Bypass __init__ and set just the attributes getLocalState needs.

    ``paused`` is the default for both player and global state when the
    two agree (the steady-state path). Pass ``player_paused`` /
    ``global_paused`` explicitly to make them diverge — that's the
    stale-cache window the pause-echo fix exists for.
    """
    client = SyncplayClient.__new__(SyncplayClient)
    client._lastPlayerUpdate = last_player_update
    client._lastGlobalUpdate = last_global_update
    client._playerPosition = player_position
    client._globalPosition = global_position
    client._playerPaused = paused if player_paused is None else player_paused
    client._globalPaused = paused if global_paused is None else global_paused
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
# Pause-echo fix — same window as the seek fix, applied to `paused`.
# ---------------------------------------------------------------------------


def test_get_local_state_prefers_global_paused_when_global_update_is_fresher():
    """Right after a server unpause arrives, before askPlayer
    resamples. _playerPaused cache still holds the pre-unpause value
    (True) because _serverUnpaused only flipped the player itself, not
    the cache. Echoing that stale True back at the server makes the
    Watcher.updateState flip the room PAUSED, attributed to us — the
    play-then-snap-back symptom.
    """
    now = time.time()
    client = _make_client_stub(
        last_player_update=now - 0.5,
        last_global_update=now - 0.001,
        player_position=100.0,
        global_position=100.0,
        paused=True,           # unused when player/global override
        player_paused=True,    # stale OLD — libvlc hasn't applied
        global_paused=False,   # the server just told us to play
    )

    _position, paused, _seeked, _state_change = client.getLocalState()

    assert paused is False  # echo the just-applied state, not stale OLD


def test_get_local_state_prefers_global_paused_in_reverse_direction_too():
    """Symmetric case: server just told us to PAUSE; player cache
    still says playing. Echoing the stale `False` would flip the
    room back to PLAYING via the same path."""
    now = time.time()
    client = _make_client_stub(
        last_player_update=now - 0.5,
        last_global_update=now - 0.001,
        player_position=100.0,
        global_position=100.0,
        paused=False,
        player_paused=False,
        global_paused=True,
    )

    _position, paused, _seeked, _state_change = client.getLocalState()

    assert paused is True


def test_get_local_state_uses_player_paused_in_steady_state():
    """When askPlayer ticks are fresher than the last global update
    (the typical 100 ms vs 1 s cadence), echo the player's actual
    cached pause state. Substituting global in steady state would
    mask real, intentional local pause changes from the server.
    """
    now = time.time()
    client = _make_client_stub(
        last_player_update=now - 0.05,
        last_global_update=now - 0.8,
        player_position=200.0,
        global_position=198.0,
        paused=False,
        player_paused=True,     # local user just hit pause
        global_paused=False,    # server hasn't heard yet
    )

    _position, paused, _seeked, _sc = client.getLocalState()

    assert paused is True  # report the real local intent


# ---------------------------------------------------------------------------
# End-to-end regression: handleState's sub-handlers must not poison the
# echo invariant. The earlier stub-only tests can't catch this because
# they don't run _changePlayerStateAccordingToGlobalState — yet that's
# exactly where the bug lives in practice. _serverPaused calls
# setPosition, which bumps _lastPlayerUpdate to now, which (without the
# re-anchor at the end of _changePlayerStateAccordingToGlobalState)
# would defeat the getLocalState echo branch and let the watcher echo
# its stale _playerPaused=False back at the server.
# ---------------------------------------------------------------------------


class _RecordingPlayer:
    """Minimal BasePlayer surface."""

    def __init__(self):
        self.paused_calls = []
        self.position_calls = []
        self.speedSupported = False

    def setPaused(self, paused):
        self.paused_calls.append(paused)

    def setPosition(self, position):
        self.position_calls.append(position)


class _SilentUi:
    def showMessage(self, *a, **kw): pass
    def showErrorMessage(self, *a, **kw): pass
    def showDebugMessage(self, *a, **kw): pass


class _FakeUser:
    def __init__(self, username, ready=True, file_=None):
        self.username = username
        self.ready = ready
        self.file = file_ or {"name": "movie.mkv", "duration": 1000.0, "size": 1, "path": "/movie.mkv"}

    def isReady(self): return self.ready
    def canControl(self): return True


class _FakeUserlist:
    def __init__(self, current_user):
        self.currentUser = current_user


def _make_full_client(*, player_paused, global_paused, player_position=100.0, global_position=100.0):
    """A SyncplayClient instance with enough state to exercise
    _changePlayerStateAccordingToGlobalState end-to-end.
    """
    from syncplay.client import SyncplayClient

    client = SyncplayClient.__new__(SyncplayClient)
    client.userlist = _FakeUserlist(_FakeUser("me"))
    client._player = _RecordingPlayer()
    client.ui = _SilentUi()
    client._protocol = None

    now = time.time()
    # Steady-state-ish: askPlayer fresher than the last global update,
    # which is the worst case for the echo guard (and the typical case
    # outside the brief post-handleState window).
    client._lastPlayerUpdate = now - 0.05
    client._lastGlobalUpdate = now - 0.8
    client._playerPosition = player_position
    client._globalPosition = global_position
    client._playerPaused = player_paused
    client._globalPaused = global_paused
    client._userOffset = 0.0
    client._speedChanged = False
    client.behindFirstDetected = None
    client.lastRewindTime = None
    client.lastAdvanceTime = None
    client.lastLeftTime = 0
    client.playerPositionBeforeLastSeek = 0.0
    client._config = {
        "dontSlowDownWithMe": False,
        "rewindThreshold": 9999,
        "rewindOnDesync": False,
        "fastforwardOnDesync": False,
        "slowOnDesync": False,
    }
    return client


def test_serverPaused_does_not_poison_getLocalState_echo():
    """Reproduces the ping-pong: peer pauses, _serverPaused fires on
    us (setBy != self), its internal setPosition bumps
    _lastPlayerUpdate, and a naive getLocalState then echoes the stale
    _playerPaused=False back at the server, flipping the room PLAYING
    with setBy=us. The re-anchor at the end of
    _changePlayerStateAccordingToGlobalState fixes this.
    """
    client = _make_full_client(player_paused=False, global_paused=False)

    # Peer "alice" pauses; we receive the broadcast.
    client._changePlayerStateAccordingToGlobalState(
        position=120.0, paused=True, doSeek=False, setBy="alice"
    )

    # Immediately echo back, as protocols.handleState does.
    _position, paused, _seeked, _state_change = client.getLocalState()

    assert paused is True, (
        "Echo must report the just-applied global pause state, not the "
        "stale _playerPaused=False cache — otherwise the server flips "
        "the room back PLAYING via Watcher.updateState. Symptom: rapid "
        "'X paused / Y unpaused' ping-pong in chat."
    )


def test_serverUnpaused_echo_also_substitutes_global():
    """Symmetric case: peer unpauses; we receive the broadcast.
    _serverUnpaused doesn't call setPosition (so it doesn't bump
    _lastPlayerUpdate today), but the same invariant must hold so a
    future refactor that adds a setPosition call won't reintroduce
    the bug silently.
    """
    client = _make_full_client(player_paused=True, global_paused=True)

    client._changePlayerStateAccordingToGlobalState(
        position=120.0, paused=False, doSeek=False, setBy="alice"
    )

    _position, paused, _seeked, _state_change = client.getLocalState()

    assert paused is False


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
