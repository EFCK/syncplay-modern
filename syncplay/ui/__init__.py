import os
import sys

from syncplay.utils import isWindowsConsole

os.environ.setdefault("QT_PREFERRED_BINDING", "PySide6")


def _decide_qt_platform_override(env) -> "tuple[str, str] | None":
    """Decide whether we need to force Qt onto the xcb plugin.

    libvlc 3.x + python-vlc only knows ``set_xwindow`` for Linux
    embedding — it has no Wayland ``wl_surface`` setter. If Qt picks
    the ``wayland`` plugin then ``winId()`` returns a Wayland surface
    pointer that ``set_xwindow`` cannot bind to, so libvlc bails out
    and spawns its own top-level window. The user sees the video pop
    out onto a separate window (typically on another monitor) instead
    of rendering into our embedded panel.

    We therefore force ``QT_QPA_PLATFORM=xcb`` whenever we detect a
    Wayland session AND XWayland is available (``DISPLAY`` set). The
    previous logic used ``setdefault`` which silently no-oped on
    Hyprland users who export ``QT_QPA_PLATFORM=wayland`` globally —
    a common setting recommended by Hyprland guides for native-feel
    Qt apps. Until libvlc 4's output-callbacks API lands in
    python-vlc (see docs/superpowers/specs/2026-05-17-wayland-libvlc-spike.md)
    that override is the only way to keep the embed intact.

    Returns ``(value, reason)`` when an override is needed, or
    ``None`` to leave the env alone. Split out for unit tests so we
    can exercise every branch without monkey-patching os.environ at
    import time.
    """
    if env.get("SYNCPLAY_RESPECT_QT_PLATFORM"):
        # Escape hatch for users running a custom libvlc build (e.g.
        # libvlc 4 nightly with the wl_surface setter) where forcing
        # xcb would actually regress them.
        return None

    on_wayland = (
        env.get("XDG_SESSION_TYPE") == "wayland"
        or bool(env.get("WAYLAND_DISPLAY"))
    )
    if not on_wayland:
        return None

    # Forcing xcb without an X server (XWayland not running) would
    # leave Qt unable to start at all. Bail in that case and let the
    # user see whatever native Qt error gets raised — better than
    # making it worse.
    if not env.get("DISPLAY"):
        return None

    current = (env.get("QT_QPA_PLATFORM") or "").strip()
    if current == "xcb":
        # Already what we want; no notice needed.
        return None

    reason = (
        "Wayland session detected; forcing Qt to xcb so libvlc can embed "
        "video via set_xwindow (Wayland surfaces are not supported by "
        "libvlc 3.x / python-vlc). Set SYNCPLAY_RESPECT_QT_PLATFORM=1 to "
        "disable."
    )
    return ("xcb", reason)


_override = _decide_qt_platform_override(os.environ)
if _override is not None:
    _value, _reason = _override
    os.environ["QT_QPA_PLATFORM"] = _value
    # stderr so the notice is visible alongside any libvlc warnings,
    # but doesn't pollute the protocol log on stdout.
    print(f"[syncplay-modern] {_reason}", file=sys.stderr)

# Set the desktop file name before QApplication construction so Qt's
# platform plugin uses it at the first D-Bus contact with
# xdg-desktop-portal. Calling QGuiApplication.setDesktopFileName()
# *after* construction produces a redundant RegisterApplication call
# that the portal rejects with "Connection already associated with an
# application ID" (harmless but noisy).
os.environ.setdefault("QT_QPA_DESKTOP_FILE_NAME", "syncplay")

GraphicalUI = None
if not isWindowsConsole():
    try:
        from syncplay.ui.modern.mainWindow import MainWindow as GraphicalUI
    except (ImportError, AttributeError):
        GraphicalUI = None

from syncplay.ui.consoleUI import ConsoleUI


def getUi(graphical=True, passedBar=None):
    if graphical and GraphicalUI is not None and not isWindowsConsole():
        return GraphicalUI(passedBar=passedBar)
    ui = ConsoleUI()
    ui.setDaemon(True)
    ui.start()
    return ui
