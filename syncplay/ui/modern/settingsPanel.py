"""Settings + Playback dialogs.

Two dialogs are exposed here:

- `SettingsDialog`: tabbed sections covering Connection, Sync,
  Behavior, Privacy, and Notifications. Lives behind the menu-bar
  **Settings** entry.
- `PlaybackDialog`: small focused dialog with the live media options
  (audio track, subtitle track, subtitle delay, chat-on-video). Lives
  behind the menu-bar **Playback** entry, separated out so the most
  frequently-touched controls are a single click away instead of
  hidden inside the larger settings panel.

Both dialogs persist through the same `_persist_setting` path
MainWindow exposes — values land in the INI exactly the way upstream
expects to read them, so behaviour stays consistent for users who
already know upstream Syncplay.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from syncplay import constants


# Upstream-defined enum values; surfaced verbatim so user choices land in
# the INI exactly the way upstream expects to read them back.
_PRIVACY_OPTIONS = [
    ("Send actual value", constants.PRIVACY_SENDRAW_MODE),
    ("Send hashed value", constants.PRIVACY_SENDHASHED_MODE),
    ("Don't send at all", constants.PRIVACY_DONTSEND_MODE),
]

_UNPAUSE_OPTIONS = [
    ("Always unpause", constants.UNPAUSE_ALWAYS_MODE),
    ("Only if all others are ready", constants.UNPAUSE_IFOTHERSREADY_MODE),
    ("Only if at least N users are ready", constants.UNPAUSE_IFMINUSERSREADY_MODE),
]


class SettingsDialog(QtWidgets.QDialog):

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        config: dict,
        fileinfo: Optional[dict],
        get_player: Callable[[], Any],
        on_persist: Callable[[str, Any], None],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.setMinimumHeight(520)

        self._config = config
        self._get_player = get_player
        self._on_persist = on_persist

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._tabs = QtWidgets.QTabWidget(self)
        self._tabs.addTab(self._build_connection_tab(), "Connection")
        self._tabs.addTab(self._build_sync_tab(), "Sync")
        self._tabs.addTab(self._build_behavior_tab(), "Behavior")
        self._tabs.addTab(self._build_privacy_tab(), "Privacy")
        self._tabs.addTab(self._build_notifications_tab(), "Notifications")
        outer.addWidget(self._tabs, 1)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.accept)
        button_box.accepted.connect(self.accept)
        outer.addWidget(button_box)

    # ==================================================================
    # Public hooks called by MainWindow
    # ==================================================================

    def set_fileinfo(self, fileinfo: dict) -> None:
        # Playback options now live in PlaybackDialog. SettingsDialog
        # used to populate audio/subtitle track dropdowns from fileinfo;
        # those have moved. This stub is kept so MainWindow can call it
        # uniformly on every dialog without checking the class first.
        return

    # ==================================================================
    # Tab builders
    # ==================================================================

    def _build_connection_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        host_port = f"{self._config.get('host', '')}:{self._config.get('port', '')}"
        form.addRow("Server", self._readonly_label(host_port))
        form.addRow("Nickname", self._readonly_label(self._config.get("name", "")))
        form.addRow("Default room", self._readonly_label(self._config.get("room", "")))

        note = QtWidgets.QLabel(
            "These four values are set on the connect screen. Changing them "
            "requires reconnecting — relaunch the app to pick up a new value."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", note)

        return widget

    def _build_sync_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        intro = QtWidgets.QLabel(
            "When peers drift apart in playback position, Syncplay nudges "
            "your speed/position to bring you back in line. Tune that here."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow(intro)

        self._slow_on_desync = self._make_bool(
            "slowOnDesync", default=True, label="Slow down when ahead of others"
        )
        form.addRow("Slow down", self._slow_on_desync)

        self._rewind_on_desync = self._make_bool(
            "rewindOnDesync", default=True, label="Rewind if I'm too far ahead"
        )
        form.addRow("Rewind", self._rewind_on_desync)

        self._fastfwd_on_desync = self._make_bool(
            "fastforwardOnDesync", default=True, label="Fast-forward if I'm too far behind"
        )
        form.addRow("Fast-forward", self._fastfwd_on_desync)

        self._dont_slow_down_with_me = self._make_bool(
            "dontSlowDownWithMe", default=False,
            label="Don't slow down on my account (others ignore me when computing position)"
        )
        form.addRow("Drift weighting", self._dont_slow_down_with_me)

        self._slowdown_thresh = self._make_float(
            "slowdownThreshold",
            default=float(constants.DEFAULT_SLOWDOWN_KICKIN_THRESHOLD)
            if hasattr(constants, "DEFAULT_SLOWDOWN_KICKIN_THRESHOLD") else 1.5,
            minimum=0.1, maximum=10.0, step=0.1, suffix=" s",
        )
        form.addRow("Slowdown kick-in", self._slowdown_thresh)

        self._rewind_thresh = self._make_float(
            "rewindThreshold",
            default=float(constants.DEFAULT_REWIND_THRESHOLD)
            if hasattr(constants, "DEFAULT_REWIND_THRESHOLD") else 4.0,
            minimum=1.0, maximum=120.0, step=0.5, suffix=" s",
        )
        form.addRow("Rewind threshold", self._rewind_thresh)

        self._ff_thresh = self._make_float(
            "fastforwardThreshold",
            default=float(constants.DEFAULT_FASTFORWARD_THRESHOLD)
            if hasattr(constants, "DEFAULT_FASTFORWARD_THRESHOLD") else 5.0,
            minimum=1.0, maximum=120.0, step=0.5, suffix=" s",
        )
        form.addRow("Fast-forward threshold", self._ff_thresh)

        return widget

    def _build_behavior_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self._ready_at_start = self._make_bool(
            "readyAtStart", default=False, label="Mark me ready at startup"
        )
        form.addRow("Readiness", self._ready_at_start)

        self._pause_on_leave = self._make_bool(
            "pauseOnLeave", default=False, label="Pause when someone leaves the room"
        )
        form.addRow("On leave", self._pause_on_leave)

        # Unpause action — combo of three upstream modes.
        self._unpause_combo = QtWidgets.QComboBox()
        for label, value in _UNPAUSE_OPTIONS:
            self._unpause_combo.addItem(label, userData=value)
        self._select_combo_data(
            self._unpause_combo,
            self._config.get("unpauseAction") or constants.UNPAUSE_IFOTHERSREADY_MODE,
        )
        self._unpause_combo.currentIndexChanged.connect(
            lambda i: self._persist("unpauseAction", self._unpause_combo.itemData(i))
        )
        form.addRow("When I press play", self._unpause_combo)

        self._autoplay_min_users = QtWidgets.QSpinBox()
        self._autoplay_min_users.setRange(1, 99)
        try:
            self._autoplay_min_users.setValue(int(self._config.get("autoplayMinUsers") or 3))
        except (TypeError, ValueError):
            self._autoplay_min_users.setValue(3)
        self._autoplay_min_users.valueChanged.connect(
            lambda v: self._persist("autoplayMinUsers", int(v))
        )
        form.addRow("Min users for autoplay", self._autoplay_min_users)

        self._autoplay_same_files = self._make_bool(
            "autoplayRequireSameFilenames", default=True,
            label="Require everyone to have the same filename to autoplay",
        )
        form.addRow("Autoplay safety", self._autoplay_same_files)

        self._shared_playlist = self._make_bool(
            "sharedPlaylistEnabled", default=True,
            label="Enable shared playlist (room-wide queue)",
        )
        form.addRow("Playlist", self._shared_playlist)

        self._loop_playlist = self._make_bool(
            "loopAtEndOfPlaylist", default=False,
            label="Loop the playlist when the last item ends",
        )
        form.addRow("", self._loop_playlist)

        self._loop_single = self._make_bool(
            "loopSingleFiles", default=False,
            label="Loop the current file when it ends",
        )
        form.addRow("", self._loop_single)

        return widget

    def _build_privacy_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        intro = QtWidgets.QLabel(
            "Syncplay normally tells the room what file (name, size, duration) "
            "you have loaded so it can verify everyone watches the same thing. "
            "If you'd rather not share the raw values, switch to hashed (the "
            "room can only see whether files match) or disabled (no info at all)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow(intro)

        self._filename_priv = QtWidgets.QComboBox()
        for label, value in _PRIVACY_OPTIONS:
            self._filename_priv.addItem(label, userData=value)
        self._select_combo_data(
            self._filename_priv,
            self._config.get("filenamePrivacyMode") or constants.PRIVACY_SENDRAW_MODE,
        )
        self._filename_priv.currentIndexChanged.connect(
            lambda i: self._persist("filenamePrivacyMode", self._filename_priv.itemData(i))
        )
        form.addRow("Filename privacy", self._filename_priv)

        self._filesize_priv = QtWidgets.QComboBox()
        for label, value in _PRIVACY_OPTIONS:
            self._filesize_priv.addItem(label, userData=value)
        self._select_combo_data(
            self._filesize_priv,
            self._config.get("filesizePrivacyMode") or constants.PRIVACY_SENDRAW_MODE,
        )
        self._filesize_priv.currentIndexChanged.connect(
            lambda i: self._persist("filesizePrivacyMode", self._filesize_priv.itemData(i))
        )
        form.addRow("File size privacy", self._filesize_priv)

        self._only_trusted = self._make_bool(
            "onlySwitchToTrustedDomains", default=True,
            label="Only auto-switch to URLs on the trusted domains list below",
        )
        form.addRow("Trusted domains", self._only_trusted)

        self._trusted_domains = QtWidgets.QPlainTextEdit()
        self._trusted_domains.setPlaceholderText("one domain per line")
        td = self._config.get("trustedDomains") or []
        if isinstance(td, list):
            self._trusted_domains.setPlainText("\n".join(td))
        elif isinstance(td, str):
            self._trusted_domains.setPlainText(td)
        self._trusted_domains.setFixedHeight(90)
        self._trusted_domains.textChanged.connect(self._on_trusted_domains_changed)
        form.addRow("", self._trusted_domains)

        return widget

    def _build_notifications_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        intro = QtWidgets.QLabel(
            "Toasts and on-screen-display warnings. The default fork "
            "behaviour is quiet — flip these on if you want more nagging."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow(intro)

        self._show_osd = self._make_bool(
            "showOSD", default=False, label="Show on-screen overlay messages at all"
        )
        form.addRow("OSD master", self._show_osd)

        self._show_osd_warnings = self._make_bool(
            "showOSDWarnings", default=False, label="Show warning toasts"
        )
        form.addRow("Warnings", self._show_osd_warnings)

        self._show_slowdown_osd = self._make_bool(
            "showSlowdownOSD", default=False, label="Show slowdown / speedup events"
        )
        form.addRow("Sync events", self._show_slowdown_osd)

        self._show_same_room_osd = self._make_bool(
            "showSameRoomOSD", default=True, label="Show events from users in my room"
        )
        form.addRow("Same-room events", self._show_same_room_osd)

        self._show_diff_room_osd = self._make_bool(
            "showDifferentRoomOSD", default=False, label="Show events from other rooms"
        )
        form.addRow("Cross-room events", self._show_diff_room_osd)

        self._show_non_controller_osd = self._make_bool(
            "showNonControllerOSD", default=False, label="Show events triggered by non-controllers"
        )
        form.addRow("Non-controller events", self._show_non_controller_osd)

        self._show_duration_notif = self._make_bool(
            "showDurationNotification", default=True,
            label="Notify me when file durations don't match across the room",
        )
        form.addRow("Duration mismatch", self._show_duration_notif)

        self._autohide_spin = QtWidgets.QSpinBox()
        self._autohide_spin.setRange(40, 30000)
        self._autohide_spin.setSingleStep(20)
        self._autohide_spin.setSuffix(" ms")
        self._autohide_spin.setValue(int(self._config.get("fullscreenAutohideMs") or 120))
        self._autohide_spin.valueChanged.connect(
            lambda v: self._persist("fullscreenAutohideMs", int(v))
        )
        form.addRow("Fullscreen chat auto-hide", self._autohide_spin)

        return widget

    # ==================================================================
    # Reusable widget factories
    # ==================================================================

    def _make_bool(self, key: str, default: bool, label: str) -> QtWidgets.QCheckBox:
        cb = QtWidgets.QCheckBox(label)
        current = self._config.get(key)
        if current is None:
            current = default
        cb.setChecked(bool(current))
        cb.toggled.connect(lambda v, k=key: self._persist(k, bool(v)))
        return cb

    def _make_float(
        self,
        key: str,
        default: float,
        minimum: float,
        maximum: float,
        step: float,
        suffix: str = "",
    ) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        if suffix:
            spin.setSuffix(suffix)
        try:
            spin.setValue(float(self._config.get(key) or default))
        except (TypeError, ValueError):
            spin.setValue(default)
        spin.valueChanged.connect(lambda v, k=key: self._persist(k, float(v)))
        return spin

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _populate_combo(combo: QtWidgets.QComboBox, items: list) -> None:
        combo.blockSignals(True)
        combo.clear()
        for entry in items:
            combo.addItem(entry.get("label", str(entry)), userData=entry.get("id"))
        combo.blockSignals(False)

    @staticmethod
    def _select_combo_data(combo: QtWidgets.QComboBox, value: Any) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    @staticmethod
    def _wrap_layout(layout: QtWidgets.QLayout) -> QtWidgets.QWidget:
        wrapper = QtWidgets.QWidget()
        wrapper.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return wrapper

    @staticmethod
    def _readonly_label(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text or "")
        label.setStyleSheet("color: #444;")
        label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        return label

    def _persist(self, key: str, value: Any) -> None:
        self._config[key] = value
        try:
            self._on_persist(key, value)
        except Exception:
            pass

    # ==================================================================
    # Per-control handlers
    # ==================================================================

    def _on_trusted_domains_changed(self) -> None:
        raw = self._trusted_domains.toPlainText()
        domains = [line.strip() for line in raw.splitlines() if line.strip()]
        self._persist("trustedDomains", domains)


# ======================================================================
# Playback dialog
# ======================================================================


class PlaybackDialog(QtWidgets.QDialog):
    """Small focused dialog for live media options.

    Sits behind the menu-bar **Playback** entry. Holds the controls
    users touch most while watching: audio track, subtitle track,
    subtitle delay, and the chat-on-video overlay toggle. Splitting
    these out of the main Settings dialog means they're one click away
    and don't get buried under five other tabs of less-frequent
    preferences.
    """

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        config: dict,
        fileinfo: Optional[dict],
        get_player: Callable[[], Any],
        on_persist: Callable[[str, Any], None],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Playback")
        self.setMinimumWidth(420)

        self._config = config
        self._get_player = get_player
        self._on_persist = on_persist

        form = QtWidgets.QFormLayout(self)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self._audio_combo = QtWidgets.QComboBox()
        self._audio_combo.setEnabled(False)
        self._audio_combo.currentIndexChanged.connect(self._on_audio_changed)
        form.addRow("Audio track", self._audio_combo)

        self._sub_combo = QtWidgets.QComboBox()
        self._sub_combo.setEnabled(False)
        self._sub_combo.currentIndexChanged.connect(self._on_subtitle_changed)
        form.addRow("Subtitle track", self._sub_combo)

        sub_delay_row = QtWidgets.QHBoxLayout()
        self._sub_delay_spin = QtWidgets.QSpinBox()
        self._sub_delay_spin.setRange(-10000, 10000)
        self._sub_delay_spin.setSingleStep(50)
        self._sub_delay_spin.setSuffix(" ms")
        self._sub_delay_spin.setValue(int(self._config.get("subtitleDelayDefaultMs") or 0))
        self._sub_delay_spin.valueChanged.connect(self._on_sub_delay_changed)
        sub_delay_reset = QtWidgets.QPushButton("Reset")
        sub_delay_reset.clicked.connect(lambda: self._sub_delay_spin.setValue(0))
        sub_delay_row.addWidget(self._sub_delay_spin, 1)
        sub_delay_row.addWidget(sub_delay_reset, 0)
        sub_delay_wrapper = QtWidgets.QWidget()
        sub_delay_wrapper.setLayout(sub_delay_row)
        sub_delay_row.setContentsMargins(0, 0, 0, 0)
        form.addRow("Subtitle delay", sub_delay_wrapper)

        self._chat_on_video = QtWidgets.QCheckBox("Show chat on video")
        self._chat_on_video.setChecked(bool(self._config.get("chatOnVideoEnabled")))
        self._chat_on_video.toggled.connect(self._on_chat_on_video)
        form.addRow("Chat overlay", self._chat_on_video)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.accept)
        button_box.accepted.connect(self.accept)
        form.addRow(button_box)

        # Prefer a live track list from the running player over the
        # fileinfo dict — libvlc can renumber tracks between parse
        # time (when fileinfo was captured) and playback time, so the
        # cached IDs go stale. The cycle-shortcut path already queries
        # live; mirror that here so the dropdown selections actually
        # apply.
        live_info = self._fetch_live_tracks() if get_player else None
        if live_info is not None:
            self.set_fileinfo(live_info)
        elif fileinfo is not None:
            self.set_fileinfo(fileinfo)

    def _fetch_live_tracks(self) -> Optional[dict]:
        try:
            player = self._get_player()
        except Exception:
            return None
        if player is None:
            return None
        info: dict = {}
        if hasattr(player, "get_audio_tracks"):
            try:
                info["audio_tracks"] = player.get_audio_tracks()
            except Exception:
                pass
        if hasattr(player, "get_subtitle_tracks"):
            try:
                info["subtitle_tracks"] = player.get_subtitle_tracks()
            except Exception:
                pass
        return info or None

    # ------------------------------------------------------------------
    # Public hook called by MainWindow when libvlc finishes parsing media
    # ------------------------------------------------------------------

    def set_fileinfo(self, fileinfo: dict) -> None:
        audio_tracks = fileinfo.get("audio_tracks") or []
        sub_tracks = fileinfo.get("subtitle_tracks") or []
        self._populate_combo(self._audio_combo, audio_tracks)
        self._populate_combo(self._sub_combo, sub_tracks)
        self._audio_combo.setEnabled(bool(audio_tracks))
        self._sub_combo.setEnabled(bool(sub_tracks))

    # ------------------------------------------------------------------

    @staticmethod
    def _populate_combo(combo: QtWidgets.QComboBox, items: list) -> None:
        combo.blockSignals(True)
        combo.clear()
        for entry in items:
            combo.addItem(entry.get("label", str(entry)), userData=entry.get("id"))
        combo.blockSignals(False)

    def _persist(self, key: str, value: Any) -> None:
        self._config[key] = value
        try:
            self._on_persist(key, value)
        except Exception:
            pass

    def _on_audio_changed(self, index: int) -> None:
        track_id = self._audio_combo.itemData(index)
        label = self._audio_combo.itemText(index) or "(unknown)"
        player = self._get_player()
        if player is None or track_id is None or not hasattr(player, "set_audio_track"):
            return
        try:
            player.set_audio_track(int(track_id))
            self._notify_parent(f"Audio: {label}")
        except Exception as exc:
            self._notify_parent(f"Audio change failed: {exc}")

    def _on_subtitle_changed(self, index: int) -> None:
        track_id = self._sub_combo.itemData(index)
        label = self._sub_combo.itemText(index) or "(unknown)"
        player = self._get_player()
        if player is None or track_id is None or not hasattr(player, "set_subtitle_track"):
            return
        try:
            player.set_subtitle_track(int(track_id))
            self._notify_parent(f"Subtitle: {label}")
        except Exception as exc:
            self._notify_parent(f"Subtitle change failed: {exc}")

    def _notify_parent(self, text: str) -> None:
        """Show a brief toast on the MainWindow if available."""
        parent = self.parent()
        if parent is not None and hasattr(parent, "_brief_status"):
            try:
                parent._brief_status(text)
            except Exception:
                pass

    def _on_sub_delay_changed(self, value: int) -> None:
        player = self._get_player()
        if player is not None and hasattr(player, "set_subtitle_delay_ms"):
            try:
                player.set_subtitle_delay_ms(int(value))
            except Exception:
                pass
        self._persist("subtitleDelayDefaultMs", int(value))

    def _on_chat_on_video(self, on: bool) -> None:
        self._persist("chatOnVideoEnabled", bool(on))
