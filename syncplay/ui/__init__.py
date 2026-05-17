import os

from syncplay.utils import isWindowsConsole

os.environ.setdefault("QT_PREFERRED_BINDING", "PySide6")

# Force XWayland on Linux Wayland sessions: libvlc cannot draw into a
# Wayland surface in v1. Must run before QApplication() is constructed.
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

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
