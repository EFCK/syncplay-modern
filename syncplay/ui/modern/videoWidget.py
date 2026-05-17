"""Video widget hosting libvlc's render surface.

The widget is configured so libvlc owns the pixels: we ask for a native
window handle (`WA_NativeWindow`) and tell Qt not to draw over it
(`WA_OpaquePaintEvent` + empty paintEvent for the libvlc-active state).
Without those flags libvlc's output gets blanked by Qt repaints on resize
or splitter drag.

On Linux we force `QT_QPA_PLATFORM=xcb` from `syncplay/ui/__init__.py` so
`winId()` returns an X11 window ID that libvlc's `set_xwindow` understands.
"""

from __future__ import annotations

import sys

from PySide6 import QtCore, QtGui, QtWidgets


class VideoWidget(QtWidgets.QWidget):

    fileDropped = QtCore.Signal(str)  # absolute path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Critical: libvlc draws directly into our native window. Qt must
        # not repaint over it.
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(QtCore.Qt.WA_NativeWindow, True)
        self.setAttribute(QtCore.Qt.WA_DontCreateNativeAncestors, True)

        # Black background when no media is loaded.
        palette = self.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(0, 0, 0))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.setMinimumSize(360, 240)
        self.setAcceptDrops(True)
        # Accept focus on click and tab — required for keyboard shortcuts
        # scoped to this widget (Phase 5 shortcut routing).
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self._placeholder_text = "Drop a file here or use File → Open…"
        # One-shot flag: paint black for the *next* paint event even when
        # libvlc owns the surface. Used after the chat sidebar is hidden
        # so the area the video just grew into doesn't show stale chat
        # pixels until libvlc draws its next frame.
        self._black_once = False

    def paintEvent(self, event):
        if self._placeholder_text:
            painter = QtGui.QPainter(self)
            painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0))
            painter.setPen(QtGui.QColor(170, 170, 170))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, self._placeholder_text)
            painter.end()
            return
        if self._black_once:
            self._black_once = False
            painter = QtGui.QPainter(self)
            painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0))
            painter.end()
            return
        # libvlc owns the pixels — do not draw.

    def request_black_repaint(self) -> None:
        """Force one black-fill paint on the next event tick.

        libvlc draws into our native window asynchronously, so when the
        widget grows (chat hidden) the new area shows whatever was there
        before until libvlc catches up. This paints it black once so the
        gap isn't filled with stale UI pixels.
        """
        self._black_once = True
        self.update()

    def clear_placeholder(self) -> None:
        self._placeholder_text = ""
        self.update()

    def attach_player(self, media_player) -> None:
        """Hand our native window handle to libvlc."""
        winid = int(self.winId())
        if sys.platform.startswith("win"):
            media_player.set_hwnd(winid)
        elif sys.platform == "darwin":
            media_player.set_nsobject(winid)
        else:
            media_player.set_xwindow(winid)

    # --- Drag and drop ---------------------------------------------------

    def mousePressEvent(self, event):
        # Click anywhere on the video → take focus so keyboard shortcuts
        # work without the user having to tab.
        self.setFocus(QtCore.Qt.MouseFocusReason)
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.fileDropped.emit(url.toLocalFile())
                event.acceptProposedAction()
                return
