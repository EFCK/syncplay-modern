"""Tests for the Wayland → xcb platform-override helper.

The helper lives at the top of ``syncplay/ui/__init__.py`` and runs
at import time. Existing behavior on the dev box (GNOME/Plasma/Sway)
was correct only because those compositors leave QT_QPA_PLATFORM
unset, so the historical ``setdefault("xcb")`` quietly took effect.
Hyprland users typically export ``QT_QPA_PLATFORM=wayland`` (it's in
most setup guides), and ``setdefault`` no-ops in that case — libvlc
then can't bind ``set_xwindow`` to a Wayland surface and the video
pops out into its own window.

These tests pin the override matrix without depending on Qt itself.
"""

from __future__ import annotations

from syncplay.ui import _decide_qt_platform_override


def test_overrides_when_wayland_session_and_qt_set_to_wayland():
    """Hyprland-style env: WAYLAND_DISPLAY set, user has exported
    QT_QPA_PLATFORM=wayland. We must override to xcb."""
    env = {
        "XDG_SESSION_TYPE": "wayland",
        "WAYLAND_DISPLAY": "wayland-1",
        "DISPLAY": ":1",
        "QT_QPA_PLATFORM": "wayland",
        "XDG_CURRENT_DESKTOP": "Hyprland",
    }

    result = _decide_qt_platform_override(env)

    assert result is not None
    value, reason = result
    assert value == "xcb"
    assert "Wayland" in reason


def test_overrides_when_wayland_display_set_but_session_type_missing():
    """Some Hyprland configs launched from TTY don't set
    XDG_SESSION_TYPE. WAYLAND_DISPLAY alone must still trip the
    detection."""
    env = {
        "WAYLAND_DISPLAY": "wayland-0",
        "DISPLAY": ":0",
        # QT_QPA_PLATFORM left unset — Qt would pick wayland by default.
    }

    result = _decide_qt_platform_override(env)

    assert result is not None
    assert result[0] == "xcb"


def test_overrides_when_qt_platform_is_wayland_xcb_fallback_list():
    """QT_QPA_PLATFORM=wayland;xcb is the recommended Hyprland config
    for Qt apps that gracefully fall back. Qt still tries wayland
    first when it's available, which is what we need to prevent."""
    env = {
        "XDG_SESSION_TYPE": "wayland",
        "WAYLAND_DISPLAY": "wayland-1",
        "DISPLAY": ":1",
        "QT_QPA_PLATFORM": "wayland;xcb",
    }

    result = _decide_qt_platform_override(env)

    assert result is not None
    assert result[0] == "xcb"


def test_no_override_when_qt_platform_already_xcb():
    """User already on xcb — nothing to do, and we don't want to
    print a spurious notice."""
    env = {
        "XDG_SESSION_TYPE": "wayland",
        "WAYLAND_DISPLAY": "wayland-1",
        "DISPLAY": ":1",
        "QT_QPA_PLATFORM": "xcb",
    }

    assert _decide_qt_platform_override(env) is None


def test_no_override_on_pure_x11_session():
    """Plain X11 (Xorg) sessions: WAYLAND_DISPLAY unset,
    XDG_SESSION_TYPE=x11. No override needed; Qt defaults to xcb
    already."""
    env = {
        "XDG_SESSION_TYPE": "x11",
        "DISPLAY": ":0",
    }

    assert _decide_qt_platform_override(env) is None


def test_no_override_when_escape_hatch_is_set():
    """SYNCPLAY_RESPECT_QT_PLATFORM=1 lets advanced users (libvlc 4
    nightlies with the wl_surface setter, etc.) keep their chosen
    platform even on Wayland."""
    env = {
        "SYNCPLAY_RESPECT_QT_PLATFORM": "1",
        "XDG_SESSION_TYPE": "wayland",
        "WAYLAND_DISPLAY": "wayland-1",
        "DISPLAY": ":1",
        "QT_QPA_PLATFORM": "wayland",
    }

    assert _decide_qt_platform_override(env) is None


def test_no_override_when_xwayland_unavailable():
    """Forcing xcb without an X server (DISPLAY unset) leaves Qt
    unable to start at all. Bail and let the user see the native
    failure mode instead of making it worse."""
    env = {
        "XDG_SESSION_TYPE": "wayland",
        "WAYLAND_DISPLAY": "wayland-1",
        # DISPLAY deliberately omitted — no XWayland running.
        "QT_QPA_PLATFORM": "wayland",
    }

    assert _decide_qt_platform_override(env) is None


def test_no_override_on_pure_windows_or_mac_envs():
    """Sanity: an env that looks like Windows/macOS (no Wayland
    markers, no XDG_SESSION_TYPE) leaves QT_QPA_PLATFORM alone."""
    env = {}  # empty environ — most-restrictive case.

    assert _decide_qt_platform_override(env) is None
