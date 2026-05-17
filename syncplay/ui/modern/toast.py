"""Non-intrusive corner toast — replacement for VLC OSD overlays.

Receives short status messages from the player adapter (mute, volume,
delay, speed) and optionally chat lines when `chatOnVideoEnabled` is on,
renders them stacked top-right of the video area, and auto-dismisses
each after its duration.

Parented to MainWindow (not VideoWidget) so it floats above libvlc's
native X11 render surface — child widgets of a WA_NativeWindow get
painted over on Linux. MainWindow positions us via reposition() from
its resize / fullscreen-toggle paths.
"""

from __future__ import annotations

from collections import deque
from typing import Deque

from PySide6 import QtCore, QtWidgets


class Toast(QtWidgets.QFrame):

    MAX_STACK = 3
    DEFAULT_DURATION_MS = 2000

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toastStack")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            "QFrame#toastStack { background: transparent; }"
            "QLabel.toastLine { "
            "  background: rgba(22, 22, 22, 220); color: #f4f4f4; "
            "  padding: 6px 12px; border-radius: 6px; font-size: 13px; "
            "}"
        )
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)  # push labels to the top
        self._labels: Deque[QtWidgets.QLabel] = deque()
        self.hide()

    def show_message(self, text: str, duration: int | None = None) -> None:
        text = str(text).strip()
        if not text:
            return
        if duration is None or duration <= 0:
            duration = self.DEFAULT_DURATION_MS

        label = QtWidgets.QLabel(text, self)
        label.setProperty("class", "toastLine")
        label.setTextFormat(QtCore.Qt.PlainText)
        label.setWordWrap(True)
        label.setMaximumWidth(360)
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        # Stylesheet selector uses `class` property; re-polish so it picks up.
        label.style().unpolish(label)
        label.style().polish(label)

        # Insert above the stretch (stretch is the last item).
        self._layout.insertWidget(self._layout.count() - 1, label, 0, QtCore.Qt.AlignRight)
        self._labels.append(label)

        # Cap stack depth — drop the oldest.
        while len(self._labels) > self.MAX_STACK:
            oldest = self._labels.popleft()
            self._remove_label(oldest)

        QtCore.QTimer.singleShot(duration, lambda lbl=label: self._expire(lbl))

        if not self.isVisible():
            self.show()
            self.raise_()

    def reposition(self, video_geometry_in_window: QtCore.QRect) -> None:
        """Anchor top-right of the given video-pane rect (in window coords)."""
        inset = 12
        width = 380
        # Cap to the video pane width minus insets so we never overflow.
        width = max(160, min(width, video_geometry_in_window.width() - 2 * inset))
        # Generous height so stacked labels fit; layout aligns top so unused
        # vertical space is just transparent.
        height = max(180, video_geometry_in_window.height() - 2 * inset)
        x = video_geometry_in_window.x() + video_geometry_in_window.width() - width - inset
        y = video_geometry_in_window.y() + inset
        self.setGeometry(x, y, width, height)

    def _expire(self, label: QtWidgets.QLabel) -> None:
        try:
            self._labels.remove(label)
        except ValueError:
            return  # already removed by stack-cap eviction
        self._remove_label(label)

    def _remove_label(self, label: QtWidgets.QLabel) -> None:
        self._layout.removeWidget(label)
        label.deleteLater()
        if not self._labels:
            self.hide()
