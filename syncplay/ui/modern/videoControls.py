"""Auto-hiding VLC-style control bar overlaid on the video.

Single horizontal row: play/pause, current time, seek slider, total time,
mute toggle, volume slider, fullscreen toggle. Stateless — MainWindow
drives it via `update_state(...)` from a periodic timer that polls
libvlc, and the bar emits signals back when the user clicks or drags.

Lives as a child of MainWindow (not VideoWidget) so it floats above
libvlc's native X11 render surface — child widgets of a WA_NativeWindow
get painted over on Linux. MainWindow positions us via setGeometry on
its resize event and shows/hides via cursor-position polling.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class _JumpSlider(QtWidgets.QSlider):
    """QSlider that jumps to the click position instead of paging.

    Qt's default treats LeftButton on the groove as a page-step, so
    clicking near the end of a long bar only inches the value forward.
    VLC's seek bar jumps to the click. We override mousePressEvent to
    setValue at the click, then fall through to super so QSlider's
    native press handler sets up drag tracking (the handle is now at
    the click position so super's hit-test treats this as a handle
    press, not a groove press).

    The previous implementation used a QProxyStyle that returned
    `int(Qt.LeftButton)` from `SH_Slider_AbsoluteSetButtons`, but
    PySide6's `Qt.MouseButton` enum can't be cast with `int()` on
    every Qt version — hence this override.
    """

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton and self.maximum() > self.minimum():
            pos = event.position().toPoint()
            if self.orientation() == QtCore.Qt.Horizontal:
                new_val = QtWidgets.QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), pos.x(), self.width()
                )
            else:
                new_val = QtWidgets.QStyle.sliderValueFromPosition(
                    self.minimum(),
                    self.maximum(),
                    self.height() - pos.y(),
                    self.height(),
                )
            self.setValue(new_val)
        super().mousePressEvent(event)


def _format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class VideoControls(QtWidgets.QFrame):

    playPauseRequested = QtCore.Signal()
    seekToSecondsRequested = QtCore.Signal(float)
    volumeChangedTo = QtCore.Signal(int)
    muteToggleRequested = QtCore.Signal()
    fullscreenToggleRequested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("videoControls")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#videoControls { background: rgba(20, 20, 20, 230); }"
            "QToolButton { color: #eee; background: transparent; "
            "border: none; padding: 4px 8px; font-size: 14px; }"
            "QToolButton:hover { background: #2a2a2a; border-radius: 3px; }"
            "QToolButton:pressed { background: #1a1a1a; border-radius: 3px; }"
            # QLabel needs an explicit transparent background: on Windows
            # it picks up the system widget color (light gray) otherwise,
            # which renders as a white box around the time labels.
            "QLabel { color: #ccc; font-size: 11px; min-width: 44px; "
            "background: transparent; }"
            # QSlider needs the same: without a widget-level transparent
            # background, Windows renders a light frame around the entire
            # slider widget that swallows the dark groove styling.
            "QSlider { background: transparent; border: none; }"
            "QSlider::groove:horizontal { background: #444; height: 4px; "
            "border-radius: 2px; border: none; }"
            "QSlider::sub-page:horizontal { background: #2a8; "
            "border-radius: 2px; border: none; }"
            "QSlider::add-page:horizontal { background: #2a2a2a; "
            "border-radius: 2px; border: none; }"
            "QSlider::handle:horizontal { background: #fff; width: 10px; "
            "margin: -4px 0; border-radius: 5px; border: none; }"
        )
        self.setFixedHeight(34)

        self._play_btn = QtWidgets.QToolButton(self)
        self._play_btn.setText("▶")
        self._play_btn.setToolTip("Play / Pause")
        # AutoRaise suppresses the native Windows button frame so the
        # stylesheet's transparent background actually shows through.
        self._play_btn.setAutoRaise(True)
        self._play_btn.clicked.connect(self.playPauseRequested.emit)

        self._time_current = QtWidgets.QLabel("0:00", self)
        self._time_current.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self._seek = _JumpSlider(QtCore.Qt.Horizontal, self)
        self._seek.setRange(0, 0)
        self._user_seeking = False
        self._seek.sliderPressed.connect(self._on_seek_press)
        self._seek.sliderReleased.connect(self._on_seek_release)
        # Label tracks the slider unconditionally — refresh-driven
        # setValue and drag-driven setValue both flow through here.
        self._seek.valueChanged.connect(
            lambda v: self._time_current.setText(_format_time(v))
        )
        self._seek.setSingleStep(5)
        self._seek.setPageStep(30)

        self._time_total = QtWidgets.QLabel("0:00", self)
        self._time_total.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self._mute_btn = QtWidgets.QToolButton(self)
        self._mute_btn.setText("🔊")
        self._mute_btn.setToolTip("Mute")
        self._mute_btn.setAutoRaise(True)
        self._mute_btn.clicked.connect(self.muteToggleRequested.emit)

        self._volume = _JumpSlider(QtCore.Qt.Horizontal, self)
        # libvlc accepts 0-200, but anything above 100 is software
        # amplification — saturates around 140 on Windows audio
        # backends (DirectSound / WASAPI), clips on every platform.
        # Cap at 100 so every slider position is audibly meaningful.
        self._volume.setRange(0, 100)
        self._volume.setValue(100)
        self._volume.setFixedWidth(90)
        self._volume.valueChanged.connect(self._on_volume_changed)

        self._fs_btn = QtWidgets.QToolButton(self)
        self._fs_btn.setText("⛶")
        self._fs_btn.setToolTip("Fullscreen")
        self._fs_btn.setAutoRaise(True)
        self._fs_btn.clicked.connect(self.fullscreenToggleRequested.emit)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)
        layout.addWidget(self._play_btn)
        layout.addWidget(self._time_current)
        layout.addWidget(self._seek, 1)
        layout.addWidget(self._time_total)
        layout.addWidget(self._mute_btn)
        layout.addWidget(self._volume)
        layout.addWidget(self._fs_btn)

    # --- State sync -------------------------------------------------------

    def update_state(
        self,
        *,
        is_playing: bool,
        position_s: float,
        duration_s: float,
        volume: int,
        is_muted: bool,
        is_fullscreen: bool,
    ) -> None:
        self._play_btn.setText("⏸" if is_playing else "▶")
        self._time_total.setText(_format_time(duration_s))

        if not self._user_seeking:
            new_range = (0, max(0, int(duration_s)))
            if (self._seek.minimum(), self._seek.maximum()) != new_range:
                self._seek.setRange(*new_range)
            # No blockSignals: valueChanged fires here and updates the
            # current-time label via the lambda connection above.
            self._seek.setValue(int(position_s))

        # Block volumeChangedTo so refresh-driven values don't loop back
        # out to the player as a user-initiated change.
        self._volume.blockSignals(True)
        self._volume.setValue(int(volume))
        self._volume.blockSignals(False)

        self._mute_btn.setText("🔇" if is_muted else "🔊")
        self._fs_btn.setText("🗗" if is_fullscreen else "⛶")

    # --- Internals --------------------------------------------------------

    def _on_seek_press(self) -> None:
        self._user_seeking = True

    def _on_seek_release(self) -> None:
        target = float(self._seek.value())
        self._user_seeking = False
        self.seekToSecondsRequested.emit(target)

    def _on_volume_changed(self, value: int) -> None:
        self.volumeChangedTo.emit(int(value))
