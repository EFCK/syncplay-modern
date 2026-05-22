"""pytest-qt coverage for the modern UI widgets.

These tests exercise the widgets that ride on top of a real
`QApplication` — the Qt-free state classes (`MessageRouter`,
`RoomState`) already have their own modules. Run headless via
`QT_QPA_PLATFORM=offscreen` (set by the CI workflow and by the
pyproject test config — see `tests/conftest.py`).
"""

from __future__ import annotations

import time

import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from syncplay.ui.modern.chatPanel import ChatPanel
from syncplay.ui.modern.errorsPanel import ErrorsPanel
from syncplay.ui.modern.mainWindow import SeekCoalescer
from syncplay.ui.modern.events import (
    ChatMessage,
    ErrorEvent,
    ErrorSeverity,
    RoomSnapshot,
    SyncEvent,
)
from syncplay.ui.modern.roomPanel import RoomPanel
from syncplay.ui.modern.settingsPanel import PlaybackDialog
from syncplay.ui.modern.sidebarTabs import SidebarTabs
from syncplay.ui.modern.toast import Toast


# ---------------------------------------------------------------------------
# Toast
# ---------------------------------------------------------------------------


def _make_toast(qtbot):
    # Toast requires a parent QWidget for QObject ownership (it's a
    # top-level Qt.Tool window, not laid out under host). qtbot.addWidget
    # stores only a *weakref* — so if `host` falls out of scope when
    # this helper returns, Python GC collects it, Qt cascades the
    # delete to Toast, and the next .show_message() hits a dead C++
    # object. Stash host on the toast so the Python ref persists for
    # the test's lifetime.
    host = QtWidgets.QWidget()
    qtbot.addWidget(host)
    toast = Toast(host)
    toast._kept_alive_host = host
    return toast


def test_toast_show_message_makes_widget_visible(qtbot):
    toast = _make_toast(qtbot)

    assert not toast.isVisible()
    toast.show_message("hello")
    assert toast.isVisible()
    assert len(toast._labels) == 1


def test_toast_empty_text_is_a_noop(qtbot):
    toast = _make_toast(qtbot)

    toast.show_message("   ")
    toast.show_message("")

    assert not toast.isVisible()
    assert len(toast._labels) == 0


def test_toast_caps_at_max_stack_and_evicts_oldest(qtbot):
    toast = _make_toast(qtbot)

    # MAX_STACK=3 — pushing 4 messages drops the first one. Use a
    # large duration so the timer doesn't fire mid-test.
    for i in range(4):
        toast.show_message(f"msg {i}", duration=10_000)

    assert len(toast._labels) == 3
    visible_texts = {
        bubble.findChild(QtWidgets.QLabel).text() for bubble in toast._labels
    }
    assert "msg 0" not in visible_texts  # oldest evicted
    assert "msg 3" in visible_texts


def test_toast_expire_hides_when_last_label_goes(qtbot):
    toast = _make_toast(qtbot)

    toast.show_message("brief", duration=50)
    assert toast.isVisible()

    # Wait for the QTimer.singleShot to fire and the bubble to be
    # cleaned up. pytest-qt's waitUntil polls the predicate.
    qtbot.waitUntil(lambda: not toast.isVisible(), timeout=2000)
    assert len(toast._labels) == 0


def test_toast_expire_survives_dead_qframe(qtbot):
    """Reproduces the runtime crash seen during rapid arrow-key seeks.

    Each seek-flush emits a `Seek ±Xs` toast. Held arrows produce a
    burst of toasts; MAX_STACK eviction calls deleteLater on the
    oldest, but its original duration QTimer.singleShot is still
    scheduled. When that timer fires later, _expire(label) runs on
    a bubble whose C++ side has already been destroyed, and
    `self._labels.remove(label)` raises:

        RuntimeError: libshiboken: Internal C++ object
        (PySide6.QtWidgets.QFrame) already deleted.

    Reproducing the exact path: the evicted bubble has been popleft'd
    from _labels already, so list.remove can't find it via identity
    checks. It then falls back to `==` comparison against each item
    still in _labels — and that __eq__ call touches the dead
    wrapper's C++ side, raising RuntimeError.
    """
    import shiboken6

    toast = _make_toast(qtbot)

    # The bubble that will be "evicted" — not currently in _labels.
    evicted = QtWidgets.QFrame(toast)

    # A couple of live bubbles in _labels so list.remove has to
    # actually iterate and call __eq__ on `evicted` against them.
    alive_a = QtWidgets.QFrame(toast)
    alive_b = QtWidgets.QFrame(toast)
    toast._labels.append(alive_a)
    toast._labels.append(alive_b)

    # Forcibly destroy the evicted bubble's C++ side.
    shiboken6.delete(evicted)
    assert shiboken6.isValid(evicted) is False

    # Must not raise. Pre-fix, list.remove's traversal called __eq__
    # on the dead `evicted` wrapper and shiboken raised RuntimeError.
    toast._expire(evicted)

    # The live bubbles must still be there afterwards — _expire on a
    # stranger doesn't drop unrelated entries.
    assert alive_a in toast._labels
    assert alive_b in toast._labels


# ---------------------------------------------------------------------------
# SidebarTabs unread-badge
# ---------------------------------------------------------------------------


def _build_sidebar(qtbot):
    panels = [QtWidgets.QWidget() for _ in range(4)]
    for p in panels:
        qtbot.addWidget(p)
    tabs = SidebarTabs(*panels)
    qtbot.addWidget(tabs)
    return tabs


def test_sidebar_errors_label_starts_without_badge(qtbot):
    tabs = _build_sidebar(qtbot)
    assert tabs.tabText(SidebarTabs.ERRORS_INDEX) == "Errors"


def test_sidebar_note_error_bumps_unread_when_not_on_errors_tab(qtbot):
    tabs = _build_sidebar(qtbot)
    tabs.setCurrentIndex(SidebarTabs.CHAT_INDEX)
    tabs.note_error()
    tabs.note_error()
    assert "●2" in tabs.tabText(SidebarTabs.ERRORS_INDEX)


def test_sidebar_note_error_is_noop_while_on_errors_tab(qtbot):
    tabs = _build_sidebar(qtbot)
    tabs.setCurrentIndex(SidebarTabs.ERRORS_INDEX)
    tabs.note_error()
    assert tabs.tabText(SidebarTabs.ERRORS_INDEX) == "Errors"


def test_sidebar_switching_to_errors_clears_badge(qtbot):
    tabs = _build_sidebar(qtbot)
    tabs.setCurrentIndex(SidebarTabs.CHAT_INDEX)
    tabs.note_error()
    assert "●1" in tabs.tabText(SidebarTabs.ERRORS_INDEX)

    tabs.setCurrentIndex(SidebarTabs.ERRORS_INDEX)
    assert tabs.tabText(SidebarTabs.ERRORS_INDEX) == "Errors"


def test_sidebar_chat_badge_starts_at_zero(qtbot):
    tabs = _build_sidebar(qtbot)
    assert tabs.chat_unread_count() == 0


def test_sidebar_note_chat_bumps_unread_when_not_on_chat_tab(qtbot):
    tabs = _build_sidebar(qtbot)
    tabs.setCurrentIndex(SidebarTabs.ROOM_INDEX)
    tabs.note_chat()
    tabs.note_chat()
    tabs.note_chat()
    assert tabs.chat_unread_count() == 3


def test_sidebar_note_chat_is_noop_while_on_chat_tab(qtbot):
    tabs = _build_sidebar(qtbot)
    tabs.setCurrentIndex(SidebarTabs.CHAT_INDEX)
    tabs.note_chat()
    assert tabs.chat_unread_count() == 0


def test_sidebar_switching_to_chat_clears_badge(qtbot):
    tabs = _build_sidebar(qtbot)
    tabs.setCurrentIndex(SidebarTabs.ROOM_INDEX)
    tabs.note_chat()
    tabs.note_chat()
    assert tabs.chat_unread_count() == 2

    tabs.setCurrentIndex(SidebarTabs.CHAT_INDEX)
    assert tabs.chat_unread_count() == 0


# ---------------------------------------------------------------------------
# ErrorsPanel
# ---------------------------------------------------------------------------


def test_errors_panel_renders_severity_and_message(qtbot):
    panel = ErrorsPanel()
    qtbot.addWidget(panel)

    event = ErrorEvent(
        text="connection refused",
        category="net",
        severity=ErrorSeverity.ERROR,
        timestamp=time.time(),
    )
    panel.render_error(event)

    body = panel._log.toPlainText()
    assert "connection refused" in body
    assert "ERROR" in body
    assert "(net)" in body


def test_errors_panel_clear_button_emits_signal_and_empties_log(qtbot):
    panel = ErrorsPanel()
    qtbot.addWidget(panel)
    panel.render_error(
        ErrorEvent(
            text="boom",
            category="generic",
            severity=ErrorSeverity.WARNING,
            timestamp=time.time(),
        )
    )
    assert panel._log.toPlainText().strip()

    with qtbot.waitSignal(panel.cleared, timeout=500):
        panel._on_clear()

    assert panel._log.toPlainText().strip() == ""


# ---------------------------------------------------------------------------
# ChatPanel
# ---------------------------------------------------------------------------


def test_chat_panel_render_chat_includes_user_and_text(qtbot):
    panel = ChatPanel()
    qtbot.addWidget(panel)

    panel.render_chat(
        ChatMessage(user="alice", text="hello world", is_self=False, timestamp=time.time())
    )

    plain = panel._log.toPlainText()
    assert "alice" in plain
    assert "hello world" in plain


def test_chat_panel_render_sync_splits_multiline_detail(qtbot):
    panel = ChatPanel()
    qtbot.addWidget(panel)

    panel.render_sync(
        SyncEvent(
            kind="paused",
            detail="alice paused\nat 00:01:23",
            timestamp=time.time(),
        )
    )

    plain = panel._log.toPlainText()
    # Both lines must appear; the multi-line splitter put each in its
    # own paragraph (otherwise they'd run together on one gray line).
    assert "alice paused" in plain
    assert "at 00:01:23" in plain


def test_chat_panel_render_error_notice_points_at_errors_tab(qtbot):
    panel = ChatPanel()
    qtbot.addWidget(panel)
    panel.render_error_notice()

    plain = panel._log.toPlainText()
    assert "Errors" in plain
    assert "tab" in plain


def test_chat_panel_emits_submitted_on_enter_and_drops_empty(qtbot):
    panel = ChatPanel()
    qtbot.addWidget(panel)

    received: list[str] = []
    panel.chatSubmitted.connect(received.append)

    panel._input.setText("howdy")
    with qtbot.waitSignal(panel.chatSubmitted, timeout=500):
        QtCore.QMetaObject.invokeMethod(panel._input, "returnPressed")

    panel._input.setText("   ")
    QtCore.QMetaObject.invokeMethod(panel._input, "returnPressed")

    assert received == ["howdy"]


# ---------------------------------------------------------------------------
# RoomPanel — Ready button label (the ready-gated-sync change)
# ---------------------------------------------------------------------------


def _snapshot(is_ready: bool, *, with_file: bool = True) -> RoomSnapshot:
    return RoomSnapshot(
        users=[
            {
                "name": "me",
                "ready": is_ready,
                "filename": "movie.mkv" if with_file else "",
                "is_self": True,
            }
        ],
        room="movie-night",
        current_user="me",
        is_ready=is_ready,
    )


def test_room_panel_ready_label_when_not_ready(qtbot):
    panel = RoomPanel()
    qtbot.addWidget(panel)
    panel.set_snapshot(_snapshot(is_ready=False))
    assert panel._ready_btn.text() == "Ready (join sync)"


def test_room_panel_ready_label_when_ready(qtbot):
    panel = RoomPanel()
    qtbot.addWidget(panel)
    panel.set_snapshot(_snapshot(is_ready=True))
    assert panel._ready_btn.text() == "Not Ready (watch alone)"


def test_room_panel_ready_button_disabled_without_file(qtbot):
    panel = RoomPanel()
    qtbot.addWidget(panel)
    panel.set_snapshot(_snapshot(is_ready=False, with_file=False))
    assert not panel._ready_btn.isEnabled()


def test_room_panel_ready_button_emits_on_click(qtbot):
    panel = RoomPanel()
    qtbot.addWidget(panel)
    panel.set_snapshot(_snapshot(is_ready=False))

    with qtbot.waitSignal(panel.readyToggleRequested, timeout=500):
        panel._ready_btn.click()


# ---------------------------------------------------------------------------
# SeekCoalescer — debounces rapid arrow-key seeks
# ---------------------------------------------------------------------------


class _SeekRecorder:
    """on_flush callback that records the deltas it receives."""

    def __init__(self):
        self.flushes: list[float] = []

    def __call__(self, delta: float) -> None:
        self.flushes.append(delta)


def test_seek_coalescer_buffers_until_settle(qtbot):
    """A single queued delta is not applied immediately — it waits for
    the settle window so consecutive presses can accumulate."""
    rec = _SeekRecorder()
    coalescer = SeekCoalescer(rec, settle_ms=80)
    coalescer.queue(5.0)
    assert rec.flushes == []
    assert coalescer.pending_delta() == 5.0

    # Wait past the settle window for the QTimer to fire.
    qtbot.wait(150)

    assert rec.flushes == [5.0]
    assert coalescer.pending_delta() == 0.0


def test_seek_coalescer_collapses_burst_into_one_flush(qtbot):
    """Ten rapid keypresses should produce one flush with the summed
    delta — the whole point of the coalescer. Without this, libvlc
    would get ten partial set_time calls and the sync state machine
    would see ten doSeek=True broadcasts."""
    rec = _SeekRecorder()
    coalescer = SeekCoalescer(rec, settle_ms=80)
    for _ in range(10):
        coalescer.queue(5.0)
    qtbot.wait(150)

    assert rec.flushes == [50.0]


def test_seek_coalescer_handles_mixed_signs(qtbot):
    """Pressing → → ← → → in quick succession should net +15s, not
    fire five separate seeks."""
    rec = _SeekRecorder()
    coalescer = SeekCoalescer(rec, settle_ms=80)
    for delta in (5.0, 5.0, -5.0, 5.0, 5.0):
        coalescer.queue(delta)
    qtbot.wait(150)

    assert rec.flushes == [15.0]


def test_seek_coalescer_each_new_press_extends_settle_window(qtbot):
    """A press that arrives partway through the settle window restarts
    the timer rather than letting the original window expire — so a
    held-down arrow doesn't get cut off mid-burst."""
    rec = _SeekRecorder()
    coalescer = SeekCoalescer(rec, settle_ms=120)

    coalescer.queue(5.0)
    qtbot.wait(60)  # still mid-window
    coalescer.queue(5.0)
    qtbot.wait(60)  # would have flushed by now had we not extended
    coalescer.queue(5.0)
    # Nothing flushed yet — the timer keeps getting restarted.
    assert rec.flushes == []

    qtbot.wait(200)  # well past the latest start

    assert rec.flushes == [15.0]


# ---------------------------------------------------------------------------
# PlaybackDialog — audio / subtitle track switching
# ---------------------------------------------------------------------------


class _FakePlayer:
    """Stand-in for EmbeddedVlcPlayer for the dialog's purposes."""

    def __init__(self, audio_current: int = -1, sub_current: int = -1,
                 audio_result: int = 0, sub_result: int = 0,
                 subtitle_delay_ms: int = 0):
        self.audio_calls: list[int] = []
        self.subtitle_calls: list[int] = []
        self.subtitle_delay_sets: list[int] = []
        self._audio_current = audio_current
        self._sub_current = sub_current
        self._audio_result = audio_result
        self._sub_result = sub_result
        self._subtitle_delay_ms = int(subtitle_delay_ms)

    def get_audio_tracks(self):
        return [
            {"id": -1, "label": "Disable"},
            {"id": 1, "label": "English"},
            {"id": 2, "label": "Spanish"},
        ]

    def get_subtitle_tracks(self):
        return [
            {"id": -1, "label": "Disable"},
            {"id": 3, "label": "EN subs"},
            {"id": 4, "label": "FR subs"},
        ]

    def get_current_audio_track(self):
        return self._audio_current

    def get_current_subtitle_track(self):
        return self._sub_current

    def set_audio_track(self, tid):
        self.audio_calls.append(tid)
        return self._audio_result

    def set_subtitle_track(self, tid):
        self.subtitle_calls.append(tid)
        return self._sub_result

    def set_subtitle_delay_ms(self, ms):
        self.subtitle_delay_sets.append(int(ms))
        self._subtitle_delay_ms = int(ms)

    def get_subtitle_delay_ms(self):
        return int(self._subtitle_delay_ms)


def _make_playback_dialog(qtbot, player, parent=None):
    if parent is None:
        parent = QtWidgets.QWidget()
        qtbot.addWidget(parent)
    dialog = PlaybackDialog(
        parent=parent,
        config={},
        fileinfo=None,
        get_player=lambda: player,
        on_persist=lambda k, v: None,
    )
    dialog._kept_alive_parent = parent
    qtbot.addWidget(dialog)
    return dialog


def test_playback_dialog_calls_set_audio_track_on_combo_change(qtbot):
    """Sanity: the basic wiring works. Picking 'Spanish' (id=2) calls
    set_audio_track(2) on the player."""
    player = _FakePlayer(audio_current=1)  # English active
    dialog = _make_playback_dialog(qtbot, player)

    # English (id=1) is already selected; pick Spanish (id=2) at combo index 2
    dialog._audio_combo.setCurrentIndex(2)

    assert player.audio_calls == [2]


def test_playback_dialog_preselects_current_audio_track(qtbot):
    """The combo should open showing the track libvlc is actually
    playing — not 'Disable' at index 0. The 'looks broken' symptom
    came from users picking what they wanted and seeing no change
    because libvlc had auto-selected it already."""
    player = _FakePlayer(audio_current=2)  # Spanish active
    dialog = _make_playback_dialog(qtbot, player)

    # Combo should pre-select index 2 (Spanish, id=2), not index 0.
    assert dialog._audio_combo.currentData() == 2
    # And pre-selection must not have triggered a redundant
    # set_audio_track call.
    assert player.audio_calls == []


def test_playback_dialog_preselects_current_subtitle_track(qtbot):
    player = _FakePlayer(sub_current=4)
    dialog = _make_playback_dialog(qtbot, player)

    assert dialog._sub_combo.currentData() == 4
    assert player.subtitle_calls == []


def test_playback_dialog_surfaces_libvlc_rejection(qtbot):
    """libvlc's set_audio_track returns -1 if it rejects the ID (stale
    track after a re-parse, etc). Without surfacing the return value
    the dialog showed 'Audio: English' as if it worked — masking real
    failures."""
    player = _FakePlayer(audio_current=1, audio_result=-1)  # rejection
    dialog = _make_playback_dialog(qtbot, player)

    toasts = []
    dialog._notify_parent = toasts.append

    dialog._audio_combo.setCurrentIndex(2)  # pick Spanish

    assert player.audio_calls == [2]
    assert toasts == ["Audio change rejected by libvlc (id=2)"]


def test_playback_dialog_spin_reflects_live_subtitle_delay(qtbot):
    """The dialog must read the live player delay on open, not the
    config snapshot. Pressing H/G before opening the dialog adjusts
    libvlc directly; if the dialog still showed config (0), users
    saw a value that didn't match playback."""
    player = _FakePlayer(subtitle_delay_ms=150)
    # Config snapshot is deliberately stale (0) — we want to prove
    # the dialog prefers the player value.
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    persisted: list[tuple[str, object]] = []
    dialog = PlaybackDialog(
        parent=parent,
        config={"subtitleDelayDefaultMs": 0},
        fileinfo=None,
        get_player=lambda: player,
        on_persist=lambda k, v: persisted.append((k, v)),
    )
    dialog._kept_alive_parent = parent
    qtbot.addWidget(dialog)

    assert dialog._sub_delay_spin.value() == 150
    # Initial population must not bounce back through set/persist.
    assert player.subtitle_delay_sets == []
    assert persisted == []


def test_playback_dialog_falls_back_to_config_when_no_player(qtbot):
    """When the player is unavailable (no file open yet) the dialog
    has no live value to read, so it must fall back to the config
    snapshot instead of showing a hardcoded 0."""
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    dialog = PlaybackDialog(
        parent=parent,
        config={"subtitleDelayDefaultMs": 75},
        fileinfo=None,
        get_player=lambda: None,
        on_persist=lambda k, v: None,
    )
    dialog._kept_alive_parent = parent
    qtbot.addWidget(dialog)

    assert dialog._sub_delay_spin.value() == 75


def test_playback_dialog_refresh_subtitle_delay_pulls_from_player(qtbot):
    """After H/G fires outside the dialog, MainWindow calls
    refresh_subtitle_delay so the spinbox catches up. The refresh
    must not re-persist or re-call set_subtitle_delay_ms — the
    keyboard path already did both."""
    player = _FakePlayer(subtitle_delay_ms=0)
    persisted: list[tuple[str, object]] = []
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    dialog = PlaybackDialog(
        parent=parent,
        config={},
        fileinfo=None,
        get_player=lambda: player,
        on_persist=lambda k, v: persisted.append((k, v)),
    )
    dialog._kept_alive_parent = parent
    qtbot.addWidget(dialog)

    # Simulate the keyboard path moving libvlc independently.
    player._subtitle_delay_ms = 200

    dialog.refresh_subtitle_delay()

    assert dialog._sub_delay_spin.value() == 200
    # Pulling state in must not push state back out.
    assert player.subtitle_delay_sets == []
    assert persisted == []


def test_playback_dialog_h_shortcut_steps_spin_and_player(qtbot):
    """H/G shortcuts are dead while the modal dialog has focus
    (MainWindow's WindowShortcut is suppressed). The dialog re-binds
    them locally; each press must step the spinbox AND call into the
    player so the displayed value matches libvlc."""
    player = _FakePlayer(subtitle_delay_ms=0)
    persisted: list[tuple[str, object]] = []
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    dialog = PlaybackDialog(
        parent=parent,
        config={},
        fileinfo=None,
        get_player=lambda: player,
        on_persist=lambda k, v: persisted.append((k, v)),
    )
    dialog._kept_alive_parent = parent
    qtbot.addWidget(dialog)

    # Find the H shortcut and activate it (QTest keyClicks needs a
    # focused widget that accepts the key — going through .activated
    # is the same code path with less Qt-event plumbing).
    h_shortcut = next(
        s for s in dialog.findChildren(QtGui.QShortcut)
        if s.key().toString() == "H"
    )
    h_shortcut.activated.emit()

    assert dialog._sub_delay_spin.value() == 50
    assert player.subtitle_delay_sets == [50]
    assert persisted == [("subtitleDelayDefaultMs", 50)]


def test_playback_dialog_disables_combo_when_no_tracks(qtbot):
    """Files without audio (or subtitles) should disable the combo
    so users don't try to interact with a dead control."""
    class _EmptyPlayer(_FakePlayer):
        def get_audio_tracks(self):
            return []
        def get_subtitle_tracks(self):
            return []

    dialog = _make_playback_dialog(qtbot, _EmptyPlayer())

    assert not dialog._audio_combo.isEnabled()
    assert not dialog._sub_combo.isEnabled()


def test_seek_coalescer_separate_bursts_each_flush(qtbot):
    """A second burst after the first one has settled produces a
    second independent flush — coalescing is per-burst, not global."""
    rec = _SeekRecorder()
    coalescer = SeekCoalescer(rec, settle_ms=80)

    coalescer.queue(5.0)
    coalescer.queue(5.0)
    qtbot.wait(150)
    assert rec.flushes == [10.0]

    coalescer.queue(-5.0)
    qtbot.wait(150)
    assert rec.flushes == [10.0, -5.0]
