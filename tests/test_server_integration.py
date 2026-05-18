"""In-process integration smoke test for the server broadcast loop.

Drives two `SyncServerProtocol` instances against a shared `SyncFactory`
via `proto_helpers.StringTransport`. No reactor, no real socket — but
the entire JSON command pipeline (Hello → Set{room} → Set{ready} →
Chat → State) runs through the real server code path.

This is the smallest test that would catch a regression in:
  - Hello / room joining
  - Chat broadcast to roommates
  - Ready-state propagation
  - State (pause/seek) broadcast
  - And, in conjunction with the seek-/pause-echo regression tests, the
    multi-watcher race conditions that fixed those bugs.

The tests deliberately stay synchronous (no deferreds, no callLater) so
they're reproducible and fast.
"""

from __future__ import annotations

import json
import time

import pytest
from twisted.internet.testing import StringTransport

from syncplay import version
from syncplay.server import SyncFactory


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class _Conn:
    """A single (transport, protocol) pair connected to the factory."""

    def __init__(self, factory: SyncFactory, peer_host: str = "127.0.0.1"):
        self.transport = StringTransport(peerAddress=_FakeAddr(peer_host))
        self.protocol = factory.buildProtocol(self.transport.getPeer())
        self.protocol.makeConnection(self.transport)

    def send(self, payload: dict) -> None:
        line = (json.dumps(payload) + "\r\n").encode("utf-8")
        self.protocol.dataReceived(line)

    def drain(self) -> list[dict]:
        """Return every JSON object the server has sent since last drain."""
        raw = self.transport.value()
        self.transport.clear()
        out: list[dict] = []
        for line in raw.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
        return out


class _FakeAddr:
    """Minimal stand-in for twisted.internet.address.IPv4Address.

    StringTransport's default peer is an IPv4Address; for our purposes
    we just need .host (used by SyncServerProtocol.__hash__ and the
    drop-with-error message)."""

    def __init__(self, host: str):
        self.host = host

    def __repr__(self) -> str:
        return f"<_FakeAddr {self.host}>"


@pytest.fixture
def factory() -> SyncFactory:
    """A fresh, minimal SyncFactory — no DB, no MOTD, no TLS, no stats."""
    return SyncFactory(
        port="0",
        password="",
        motdFilePath=None,
        roomsDbFile=None,
        permanentRoomsFile=None,
        isolateRooms=False,
        salt="deadbeef",  # explicit so the warning print is suppressed
        statsDbFile=None,
        tlsCertPath=None,
    )


def _hello(conn: _Conn, username: str, room: str) -> None:
    conn.send({
        "Hello": {
            "username": username,
            "room": {"name": room},
            "version": version,
            "realversion": version,
            "features": {
                "sharedPlaylists": True,
                "chat": True,
                "featureList": True,
                "readiness": True,
                "managedRooms": True,
                "persistentRooms": True,
            },
        }
    })


def _messages_of_type(messages: list[dict], key: str) -> list[dict]:
    return [m[key] for m in messages if key in m]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_hello_round_trip_admits_a_single_client(factory):
    alice = _Conn(factory)
    _hello(alice, "alice", "movie-night")

    incoming = alice.drain()
    # Server replies with a Hello (echo of version + motd) and a List
    # describing the current room state.
    types_seen = {k for m in incoming for k in m.keys()}
    assert "Hello" in types_seen
    # alice should now be visible in the room manager
    assert alice.protocol._logged is True
    assert alice.protocol._watcher is not None
    assert alice.protocol._watcher.getRoom().getName() == "movie-night"


def test_chat_message_is_broadcast_to_roommate(factory):
    alice = _Conn(factory)
    bob = _Conn(factory)
    _hello(alice, "alice", "movie-night")
    _hello(bob, "bob", "movie-night")
    # Clear handshake noise — we only care what arrives after the chat.
    alice.drain()
    bob.drain()

    alice.send({"Chat": "hello bob"})

    bob_messages = bob.drain()
    chats = _messages_of_type(bob_messages, "Chat")
    assert any(c.get("message") == "hello bob" and c.get("username") == "alice"
               for c in chats), bob_messages


def test_ready_state_propagates_to_roommate(factory):
    alice = _Conn(factory)
    bob = _Conn(factory)
    _hello(alice, "alice", "movie-night")
    _hello(bob, "bob", "movie-night")
    alice.drain()
    bob.drain()

    alice.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": True}}})

    bob_messages = bob.drain()
    sets = _messages_of_type(bob_messages, "Set")
    ready_changes = [s["ready"] for s in sets if "ready" in s]
    assert any(r.get("isReady") is True and r.get("username") == "alice"
               for r in ready_changes), bob_messages


def test_state_with_seek_propagates_position_to_roommate(factory):
    alice = _Conn(factory)
    bob = _Conn(factory)
    _hello(alice, "alice", "movie-night")
    _hello(bob, "bob", "movie-night")
    # Both ready up — required for the play unpause gate. Note that
    # the server doesn't enforce all-ready; this is just a real-world
    # setup mirroring the ready-gated client behaviour.
    alice.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": True}}})
    bob.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": True}}})
    alice.drain()
    bob.drain()

    # Alice seeks forward to 500s, playing.
    alice.send({
        "State": {
            "ignoringOnTheFly": {"client": 1},
            "playstate": {
                "position": 500.0,
                "paused": False,
                "doSeek": True,
                "setBy": "alice",
            },
            "ping": {
                "clientLatencyCalculation": time.time(),
                "clientRtt": 0.0,
            },
        }
    })

    bob_messages = bob.drain()
    state_msgs = _messages_of_type(bob_messages, "State")
    assert state_msgs, f"bob got nothing: {bob_messages}"
    # The forwarded State must carry the new position. The server may
    # rebroadcast multiple State messages (initial seek + periodic);
    # any one mentioning position ~500 is enough.
    saw_seek = False
    for s in state_msgs:
        playstate = s.get("playstate") or {}
        pos = playstate.get("position")
        if pos is not None and abs(pos - 500.0) < 1.0:
            saw_seek = True
            break
    assert saw_seek, state_msgs


def test_separate_rooms_do_not_see_each_other(factory):
    alice = _Conn(factory)
    bob = _Conn(factory)
    _hello(alice, "alice", "movie-night")
    _hello(bob, "bob", "different-room")
    alice.drain()
    bob.drain()

    alice.send({"Chat": "private to my own room"})

    # Bob is in a different room — must receive nothing chat-related.
    assert not _messages_of_type(bob.drain(), "Chat")
