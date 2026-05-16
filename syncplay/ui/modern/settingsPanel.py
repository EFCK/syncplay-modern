"""Settings dialog: Quick + collapsible Advanced sections.

Changes apply live (audio track, subtitle track, subtitle delay) and
persist to the INI through `ConfigurationGetter.setConfigOption`.
Connection-related fields (server / port / nickname / room) are displayed
read-only because changing them requires a reconnect; they're surfaced
here for visibility and to remind the user where they are connected.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets


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
        self.setMinimumWidth(420)

        self._config = config
        self._get_player = get_player
        self._on_persist = on_persist

        layout = QtWidgets.QVBoxLayout(self)

        # === Quick section =================================================
        quick_box = QtWidgets.QGroupBox("Quick", self)
        quick_form = QtWidgets.QFormLayout(quick_box)
        quick_form.setLabelAlignment(QtCore.Qt.AlignRight)

        self._audio_combo = QtWidgets.QComboBox()
        self._audio_combo.setEnabled(False)
        self._audio_combo.currentIndexChanged.connect(self._on_audio_changed)
        quick_form.addRow("Audio track", self._audio_combo)

        self._sub_combo = QtWidgets.QComboBox()
        self._sub_combo.setEnabled(False)
        self._sub_combo.currentIndexChanged.connect(self._on_subtitle_changed)
        quick_form.addRow("Subtitle track", self._sub_combo)

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
        quick_form.addRow("Subtitle delay", self._wrap_layout(sub_delay_row))

        self._chat_on_video = QtWidgets.QCheckBox("Show chat on video")
        self._chat_on_video.setChecked(bool(self._config.get("chatOnVideoEnabled")))
        self._chat_on_video.toggled.connect(self._on_chat_on_video)
        quick_form.addRow("", self._chat_on_video)

        # Connection summary (read-only, requires reconnect)
        host_port = f"{self._config.get('host', '')}:{self._config.get('port', '')}"
        quick_form.addRow("Server", self._readonly_label(host_port))
        quick_form.addRow("Nickname", self._readonly_label(self._config.get("name", "")))
        quick_form.addRow("Room", self._readonly_label(self._config.get("room", "")))
        note = QtWidgets.QLabel(
            "Changing server / nickname / room requires reconnecting."
        )
        note.setStyleSheet("color: #888; font-size: 11px;")
        quick_form.addRow("", note)

        layout.addWidget(quick_box)

        # === Advanced section (collapsible) ================================
        self._advanced_button = QtWidgets.QToolButton(self)
        self._advanced_button.setText("▶ Advanced")
        self._advanced_button.setCheckable(True)
        self._advanced_button.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; padding: 4px; }"
        )
        self._advanced_button.toggled.connect(self._toggle_advanced)

        self._advanced_box = QtWidgets.QGroupBox()
        self._advanced_box.setVisible(False)
        adv_form = QtWidgets.QFormLayout(self._advanced_box)

        self._ready_at_start = QtWidgets.QCheckBox("Mark me ready at startup")
        self._ready_at_start.setChecked(bool(self._config.get("readyAtStart")))
        self._ready_at_start.toggled.connect(
            lambda v: self._persist("readyAtStart", v)
        )
        adv_form.addRow("Readiness", self._ready_at_start)

        self._pause_on_leave = QtWidgets.QCheckBox("Pause when someone leaves")
        self._pause_on_leave.setChecked(bool(self._config.get("pauseOnLeave")))
        self._pause_on_leave.toggled.connect(
            lambda v: self._persist("pauseOnLeave", v)
        )
        adv_form.addRow("", self._pause_on_leave)

        self._slow_on_desync = QtWidgets.QCheckBox("Slow down when ahead of others")
        self._slow_on_desync.setChecked(bool(self._config.get("slowOnDesync", True)))
        self._slow_on_desync.toggled.connect(
            lambda v: self._persist("slowOnDesync", v)
        )
        adv_form.addRow("Drift correction", self._slow_on_desync)

        self._rewind_on_desync = QtWidgets.QCheckBox("Rewind if I get ahead")
        self._rewind_on_desync.setChecked(bool(self._config.get("rewindOnDesync", True)))
        self._rewind_on_desync.toggled.connect(
            lambda v: self._persist("rewindOnDesync", v)
        )
        adv_form.addRow("", self._rewind_on_desync)

        self._fastfwd_on_desync = QtWidgets.QCheckBox("Fast-forward if I get behind")
        self._fastfwd_on_desync.setChecked(bool(self._config.get("fastforwardOnDesync", True)))
        self._fastfwd_on_desync.toggled.connect(
            lambda v: self._persist("fastforwardOnDesync", v)
        )
        adv_form.addRow("", self._fastfwd_on_desync)

        self._autohide_spin = QtWidgets.QSpinBox()
        self._autohide_spin.setRange(500, 30000)
        self._autohide_spin.setSingleStep(500)
        self._autohide_spin.setSuffix(" ms")
        self._autohide_spin.setValue(int(self._config.get("fullscreenAutohideMs") or 3000))
        self._autohide_spin.valueChanged.connect(
            lambda v: self._persist("fullscreenAutohideMs", v)
        )
        adv_form.addRow("Fullscreen chat auto-hide", self._autohide_spin)

        self._show_osd_warnings = QtWidgets.QCheckBox("Allow corner toast for warnings")
        self._show_osd_warnings.setChecked(bool(self._config.get("showOSDWarnings", False)))
        self._show_osd_warnings.toggled.connect(
            lambda v: self._persist("showOSDWarnings", v)
        )
        adv_form.addRow("Notifications", self._show_osd_warnings)

        self._trusted_domains = QtWidgets.QPlainTextEdit()
        self._trusted_domains.setPlaceholderText("one domain per line")
        td = self._config.get("trustedDomains") or []
        if isinstance(td, list):
            self._trusted_domains.setPlainText("\n".join(td))
        elif isinstance(td, str):
            self._trusted_domains.setPlainText(td)
        self._trusted_domains.setFixedHeight(60)
        self._trusted_domains.textChanged.connect(self._on_trusted_domains_changed)
        adv_form.addRow("Trusted domains", self._trusted_domains)

        layout.addWidget(self._advanced_button)
        layout.addWidget(self._advanced_box)

        # === Buttons =======================================================
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.accept)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Populate dropdowns if we already have file info from a parsed media.
        if fileinfo is not None:
            self.set_fileinfo(fileinfo)

    # --- Public API used by MainWindow ------------------------------------

    def set_fileinfo(self, fileinfo: dict) -> None:
        audio_tracks = fileinfo.get("audio_tracks") or []
        sub_tracks = fileinfo.get("subtitle_tracks") or []
        self._populate_combo(self._audio_combo, audio_tracks)
        self._populate_combo(self._sub_combo, sub_tracks)
        self._audio_combo.setEnabled(bool(audio_tracks))
        self._sub_combo.setEnabled(bool(sub_tracks))

    # --- Internals --------------------------------------------------------

    @staticmethod
    def _populate_combo(combo: QtWidgets.QComboBox, items: list) -> None:
        # Avoid firing currentIndexChanged while we rebuild the model.
        combo.blockSignals(True)
        combo.clear()
        for entry in items:
            combo.addItem(entry.get("label", str(entry)), userData=entry.get("id"))
        combo.blockSignals(False)

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

    def _toggle_advanced(self, on: bool) -> None:
        self._advanced_button.setText("▼ Advanced" if on else "▶ Advanced")
        self._advanced_box.setVisible(on)
        self.adjustSize()

    def _persist(self, key: str, value: Any) -> None:
        self._config[key] = value
        try:
            self._on_persist(key, value)
        except Exception:
            pass

    def _on_audio_changed(self, index: int) -> None:
        track_id = self._audio_combo.itemData(index)
        player = self._get_player()
        if player is not None and track_id is not None and hasattr(player, "set_audio_track"):
            try:
                player.set_audio_track(int(track_id))
            except Exception:
                pass

    def _on_subtitle_changed(self, index: int) -> None:
        track_id = self._sub_combo.itemData(index)
        player = self._get_player()
        if player is not None and track_id is not None and hasattr(player, "set_subtitle_track"):
            try:
                player.set_subtitle_track(int(track_id))
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

    def _on_trusted_domains_changed(self) -> None:
        raw = self._trusted_domains.toPlainText()
        domains = [line.strip() for line in raw.splitlines() if line.strip()]
        self._persist("trustedDomains", domains)
