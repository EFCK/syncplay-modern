"""Video widget hosting libvlc's render surface.

Phase 3 placeholder. Implementation notes:
- Must set Qt.WA_OpaquePaintEvent, Qt.WA_NativeWindow, Qt.WA_DontCreateNativeAncestors
- paintEvent() must be empty (no super call) — libvlc owns the pixels
- Native window handle obtained from widget.winId() and passed to:
    set_hwnd()    on Windows
    set_xwindow() on X11 (XWayland forced via QT_QPA_PLATFORM=xcb in ui/__init__.py)
    set_nsobject() on macOS
"""
