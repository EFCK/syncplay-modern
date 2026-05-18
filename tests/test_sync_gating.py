"""Tests for the ready-gated sync model.

Spec: docs/superpowers/specs/2026-05-18-ready-gated-sync-design.md

The rule: ready is in, not-ready is out. While not ready,
SyncplayClient.updatePlayerStatus must not call sendState, and
_changePlayerStateAccordingToGlobalState must not touch the player.
On the not-ready -> ready transition, the local player snaps to the
group's current position and pause state, and any held file
announcement is replayed.

These tests bypass __init__ and stub only the surface each method
actually touches — same pattern as test_seek_echo_regression.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

import pytest

from syncplay.client import SyncplayClient


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _RecordingProtocol:
    state_calls: List[tuple] = field(default_factory=list)
    file_settings: List[dict] = field(default_factory=list)
    logged: bool = True

    def sendState(self, position, paused, doSeek, latencyCalculation, stateChange):
        self.state_calls.append((position, paused, doSeek, stateChange))

    def sendFileSetting(self, file_):
        self.file_settings.append(file_)


@dataclass
class _RecordingPlayer:
    position_calls: List[float] = field(default_factory=list)
    paused_calls: List[bool] = field(default_factory=list)

    def setPosition(self, position):
        self.position_calls.append(position)

    def setPaused(self, paused):
        self.paused_calls.append(paused)


@dataclass
class _FakeUser:
    username: str
    ready: Optional[bool] = None
    file: Optional[dict] = None
    room: str = "movie-night"

    def isReady(self):
        return self.ready

    def setReady(self, ready):
        self.ready = ready

    def canControl(self):
        return True


class _FakeUserlist:
    def __init__(self, current_user, others=None):
        self.currentUser = current_user
        self._users = {u.username: u for u in (others or [])}

    def isReady(self, username):
        if username == self.currentUser.username:
            return self.currentUser.isReady()
        user = self._users.get(username)
        return user.isReady() if user else None

    def setReady(self, username, isReady):
        if username == self.currentUser.username:
            self.currentUser.setReady(isReady)
        elif username in self._users:
            self._users[username].setReady(isReady)

    def areAllUsersInRoomReady(self, requireSameFilenames=False):
        if not self.currentUser.isReady():
            return False
        for u in self._users.values():
            if u.room == self.currentUser.room and not u.isReady():
                return False
        return True


def _make_client(
    *,
    ready,
    last_global_update=None,
    global_position=0.0,
    global_paused=True,
    player_position=0.0,
    player_paused=True,
    file_dict=None,
    others=None,
):
    """Build a SyncplayClient with just enough surface for the tests."""
    client = SyncplayClient.__new__(SyncplayClient)
    user = _FakeUser(
        "me",
        ready=ready,
        file=file_dict or {"name": "a.mkv", "duration": 100.0, "size": 1},
    )
    client.userlist = _FakeUserlist(user, others=others)
    client._protocol = _RecordingProtocol()
    client._player = _RecordingPlayer()

    now = time.time()
    client._lastPlayerUpdate = now - 0.1
    client._lastGlobalUpdate = last_global_update
    client._playerPosition = player_position
    client._globalPosition = global_position
    client._playerPaused = player_paused
    client._globalPaused = global_paused
    client.playerPositionBeforeLastSeek = 0.0
    client.lastRewindTime = None
    client.lastAdvanceTime = None
    client._userOffset = 0.0
    client._speedChanged = False
    client.behindFirstDetected = None
    client._config = {
        "dontSlowDownWithMe": False,
        "rewindThreshold": 9999,
        "rewindOnDesync": False,
        "fastforwardOnDesync": False,
        "slowOnDesync": False,
    }

    class _NullUi:
        def showMessage(self, *a, **kw):
            pass

        def showErrorMessage(self, *a, **kw):
            pass

        def showDebugMessage(self, *a, **kw):
            pass

        def userListChange(self, *a, **kw):
            pass

    client.ui = _NullUi()

    class _Warnings:
        def checkReadyStates(self):
            pass

    client._warnings = _Warnings()

    return client


# ---------------------------------------------------------------------------
# Predicate
# ---------------------------------------------------------------------------


def test_sync_engaged_false_when_ready_is_none():
    client = _make_client(ready=None)
    assert client._syncEngaged() is False


def test_sync_engaged_false_when_ready_is_false():
    client = _make_client(ready=False)
    assert client._syncEngaged() is False


def test_sync_engaged_true_when_ready_is_true():
    client = _make_client(ready=True)
    assert client._syncEngaged() is True


# ---------------------------------------------------------------------------
# Outbound state silence
# ---------------------------------------------------------------------------


def test_pause_change_while_not_ready_does_not_send_state():
    """User toggles pause locally; without engagement, the group must
    not see it. updatePlayerStatus is the path libvlc->client uses."""
    client = _make_client(
        ready=False,
        last_global_update=time.time() - 1.0,
        global_position=10.0,
        global_paused=False,
        player_position=10.0,
        player_paused=False,
    )

    # libvlc reports the user just paused at position 10.
    client.updatePlayerStatus(paused=True, position=10.0)

    assert client._protocol.state_calls == []


def test_pause_change_while_ready_sends_state():
    """Sanity: the gate is purely about engagement, not a regression."""
    client = _make_client(
        ready=True,
        last_global_update=time.time() - 1.0,
        global_position=10.0,
        global_paused=False,
        player_position=10.0,
        player_paused=False,
    )

    client.updatePlayerStatus(paused=True, position=10.0)

    assert len(client._protocol.state_calls) == 1


# ---------------------------------------------------------------------------
# Inbound state silence (with global mirror)
# ---------------------------------------------------------------------------


def test_global_state_mirrored_even_when_not_engaged():
    """When not-ready, we still update _globalPosition / _globalPaused
    so the snap-on-ready transition has a target. But the player must
    not be touched."""
    client = _make_client(
        ready=False,
        last_global_update=time.time() - 1.0,
        global_position=20.0,
        global_paused=True,
        player_position=5.0,
        player_paused=False,
    )

    made_change = client._changePlayerStateAccordingToGlobalState(
        position=200.0, paused=False, doSeek=True, setBy="alice"
    )

    assert made_change is False
    assert client._globalPosition == 200.0
    assert client._globalPaused is False
    assert client._lastGlobalUpdate is not None
    assert client._player.position_calls == []
    assert client._player.paused_calls == []


# ---------------------------------------------------------------------------
# Snap-on-ready
# ---------------------------------------------------------------------------


def test_setReady_snaps_player_on_not_ready_to_ready_transition():
    """When the local user flips from not-ready to ready with a peer
    in the room, the local player should snap to the group's position
    and pause state."""
    peer = _FakeUser("alice", ready=True, file={"name": "movie.mkv"})
    client = _make_client(
        ready=False,
        last_global_update=time.time(),  # paused, so no extrapolation
        global_position=300.0,
        global_paused=True,
        others=[peer],
    )

    client.setReady(username="me", isReady=True)

    assert client._player.position_calls == [pytest.approx(300.0, abs=0.05)]
    assert client._player.paused_calls == [True]


def test_setReady_does_not_snap_when_alone_in_room():
    """No peer in the room means no group state to sync to — snapping
    would yank the user's solo playback back to _globalPosition=0
    paused and look like the Ready button broke the video."""
    client = _make_client(
        ready=False,
        last_global_update=time.time(),
        global_position=0.0,
        global_paused=True,
    )

    client.setReady(username="me", isReady=True)

    assert client._player.position_calls == []
    assert client._player.paused_calls == []


def test_setReady_no_snap_when_already_ready():
    """ready -> ready shouldn't trigger the snap."""
    client = _make_client(
        ready=True,
        last_global_update=time.time(),
        global_position=300.0,
        global_paused=True,
    )

    client.setReady(username="me", isReady=True)

    assert client._player.position_calls == []
    assert client._player.paused_calls == []


def test_setReady_no_snap_without_global_state_yet():
    """If we never received a global state — alone in a room, or pre-
    connection ready toggle — the snap is a no-op."""
    client = _make_client(ready=False, last_global_update=None)

    client.setReady(username="me", isReady=True)

    assert client._player.position_calls == []
    assert client._player.paused_calls == []


def test_setReady_other_user_does_not_snap_local_player():
    """Only currentUser readying should snap; other users readying is
    purely informational."""
    other = _FakeUser("alice", ready=False)
    client = _make_client(
        ready=True,
        last_global_update=time.time(),
        global_position=300.0,
        global_paused=True,
        others=[other],
    )

    client.setReady(username="alice", isReady=True)

    assert client._player.position_calls == []
    assert client._player.paused_calls == []


# ---------------------------------------------------------------------------
# File announcement (always flows — sync-gating covers playback, not presence)
# ---------------------------------------------------------------------------


def test_sendFile_announces_even_when_not_engaged():
    """Peers should see what a user is loading even before that user
    has readied up — file presence is informational, not a sync action."""
    client = _make_client(ready=False)

    client.sendFile()

    assert len(client._protocol.file_settings) == 1


def test_sendFile_announces_when_engaged():
    client = _make_client(ready=True)

    client.sendFile()

    assert len(client._protocol.file_settings) == 1


# ---------------------------------------------------------------------------
# Strict all-ready unpause gate
# ---------------------------------------------------------------------------


def test_instaplay_blocked_when_other_user_not_ready():
    other = _FakeUser("alice", ready=False)
    client = _make_client(ready=True, others=[other])

    assert client.instaplayConditionsMet() is False


def test_instaplay_blocked_when_local_user_not_ready():
    other = _FakeUser("alice", ready=True)
    client = _make_client(ready=False, others=[other])

    assert client.instaplayConditionsMet() is False


def test_instaplay_passes_when_everyone_ready():
    other = _FakeUser("alice", ready=True)
    client = _make_client(ready=True, others=[other])

    assert client.instaplayConditionsMet() is True


def test_instaplay_passes_when_alone_and_ready():
    client = _make_client(ready=True)

    assert client.instaplayConditionsMet() is True


# ---------------------------------------------------------------------------
# setPaused gate (ready user, group not all ready)
# ---------------------------------------------------------------------------


def test_setPaused_blocks_unpause_when_someone_else_not_ready():
    other = _FakeUser("alice", ready=False)
    client = _make_client(ready=True, others=[other], player_paused=True)

    toast_calls = []

    class _Notify:
        def showSyncBlockedMessage(self, count):
            toast_calls.append(count)

        def showMessage(self, *a, **kw):
            pass

        def showErrorMessage(self, *a, **kw):
            pass

        def showDebugMessage(self, *a, **kw):
            pass

        def userListChange(self, *a, **kw):
            pass

    client.ui = _Notify()

    client.setPaused(False)

    assert client._player.paused_calls == [True]  # snapped back
    assert toast_calls == [1]


def test_setPaused_allows_pause_always():
    """Pause never blocks — only unpause is gated."""
    other = _FakeUser("alice", ready=False)
    client = _make_client(
        ready=True, others=[other], player_paused=False
    )

    client.setPaused(True)

    assert client._player.paused_calls == [True]


def test_setPaused_allows_unpause_when_everyone_ready():
    other = _FakeUser("alice", ready=True)
    client = _make_client(ready=True, others=[other], player_paused=True)

    client.setPaused(False)

    assert client._player.paused_calls == [False]
