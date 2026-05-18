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
from PySide6 import QtCore, QtWidgets

from syncplay.ui.modern.chatPanel import ChatPanel
from syncplay.ui.modern.errorsPanel import ErrorsPanel
from syncplay.ui.modern.events import (
    ChatMessage,
    ErrorEvent,
    ErrorSeverity,
    RoomSnapshot,
    SyncEvent,
)
from syncplay.ui.modern.roomPanel import RoomPanel
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
