"""Unit tests for RoomState — Qt-free, no QApplication needed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from syncplay.ui.modern.events import (
    RoomSnapshot,
    UserFileChanged,
    UserJoined,
    UserLeft,
    UserReadyChanged,
)
from syncplay.ui.modern.roomState import RoomState

from tests.conftest import collect_events


@dataclass
class _FakeUser:
    """Minimal stand-in for SyncplayClient's User object."""

    username: str
    ready: bool = False
    file: Optional[dict] = field(default_factory=dict)

    def isReady(self) -> bool:
        return self.ready


def _rooms_with(users):
    return {"movie-night": list(users)}


def test_first_snapshot_emits_only_room_snapshot():
    state = RoomState()
    events = collect_events(state)
    alice = _FakeUser("alice")

    state.update_from_rooms(alice, _rooms_with([alice]))

    # First snapshot intentionally skips per-user join events so we
    # don't fire a join storm at connect.
    assert all(isinstance(e, RoomSnapshot) for e in events)
    assert len(events) == 1
    snap = events[0]
    assert snap.current_user == "alice"
    assert snap.is_ready is False
    assert [u["name"] for u in snap.users] == ["alice"]


def test_repeat_with_identical_rooms_emits_only_snapshot():
    state = RoomState()
    alice = _FakeUser("alice")
    state.update_from_rooms(alice, _rooms_with([alice]))

    events = collect_events(state)
    state.update_from_rooms(alice, _rooms_with([alice]))

    assert len(events) == 1
    assert isinstance(events[0], RoomSnapshot)


def test_ready_toggle_emits_user_ready_changed():
    state = RoomState()
    alice = _FakeUser("alice", ready=False)
    state.update_from_rooms(alice, _rooms_with([alice]))

    events = collect_events(state)
    alice.ready = True
    state.update_from_rooms(alice, _rooms_with([alice]))

    ready_events = [e for e in events if isinstance(e, UserReadyChanged)]
    assert len(ready_events) == 1
    assert ready_events[0].user == "alice"
    assert ready_events[0].ready is True

    snap = next(e for e in events if isinstance(e, RoomSnapshot))
    assert snap.is_ready is True


def test_file_change_emits_user_file_changed():
    state = RoomState()
    alice = _FakeUser("alice", file={"name": "a.mkv"})
    state.update_from_rooms(alice, _rooms_with([alice]))

    events = collect_events(state)
    alice.file = {"name": "b.mkv"}
    state.update_from_rooms(alice, _rooms_with([alice]))

    file_events = [e for e in events if isinstance(e, UserFileChanged)]
    assert len(file_events) == 1
    assert file_events[0].user == "alice"
    assert file_events[0].filename == "b.mkv"


def test_user_join_after_first_snapshot_emits_user_joined():
    state = RoomState()
    alice = _FakeUser("alice")
    state.update_from_rooms(alice, _rooms_with([alice]))

    events = collect_events(state)
    bob = _FakeUser("bob")
    state.update_from_rooms(alice, _rooms_with([alice, bob]))

    join_events = [e for e in events if isinstance(e, UserJoined)]
    assert len(join_events) == 1
    assert join_events[0].user == "bob"


def test_user_left_emits_user_left():
    state = RoomState()
    alice = _FakeUser("alice")
    bob = _FakeUser("bob")
    state.update_from_rooms(alice, _rooms_with([alice, bob]))

    events = collect_events(state)
    state.update_from_rooms(alice, _rooms_with([alice]))

    leave_events = [e for e in events if isinstance(e, UserLeft)]
    assert len(leave_events) == 1
    assert leave_events[0].user == "bob"


def test_filename_basename_strip():
    state = RoomState()
    alice = _FakeUser("alice", file={"name": "/home/alice/Videos/movie.mkv"})
    state.update_from_rooms(alice, _rooms_with([alice]))

    snap = state._last  # internal — same shape used to feed snapshots
    assert snap["alice"]["filename"] == "movie.mkv"


def test_snapshot_is_ready_reflects_current_user_state():
    state = RoomState()
    alice = _FakeUser("alice", ready=True)

    events = collect_events(state)
    state.update_from_rooms(alice, _rooms_with([alice]))

    snap = events[-1]
    assert isinstance(snap, RoomSnapshot)
    assert snap.is_ready is True
