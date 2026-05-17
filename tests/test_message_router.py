"""Unit tests for MessageRouter — Qt-free, no QApplication needed."""

from __future__ import annotations

from syncplay.ui.modern.events import (
    ChatMessage,
    ConnectionState,
    ConnectionStateKind,
    ErrorEvent,
    ErrorSeverity,
    PlaylistAppended,
    PlaylistChanged,
    PlaylistIndexChanged,
    SyncEvent,
    SyncEventKind,
)
from syncplay.ui.modern.messageRouter import MessageRouter

from tests.conftest import collect_events


def test_show_chat_message_emits_chat_message():
    router = MessageRouter()
    events = collect_events(router)

    router.showChatMessage("alice", "hello")

    assert len(events) == 1
    evt = events[0]
    assert isinstance(evt, ChatMessage)
    assert evt.user == "alice"
    assert evt.text == "hello"
    assert evt.is_self is False


def test_show_message_swallows_loaded_file():
    router = MessageRouter()
    events = collect_events(router)

    router.showMessage("alice loaded file: foo.mkv")

    assert events == []


def test_show_message_swallows_ready_lines():
    router = MessageRouter()
    events = collect_events(router)

    router.showMessage("alice is ready")
    router.showMessage("alice is not ready")
    router.showMessage("alice no longer ready")

    assert events == []


def test_show_message_emits_connection_state_on_connect():
    router = MessageRouter()
    events = collect_events(router)

    router.showMessage("successfully connected to server")

    # The "successfully connected" substring is also in the swallow list,
    # so we get the ConnectionState but no follow-up SyncEvent.
    assert len(events) == 1
    evt = events[0]
    assert isinstance(evt, ConnectionState)
    assert evt.state == ConnectionStateKind.CONNECTED


def test_show_message_emits_connection_state_on_reconnect():
    router = MessageRouter()
    events = collect_events(router)

    router.showMessage("Connection with server lost, attempting to reconnect")

    states = [e for e in events if isinstance(e, ConnectionState)]
    assert any(s.state == ConnectionStateKind.RECONNECTING for s in states)


def test_show_message_generic_emits_sync_event():
    router = MessageRouter()
    events = collect_events(router)

    router.showMessage("alice paused at 0:14:22")

    assert len(events) == 1
    evt = events[0]
    assert isinstance(evt, SyncEvent)
    assert evt.kind == SyncEventKind.GENERIC
    assert "paused" in evt.detail


def test_show_error_message_emits_error_event():
    router = MessageRouter()
    events = collect_events(router)

    router.showErrorMessage("something broke")

    assert len(events) == 1
    evt = events[0]
    assert isinstance(evt, ErrorEvent)
    assert evt.severity == ErrorSeverity.ERROR
    assert evt.text == "something broke"


def test_show_error_message_critical_severity():
    router = MessageRouter()
    events = collect_events(router)

    router.showErrorMessage("kaboom", criticalerror=True)

    assert events[0].severity == ErrorSeverity.CRITICAL


def test_show_error_message_disconnect_emits_connection_state():
    router = MessageRouter()
    events = collect_events(router)

    router.showErrorMessage("connection with server lost")

    states = [e for e in events if isinstance(e, ConnectionState)]
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(states) == 1
    assert states[0].state == ConnectionStateKind.DISCONNECTED
    # Error still surfaces alongside the disconnect signal.
    assert len(errors) == 1


def test_show_osd_message_is_suppressed():
    router = MessageRouter()
    events = collect_events(router)

    router.showOSDMessage("anything")

    assert events == []


def test_add_file_to_playlist_emits_appended():
    router = MessageRouter()
    events = collect_events(router)

    router.addFileToPlaylist("a.mkv")

    assert len(events) == 1
    assert isinstance(events[0], PlaylistAppended)
    assert events[0].filename == "a.mkv"


def test_set_playlist_emits_changed():
    router = MessageRouter()
    events = collect_events(router)

    router.setPlaylist(["a.mkv", "b.mkv"], "a.mkv")

    assert len(events) == 1
    evt = events[0]
    assert isinstance(evt, PlaylistChanged)
    assert evt.files == ["a.mkv", "b.mkv"]
    assert evt.current_filename == "a.mkv"


def test_set_playlist_with_none_index_filename():
    router = MessageRouter()
    events = collect_events(router)

    router.setPlaylist(["a.mkv"])

    evt = events[0]
    assert isinstance(evt, PlaylistChanged)
    assert evt.current_filename is None


def test_set_playlist_index_filename_emits_index_changed():
    router = MessageRouter()
    events = collect_events(router)

    router.setPlaylistIndexFilename("b.mkv")

    assert len(events) == 1
    assert isinstance(events[0], PlaylistIndexChanged)
    assert events[0].filename == "b.mkv"
