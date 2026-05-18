"""Non-intrusive corner toast — replacement for VLC OSD overlays.

Receives short status messages from the player adapter (mute, volume,
delay, speed) and optionally chat lines when `chatOnVideoEnabled` is on,
renders them stacked top-right of the video area, and auto-dismisses
each after its duration.

Implemented as a top-level frameless tool window rather than a child
widget of MainWindow. The video widget is `WA_NativeWindow` — a child
HWND — and on Windows sibling Qt widgets cannot reliably draw over a
native child HWND (the OS treats the native child as always-on-top of
non-native siblings, the parent's paint region gets clipped, and the
video frame tears, going half-black where the toast geometry sits).

A separate top-level HWND for the toast sidesteps the whole layering
problem: the WM stacks it above the MainWindow (and therefore above
the video HWND) cleanly. Positioned in screen coordinates by
MainWindow's resize / fullscreen / chat-toggle paths.
"""

from __future__ import annotations

from collections import deque
from typing import Deque

from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid as _qt_isValid


class Toast(QtWidgets.QFrame):

    MAX_STACK = 3
    DEFAULT_DURATION_MS = 2000

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(
            parent,
            QtCore.Qt.Tool
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowTransparentForInput
            | QtCore.Qt.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("toastStack")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        # Padding lives on the wrapping QFrame's layout margins, not as
        # CSS padding on the QLabel: QLabel's sizeHint() under-reports
        # height for word-wrapped text when CSS padding is set, so
        # multi-line toasts got clipped vertically. With the bubble as
        # a QFrame containing a plain QLabel, Qt's natural sizing
        # works correctly.
        self.setStyleSheet(
            "QFrame#toastStack { background: transparent; }"
            "QFrame#toastBubble { "
            "  background: rgba(22, 22, 22, 220); border-radius: 10px; "
            "}"
            "QLabel#toastText { "
            "  color: #f4f4f4; font-size: 17px; background: transparent; "
            "}"
        )
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)  # push labels to the top
        self._labels: Deque[QtWidgets.QFrame] = deque()
        self.hide()

    def show_message(self, text: str, duration: int | None = None) -> None:
        text = str(text).strip()
        if not text:
            return
        if duration is None or duration <= 0:
            duration = self.DEFAULT_DURATION_MS

        bubble = QtWidgets.QFrame(self)
        bubble.setObjectName("toastBubble")
        bubble.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        bubble.setMinimumWidth(220)
        bubble.setMaximumWidth(460)

        label = QtWidgets.QLabel(text, bubble)
        label.setObjectName("toastText")
        label.setTextFormat(QtCore.Qt.PlainText)
        label.setWordWrap(True)
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        inner = QtWidgets.QHBoxLayout(bubble)
        inner.setContentsMargins(26, 18, 26, 18)
        inner.addWidget(label)

        # Insert above the stretch (stretch is the last item).
        self._layout.insertWidget(self._layout.count() - 1, bubble, 0, QtCore.Qt.AlignRight)
        self._labels.append(bubble)

        # Cap stack depth — drop the oldest.
        while len(self._labels) > self.MAX_STACK:
            oldest = self._labels.popleft()
            self._remove_label(oldest)

        QtCore.QTimer.singleShot(duration, lambda lbl=bubble: self._expire(lbl))

        if not self.isVisible():
            self.show()
            self.raise_()

    def reposition(self, video_geometry_in_window: QtCore.QRect) -> None:
        """Anchor top-right of the given video-pane rect (in window coords)."""
        inset = 12
        width = 500
        # Cap to the video pane width minus insets so we never overflow.
        width = max(200, min(width, video_geometry_in_window.width() - 2 * inset))
        # Generous height so stacked labels fit; layout aligns top so unused
        # vertical space is just transparent.
        height = max(180, video_geometry_in_window.height() - 2 * inset)
        x = video_geometry_in_window.x() + video_geometry_in_window.width() - width - inset
        y = video_geometry_in_window.y() + inset
        self.setGeometry(x, y, width, height)

    def _expire(self, label: QtWidgets.QFrame) -> None:
        # The bubble's C++ side may already be gone — MAX_STACK
        # eviction calls deleteLater on the oldest bubble, but the
        # original duration timer for that bubble is still scheduled
        # and fires here later. list.remove(label) then traverses
        # _labels and compares `label` (dead) against each remaining
        # item via __eq__, which touches the dead wrapper and raises
        # `RuntimeError: Internal C++ object ... already deleted`.
        # Short-circuit when the C++ side is gone — there's no list
        # entry to drop anyway (eviction already popleft'd it).
        if not _qt_isValid(label):
            return
        try:
            self._labels.remove(label)
        except (ValueError, RuntimeError):
            # ValueError: already popleft'd by stack-cap eviction.
            # RuntimeError: defensive — comparison touched another
            # half-deleted Qt object mid-iteration.
            return
        self._remove_label(label)

    def _remove_label(self, label: QtWidgets.QFrame) -> None:
        if _qt_isValid(label):
            self._layout.removeWidget(label)
            label.deleteLater()
        if not self._labels and _qt_isValid(self):
            self.hide()
